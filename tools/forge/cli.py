"""forge: one command line for building, checking and packaging Oblivion mods.

    forge caps [--json]                     capability registry + what works on this machine
    forge spec check <spec> [--set K=V]     validate a spec, list the capabilities it needs
    forge new "<prompt>" [--name slug]      draft a spec from a plain-English idea (kind: plugin)
    forge build <spec> [--set K=V] [--out DIR] [--package] [--json]
    forge package <spec> [--out DIR]        zip the last build for Vortex (plugin + readme)
    forge compare <a.esp> <b.esp> [--json]  byte-identical / record-identical / different
    forge kb <command> ...                  knowledge store (forge kb --help)
    forge dump <plugin> <EDID|FormID>       decode a record's subrecords (read-only)
    forge layout-check <plugin> [--sig S]   re-encode every record of a type byte for byte (read-only)
    forge script-decode <plugin|corpus>     decompile every script's SCDA; survey or --show EDID (read-only)
    forge script-check <plugin|corpus>      compile every script's source, compare bytes with its SCDA

Playtest (tools/playtest, see its README):
    forge playtest <spec|esp> [--cell arena|street|open] [--quit] [--dry-run]   quick-boot test + checks
    forge playtest restore|status|cells     put the real Plugins.txt/ini back, show state, build the cells
    forge test [RUN_DIR] [--json]           report of the last (or a given) playtest run
    forge preview <spec|esp|cells> [--open] browser preview of the test cell / the mod's placed objects

Wrapped tools (arguments pass straight through):
    forge lint|info|records|conflicts|load-order|find ...   -> tools/modlint.py
    forge xedit ...                                          -> tools/xedit_run.py
    forge cs ...                                             -> oblivion_cs_bridge_client.py
    forge asset ...                                          -> python -m assetkit.build

Exit codes: 0 ok, 1 usage/input error, 2 build ran but a check failed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from forge import VERSION, buildlog, capabilities, spec as specmod  # noqa: E402

MODLINT_CMDS = {"lint", "info", "records", "conflicts", "load-order", "find"}
WRAPPED = {
    "xedit": [sys.executable, str(TOOLS / "xedit_run.py")],
    "cs": [sys.executable, str(ROOT / "oblivion_cs_bridge_client.py")],
    "asset": [sys.executable, "-m", "assetkit.build"],
}


def _print(obj, as_json: bool, text: str) -> None:
    print(json.dumps(obj, indent=1, default=str) if as_json else text)


def _sets(pairs: list[str]) -> dict:
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise specmod.SpecError(f"--set needs NAME=VALUE, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


def _guard_output(out_dir: Path) -> None:
    """Never build straight into a game Data folder or Vortex: deploy only through a packaged zip."""
    parts = [x.casefold() for x in out_dir.resolve().parts]
    if "vortex" in parts:
        raise specmod.SpecError(f"refusing to write into a Vortex folder: {out_dir}")
    for d in [out_dir.resolve(), *out_dir.resolve().parents]:
        if (d / "Oblivion.esm").is_file():
            raise specmod.SpecError(f"refusing to write into a game Data folder: {d}. "
                                    "Build elsewhere, then package and install through Vortex.")


# --------------------------------------------------------------------------- caps
def cmd_caps(a) -> int:
    rows = capabilities.table()
    if a.json:
        _print(rows, True, "")
        return 0
    w = max(len(r["capability"]) for r in rows)
    print(f"{'capability'.ljust(w)}  status       ph  confidence              available provider")
    for r in rows:
        avail = r["available"] or ("-" if r["status"] == "planned" else "NOT AVAILABLE here")
        print(f"{r['capability'].ljust(w)}  {r['status']:<11}  {r['phase']:<2}  {r['confidence']:<22}  {avail}")
    return 0


# --------------------------------------------------------------------------- spec
def _load_checked(path, sets) -> tuple[specmod.Spec, list[str]]:
    s = specmod.load(path, _sets(sets))
    return s, specmod.validate(s)


def cmd_spec_check(a) -> int:
    s, errs = _load_checked(a.spec, a.set)
    caps = capabilities.check(specmod.required_caps(s)) if not errs or s.raw.get("kind") in specmod.KINDS else []
    files = []
    if not errs and s.kind == "merge_patch":
        mp = s.section("merge_patch")
        for k in ("vanilla", "installed_dir", "plugins_txt"):
            p = s.resolve(mp[k])
            files.append({"field": f"merge_patch.{k}", "path": str(p), "exists": p.exists()})
        if not isinstance(mp.get("config"), dict):
            p = s.resolve(mp["config"])
            files.append({"field": "merge_patch.config", "path": str(p), "exists": p.exists()})
    kind_status = specmod.KINDS.get(s.raw.get("kind"), "unknown")
    ok = not errs and all(c["ok"] for c in caps) and all(f["exists"] for f in files) \
        and kind_status == "implemented"
    res = {"spec": str(s.path), "valid": not errs, "errors": errs, "kind": s.raw.get("kind"),
           "kind_status": kind_status, "capabilities": caps, "files": files, "buildable_here": ok}
    lines = [f"spec {s.path.name}: {'valid' if not errs else 'INVALID'} (kind {s.raw.get('kind')}: {kind_status})"]
    lines += [f"  error: {e}" for e in errs]
    lines += [f"  cap {c['capability']:<16} {'ok (' + str(c.get('provider')) + ')' if c['ok'] else 'MISSING: ' + c['why']}"
              for c in caps]
    lines += [f"  file {f['field']:<26} {'ok' if f['exists'] else 'NOT FOUND'}  {f['path']}" for f in files]
    lines.append(f"  buildable here: {'yes' if ok else 'no'}")
    _print(res, a.json, "\n".join(lines))
    return 0 if not errs else 1


def cmd_new(a) -> int:
    prompt = a.prompt.strip()
    slug = a.name or re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:48].strip("-") or "new-mod"
    dest = Path(a.dir).resolve() / f"{slug}.yaml"
    if dest.exists():
        print(f"error: {dest} exists; pick another --name", file=sys.stderr)
        return 1
    plugin = "".join(w.capitalize() for w in slug.split("-"))[:40] + ".esp"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(DRAFT.format(slug=slug, prompt=json.dumps(prompt), plugin=plugin), encoding="utf-8")
    print(f"draft spec written: {dest}\n"
          "Fill in records/scripts/assets/test_plan. kind: plugin builds from phase 3; "
          "`forge spec check` shows what is still missing.")
    return 0


DRAFT = """forge_spec: 1
name: {slug}
kind: plugin            # builds from phase 3 (records + scripts through the CS bridge)
status: draft
intent: {prompt}
output:
  plugin: {plugin}
  version: "1.0"
inputs: []              # every external file: {{id, path, permission, role}}
dependencies:
  masters: [Oblivion.esm]
  runtime: []           # e.g. xOBSE 22.x
compatibility_targets: [Oblivion Rebirth+ (Steam, Vortex)]
records: []
scripts: []
assets: []
placements: []
test_plan: []           # in-game steps -> expected result; "it launched" is not a pass
"""


# --------------------------------------------------------------------------- build
def _search_new_mods(s, cfg, explicit: list[Path]) -> tuple[list[Path], list[str]]:
    """Find needed new-mod plugins by file name under merge_patch.new_mod_search folders.

    A folder is searched at the top level only; end it with /** to search all subfolders.
    """
    mp = s.section("merge_patch")
    dirs = []
    for d in mp.get("new_mod_search") or []:
        rec = str(d).replace("\\", "/").endswith("/**")
        dirs.append((s.resolve(str(d)[:-3] if rec else d), rec))
    have = {p.name for p in explicit} | {Path(p).name for p in cfg.get("extra_paths", [])}
    need = [n for n in cfg["new_order"] if n not in have]
    found: list[Path] = []
    problems: list[str] = []
    if not dirs:
        return found, problems
    index: dict[str, list[Path]] = {}
    for d, rec in dirs:
        if not d.is_dir():
            problems.append(f"new_mod_search folder not found: {d}")
            continue
        for f in sorted(d.rglob("*") if rec else d.iterdir()):
            if f.suffix.lower() in (".esp", ".esm") and f.is_file():
                index.setdefault(f.name, []).append(f)
    for n in need:
        c = index.get(n, [])
        hashes = {buildlog.sha256_file(f) for f in c}
        if len(hashes) > 1:
            problems.append(f"{n}: {len(c)} different copies under new_mod_search; pin one in "
                            f"merge_patch.new_mod_paths: " + "; ".join(map(str, c)))
        elif c:
            found.append(c[0])
    return found, problems


def cmd_build(a) -> int:
    t0 = time.time()
    s, errs = _load_checked(a.spec, a.set)
    if errs:
        _print({"status": "invalid-spec", "errors": errs}, a.json,
               "spec invalid:\n" + "\n".join(f"  {e}" for e in errs))
        return 1
    if specmod.KINDS[s.kind] != "implemented":
        print(f"error: kind {s.kind!r} is {specmod.KINDS[s.kind]}", file=sys.stderr)
        return 1
    caps = capabilities.check(specmod.required_caps(s))
    bad = [c for c in caps if not c["ok"]]
    if bad:
        print("error: missing capabilities: " + "; ".join(f"{c['capability']} ({c['why']})" for c in bad),
              file=sys.stderr)
        return 1
    out_dir = s.output_dir(Path(a.out) if a.out else None)
    _guard_output(out_dir)
    if s.kind == "plugin":
        return _build_plugin(s, out_dir, a, t0, caps)
    return _build_merge_patch(s, out_dir, a, t0, caps)


def _build_plugin(s, out_dir: Path, a, t0: float, caps) -> int:
    """kind: plugin (phase 3a): records from the spec -> new plugin, round-trip, lint, log."""
    from forge.providers import plugin as pp
    from forge import records as R
    from forge.kb.build import DEFAULT_DB
    import modlint
    import tes4_plugin as tp

    ids_file = specmod.ids_path(s)
    kb_db = s.resolve(s.raw["kb"]) if s.raw.get("kb") else DEFAULT_DB
    try:
        res = pp.build(s, ids_file, kb_db, s.resolve(s.raw["commands"]) if s.raw.get("commands") else None)
    except (pp.PluginError, R.CodecError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = out_dir / s.output_plugin
    plugin_path.write_bytes(res.data)
    if res.ids_changed:
        ids_file.write_text(json.dumps(res.ids, indent=1) + "\n", encoding="utf-8")

    warnings, failures = [], []
    # round trip: every subrecord we wrote decodes and re-encodes to the same bytes
    rt = {"records": 0, "subrecords": 0, "mismatches": 0}
    pl = None
    for pl, r in tp.iter_records(plugin_path):
        rt["records"] += 1
        subs = [(x.sig, x.data) for x in r.subrecords()]
        for (sig, data), d in zip(subs, R.decode_record(r.sig, subs)):
            rt["subrecords"] += 1
            if R.encode(r.sig, d, d["nth"]) != data:
                rt["mismatches"] += 1
    if pl is not None and pl.errors:
        failures.append(f"parse errors: {pl.errors}")
    if rt["mismatches"] or rt["records"] != len(res.records):
        failures.append(f"round-trip: {rt}")
    lint_data = s.resolve((s.section("lint") or {}).get("data")) if (s.section("lint") or {}).get("data") else None
    lint = None
    if lint_data and lint_data.is_dir():
        lint = modlint.lint_plugin(plugin_path, lint_data, True, None)
        if lint["summary"].get("error"):
            failures.append("lint: " + "; ".join(i["message"] for i in lint["issues"] if i["level"] == "error"))
        if lint["summary"].get("warning"):
            warnings.append("lint: " + "; ".join(i["message"] for i in lint["issues"] if i["level"] == "warning"))
    else:
        warnings.append("lint skipped: set lint.data to a Data folder holding the masters")
    out_sha = buildlog.sha256_bytes(res.data)
    expect = s.section("expect")
    if expect.get("sha256") and expect["sha256"].lower() != out_sha:
        failures.append(f"sha256 {out_sha} != expected {expect['sha256']}")
    (out_dir / "records.json").write_text(json.dumps(res.records, indent=1), encoding="utf-8")

    status = "failed" if failures else "ok"
    code_files = [TOOLS / "tes4_plugin.py", TOOLS / "modlint.py", TOOLS / "merge-patch" / "patchlib.py",
                  TOOLS / "forge" / "records.py", Path(pp.__file__), TOOLS / "forge" / "kb" / "data" / "record_schemas.json",
                  TOOLS / "forge" / "kb" / "data" / "layout_overrides.json", Path(__file__),
                  TOOLS / "forge" / "script" / "compiler.py", TOOLS / "forge" / "script" / "commands.py"]
    log = {
        "spec": s.name, "kind": s.kind, "status": status,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)), "finished": buildlog.now(),
        "seconds": round(time.time() - t0, 2), "command": [Path(sys.argv[0]).name, *sys.argv[1:]],
        "vars": s.vars, "capabilities": caps, "tool_versions": buildlog.tool_versions(code_files),
        "inputs": {"spec": buildlog.file_entry(s.path), "ids": buildlog.file_entry(ids_file)},
        "outputs": {"plugin": buildlog.file_entry(plugin_path),
                    "records": buildlog.file_entry(out_dir / "records.json")},
        "masters": res.masters, "records": res.records,
        "checks": {"roundtrip": rt, "lint": {"summary": lint["summary"], "issues": lint["issues"][:50]} if lint else None},
        "warnings": warnings, "failures": failures,
    }
    if a.package and status == "ok":
        from forge.package import make_zip
        log["outputs"]["package"] = buildlog.file_entry(make_zip(s, out_dir, plugin_path, log))
    log_path = buildlog.write(out_dir, log)
    summary = {"status": status, "plugin": str(plugin_path), "sha256": out_sha, "masters": res.masters,
               "records": res.records, "ids_file": str(ids_file), "ids_changed": res.ids_changed,
               "warnings": warnings, "failures": failures, "build_log": str(log_path)}
    text = [f"build {s.name}: {status.upper()}  ({log['seconds']}s)",
            f"  plugin  {plugin_path}", f"  sha256  {out_sha}", f"  masters {', '.join(res.masters) or '-'}"]
    text += [f"  record  {r['sig']} {r['edid']}  {s.output_plugin}:{r['objid']}" for r in res.records]
    text.append(f"  round-trip {rt['subrecords']} subrecords, {rt['mismatches']} mismatches")
    text.append(f"  lint    {(lint['summary'] or 'no issues') if lint else 'skipped'}")
    if res.ids_changed:
        text.append(f"  ids     new FormIDs written to {ids_file} (commit it; IDs are permanent)")
    text += [f"  warn    {w}" for w in warnings] + [f"  FAIL    {f}" for f in failures]
    if "package" in log["outputs"]:
        text.append(f"  package {log['outputs']['package']['path']}")
    text.append(f"  log     {log_path}")
    _print(summary, a.json, "\n".join(text))
    return 0 if status == "ok" else 2


def _build_merge_patch(s, out_dir: Path, a, t0: float, caps) -> int:
    from forge.providers import merge_patch as mpp
    import modlint

    mp = s.section("merge_patch")
    cfg, cfg_path = specmod.merge_config(s)
    explicit = [s.resolve(p) for p in mp.get("new_mod_paths") or []]
    # build_cfg.json may still list paths from the machine it was written on; skip those
    stale = [p for p in cfg.get("extra_paths", []) if not Path(p).is_file()]
    cfg["extra_paths"] = [p for p in cfg.get("extra_paths", []) if Path(p).is_file()]
    searched, problems = _search_new_mods(s, cfg, explicit)
    if problems:
        print("error: " + "\n  ".join(problems), file=sys.stderr)
        return 1
    inp = mpp.MergeInputs(
        output_name=s.output_plugin,
        vanilla=s.resolve(mp["vanilla"]),
        installed_dir=s.resolve(mp["installed_dir"]),
        plugins_txt=s.resolve(mp["plugins_txt"]),
        cfg=cfg,
        new_mod_paths=explicit + [Path(p) for p in cfg.get("extra_paths", [])] + searched,
        extra_plugins={k: s.resolve(v) for k, v in (mp.get("extra_plugins") or {}).items()},
        insert_after=dict(mp.get("insert_after") or {}),
        author=mp.get("author", "Claude for Yuri"),
    )
    for f in (inp.vanilla, inp.plugins_txt):
        if not f.is_file():
            print(f"error: not found: {f}", file=sys.stderr)
            return 1
    try:
        res = mpp.build(inp, quiet=a.quiet or a.json)
    except mpp.MergeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = out_dir / s.output_plugin
    if any(plugin_path.resolve() == Path(p).resolve() for p in res.inputs_used.values()):
        print(f"error: output would overwrite an input: {plugin_path}", file=sys.stderr)
        return 1
    plugin_path.write_bytes(res.data)
    (out_dir / "load_order.json").write_text(json.dumps(res.load_order, indent=0), encoding="utf-8")
    (out_dir / "patch_report.json").write_text(json.dumps(
        {"stats": res.stats, "masters": res.masters, "world_edits": res.world_log, "report": res.report},
        indent=1), encoding="utf-8")

    # ---- checks
    warnings, failures = [f"build_cfg extra_paths entry not found, ignored: {p}" for p in stale], []
    rt = res.roundtrip
    if rt["mismatches"] or rt["parse_errors"]:
        failures.append(f"round-trip: {rt['mismatches']} mismatches, parse errors {rt['parse_errors']}")
    if res.stats.get("ORDER_WARN"):
        warnings.append(f"{res.stats['ORDER_WARN']} merged records have unusual subrecord order (see patch_report.json)")
    lint_data = s.resolve((s.section("lint") or {}).get("data") or mp["installed_dir"])
    lint = modlint.lint_plugin(plugin_path, lint_data, True, None)
    if lint["summary"].get("error"):
        failures.append("lint: " + "; ".join(i["message"] for i in lint["issues"] if i["level"] == "error"))
    if lint["summary"].get("warning"):
        warnings.append("lint: " + "; ".join(i["message"] for i in lint["issues"] if i["level"] == "warning"))
    out_sha = buildlog.sha256_bytes(res.data)
    expect = s.section("expect")
    checks = {"roundtrip": rt, "lint": {"summary": lint["summary"], "issues": lint["issues"][:50]}}
    if expect.get("sha256"):
        same = expect["sha256"].lower() == out_sha
        checks["expect_sha256"] = {"expected": expect["sha256"], "got": out_sha, "ok": same}
        if not same:
            failures.append(f"sha256 {out_sha} != expected {expect['sha256']}")
    if expect.get("same_records_as"):
        from forge.compare import compare
        ref = s.resolve(expect["same_records_as"])
        if ref.is_file():
            cmp_ = compare(ref, plugin_path)
            checks["same_records_as"] = cmp_
            if cmp_["verdict"].startswith("different"):
                failures.append(f"differs from {ref.name}: {cmp_['verdict']}")
        else:
            failures.append(f"expect.same_records_as not found: {ref}")

    status = "failed" if failures else "ok"
    code_files = [TOOLS / "tes4_plugin.py", TOOLS / "modlint.py", mpp.MERGE_DIR / "patchlib.py",
                  mpp.WORLD_EDITS, Path(mpp.__file__), Path(__file__)]
    inputs = {"spec": buildlog.file_entry(s.path),
              "plugins_txt": buildlog.file_entry(inp.plugins_txt),
              "plugins": {n: buildlog.file_entry(p) for n, p in res.inputs_used.items()}}
    if cfg_path:
        inputs["merge_config"] = buildlog.file_entry(cfg_path)
    for job in cfg.get("world_edits", []):
        if job.get("type") == "port_patch":
            inputs.setdefault("port_patches", {})[Path(job["path"]).name] = buildlog.file_entry(Path(job["path"]))
    log = {
        "spec": s.name, "kind": s.kind, "status": status,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)), "finished": buildlog.now(),
        "seconds": round(time.time() - t0, 2),
        "command": [Path(sys.argv[0]).name, *sys.argv[1:]],
        "vars": s.vars, "parameters": {"merge_config": cfg, "insert_after": inp.insert_after,
                                       "author": inp.author, "output_dir": str(out_dir)},
        "capabilities": caps, "tool_versions": buildlog.tool_versions(code_files),
        "inputs": inputs,
        "outputs": {"plugin": buildlog.file_entry(plugin_path),
                    "load_order": buildlog.file_entry(out_dir / "load_order.json"),
                    "patch_report": buildlog.file_entry(out_dir / "patch_report.json")},
        "masters": res.masters, "stats": res.stats, "world_edits": res.world_log,
        "checks": checks, "warnings": warnings, "failures": failures,
    }
    if a.package and status == "ok":
        from forge.package import make_zip
        z = make_zip(s, out_dir, plugin_path, log)
        log["outputs"]["package"] = buildlog.file_entry(z)
    log_path = buildlog.write(out_dir, log)

    summary = {"status": status, "plugin": str(plugin_path), "sha256": out_sha, "masters": len(res.masters),
               "stats": res.stats, "warnings": warnings, "failures": failures, "build_log": str(log_path)}
    text = [f"build {s.name}: {status.upper()}  ({log['seconds']}s)",
            f"  plugin  {plugin_path}", f"  sha256  {out_sha}",
            f"  masters {len(res.masters)}   records merged {sum(v for k, v in res.stats.items() if k.isupper() and k != 'ORDER_WARN')}",
            f"  round-trip {rt['checked']} checked, {rt['mismatches']} mismatches",
            f"  lint    {lint['summary'] or 'no issues'}"]
    text += [f"  warn    {w}" for w in warnings] + [f"  FAIL    {f}" for f in failures]
    if "package" in log["outputs"]:
        text.append(f"  package {log['outputs']['package']['path']}")
    text.append(f"  log     {log_path}")
    _print(summary, a.json, "\n".join(text))
    return 0 if status == "ok" else 2


def cmd_package(a) -> int:
    from forge.package import make_zip
    s, errs = _load_checked(a.spec, a.set)
    if errs:
        print("spec invalid:\n" + "\n".join(f"  {e}" for e in errs), file=sys.stderr)
        return 1
    out_dir = s.output_dir(Path(a.out) if a.out else None)
    log_path = out_dir / "build-log.json"
    plugin = out_dir / s.output_plugin
    if not log_path.is_file() or not plugin.is_file():
        print(f"error: no build in {out_dir}; run forge build first", file=sys.stderr)
        return 1
    log = json.loads(log_path.read_text(encoding="utf-8"))
    if log.get("status") != "ok":
        print("error: last build did not pass its checks; not packaging", file=sys.stderr)
        return 2
    if buildlog.sha256_file(plugin) != log["outputs"]["plugin"]["sha256"]:
        print("error: plugin changed since it was built (hash differs from build-log.json); rebuild",
              file=sys.stderr)
        return 2
    z = make_zip(s, out_dir, plugin, log)
    print(f"package {z}\n  sha256 {buildlog.sha256_file(z)}")
    return 0


def cmd_layout_check(argv: list[str]) -> int:
    """forge layout-check <plugin> [--data DIR] [--sig SPEL --sig MGEF] [--json]"""
    import argparse
    from forge import records as R
    ap = argparse.ArgumentParser(prog="forge layout-check",
                                 description="Decode and re-encode every subrecord of the given record types; "
                                             "pass = all identical and no struct leaves undecoded bytes.")
    ap.add_argument("plugin"); ap.add_argument("--data", type=Path)
    ap.add_argument("--sig", action="append"); ap.add_argument("--json", action="store_true")
    ap.add_argument("--all", action="store_true", help="every record type, with a per-type table")
    a = ap.parse_args(argv)
    path = (a.data / a.plugin) if a.data else Path(a.plugin)
    if not path.is_file():
        print(f"error: not found: {path}", file=sys.stderr)
        return 1
    if a.all:
        import tes4_plugin as tp
        sigs = {r.sig for _, r in tp.iter_records(path)}
        per = {}
        for sig in sorted(sigs):
            r = R.layout_check(path, {sig}, limit_examples=3)
            per[sig] = r
        bad = {k: v for k, v in per.items() if v["mismatch"] or v["with_tail"]}
        out = {"pass": not bad, "types": len(per), "failing_types": sorted(bad),
               "per_type": {k: {x: v[x] for x in ("records", "subrecords", "identical", "mismatch", "with_tail",
                                                  "struct", "array", "string", "raw")} for k, v in per.items()},
               "examples": {k: v["examples"] for k, v in bad.items()},
               "raw_by_sub": {k: v["raw_by_sub"] for k, v in per.items() if v["raw_by_sub"]}}
        lines = [f"layout-check {path.name} --all: {'PASS' if not bad else 'FAIL'}  ({len(per)} record types)",
                 f"  {'type':<5} {'records':>8} {'subs':>8} {'identical':>9} {'mismatch':>8} {'tail':>5} "
                 f"{'struct':>7} {'array':>6} {'string':>7} {'raw':>7}"]
        for k, v in per.items():
            lines.append(f"  {k:<5} {v['records']:>8} {v['subrecords']:>8} {v['identical']:>9} {v['mismatch']:>8} "
                         f"{v['with_tail']:>5} {v['struct']:>7} {v['array']:>6} {v['string']:>7} {v['raw']:>7}"
                         + ("  <-- FAIL" if k in bad else ""))
        raw_all = {}
        for k, v in per.items():
            for sub, n in v["raw_by_sub"].items():
                raw_all[f"{k}.{sub}"] = n
        if raw_all:
            lines.append("  most common undecoded (raw) subrecords - they round-trip, but fields aren't named yet:")
            for key, n in sorted(raw_all.items(), key=lambda x: -x[1])[:25]:
                lines.append(f"    {n:>9}  {key}")
        for k in sorted(bad):
            for e in per[k]["examples"][:3]:
                lines.append(f"  {'MISMATCH' if not e['ok'] else 'TAIL'} {e['record']} {e['sub']} ({e['size']} bytes): "
                             f"{json.dumps(e['decoded'])[:160]}")
        _print(out, a.json, "\n".join(lines))
        return 0 if not bad else 2
    sigs = {x.upper() for x in (a.sig or ["SPEL", "MGEF"])}
    res = R.layout_check(path, sigs)
    ok = res["mismatch"] == 0 and res["with_tail"] == 0 and res["records"] > 0
    res["pass"] = ok
    lines = [f"layout-check {path.name} {sorted(sigs)}: {'PASS' if ok else 'FAIL'}",
             f"  records {res['records']}  subrecords {res['subrecords']}  identical {res['identical']}  "
             f"mismatch {res['mismatch']}",
             f"  decoded as struct {res['struct']}, array {res['array']}, string {res['string']}, raw {res['raw']}  "
             f"(structs with leftover bytes: {res['with_tail']})"]
    for e in res["examples"][:10]:
        lines.append(f"  {'MISMATCH' if not e['ok'] else 'TAIL'} {e['record']} {e['sub']} ({e['size']} bytes): "
                     f"{json.dumps(e['decoded'])[:200]}")
    _print(res, a.json, "\n".join(lines))
    return 0 if ok else 2


def cmd_compare(a) -> int:
    from forge.compare import compare
    r = compare(a.a, a.b)
    lines = [f"{r['verdict']}", f"  a {r['a_sha256']}  {r['a']}", f"  b {r['b_sha256']}  {r['b']}"]
    if not r["byte_identical"]:
        lines.append(f"  records a={r['records_a']} b={r['records_b']}  only-a={r['only_in_a_count']} "
                     f"only-b={r['only_in_b_count']}  same order={r['same_order']}")
        if r["header_differences"]:
            lines.append("  header differs: " + ", ".join(r["header_differences"]))
    _print(r, a.json, "\n".join(lines))
    return 0 if not r["verdict"].startswith("different") else 2


# --------------------------------------------------------------------------- wrapped tools
def run_wrapped(cmd: str, args: list[str]) -> int:
    if cmd in MODLINT_CMDS:
        argv = [sys.executable, str(TOOLS / "modlint.py")]
        # modlint takes global options before the command; let them through in either position
        glob, rest, i = [], [], 0
        while i < len(args):
            if args[i] in ("--data", "--plugins-txt") and i + 1 < len(args):
                glob += args[i:i + 2]; i += 2; continue
            if args[i] == "--json":
                glob.append("--json"); i += 1; continue
            rest.append(args[i]); i += 1
        return subprocess.call(argv + glob + [cmd] + rest)
    return subprocess.call(WRAPPED[cmd] + args, cwd=str(TOOLS) if cmd == "asset" else None)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and (argv[0] in MODLINT_CMDS or argv[0] in WRAPPED):
        return run_wrapped(argv[0], argv[1:])
    if argv and argv[0] == "layout-check":
        return cmd_layout_check(argv[1:])
    if argv and argv[0] == "dump":
        from forge.dump import main as dump_main
        return dump_main(argv[1:])
    if argv and argv[0] == "script-check":
        from forge.script.check import main as check_main
        return check_main(argv[1:])
    if argv and argv[0] == "script-decode":
        from forge.script.survey import main as decode_main
        return decode_main(argv[1:])
    if argv and argv[0] == "kb":
        from forge.kb.cli import main as kb_main
        return kb_main(argv[1:])
    ap = argparse.ArgumentParser(prog="forge", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"forge {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("caps"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_caps)
    p = sub.add_parser("spec"); ss = p.add_subparsers(dest="spec_cmd", required=True)
    c = ss.add_parser("check"); c.add_argument("spec"); c.add_argument("--set", action="append")
    c.add_argument("--json", action="store_true"); c.set_defaults(fn=cmd_spec_check)
    p = sub.add_parser("new"); p.add_argument("prompt"); p.add_argument("--name")
    p.add_argument("--dir", default=str(ROOT / "specs")); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("build"); p.add_argument("spec"); p.add_argument("--set", action="append")
    p.add_argument("--out"); p.add_argument("--package", action="store_true")
    p.add_argument("--quiet", action="store_true"); p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("package"); p.add_argument("spec"); p.add_argument("--set", action="append")
    p.add_argument("--out"); p.set_defaults(fn=cmd_package)
    p = sub.add_parser("compare"); p.add_argument("a"); p.add_argument("b")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_compare)
    sub.add_parser("kb", help="knowledge store: forge kb --help")
    sub.add_parser("dump", help="decode a record's subrecords: forge dump <plugin> <EDID|FormID>")
    sub.add_parser("layout-check", help="re-encode every SPEL/MGEF (or --sig X) byte for byte")
    sub.add_parser("script-check", help="compile every script and compare: forge script-check <plugin|corpus>")
    sub.add_parser("script-decode", help="decompile scripts: forge script-decode <plugin|corpus> [--show EDID]")
    from playtest import cli as playtest_cli
    playtest_cli.register(sub)
    for name in sorted(MODLINT_CMDS | set(WRAPPED)):
        sub.add_parser(name, help="wrapped tool; arguments pass through")
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except specmod.SpecError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
