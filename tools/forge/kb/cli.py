"""`forge kb ...` commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from forge.kb import build as kbuild, query as q

USAGE = """forge kb: the knowledge store (forge-kb.sqlite)

  build [--db F] [--vanilla F] [--commands F]   build the DB and print counts per table
  query "<text>" [--kind K ...] [--limit N]     ranked full-text search over everything
  func <name|alias>                             OBSE/vanilla function: params, version, notes
  record <SIG>                                  record layout: subrecords, FormID fields, required
  form <EditorID | FormID | Plugin.esp:FormID>  vanilla form lookup (needs the PC export)
  forms --sig <SIG>                             every vanilla record of one type (e.g. WTHR)
  technique <keyword>                           research-mod techniques
  crash [keyword]                               known crash/hang signatures
  stats                                         build info and counts
  export-vanilla --data <Data> [--out F]        PC: write vanilla_index.jsonl (git-ignored)
  export-commands --exe <Oblivion.exe> [--out F] PC: write vanilla_commands.jsonl (git-ignored)
  refresh-sources --xobse D --xedit F --vim F   dev: regenerate kb/data/*.json from upstream
Add --json to any lookup for agent-readable output. Every row has source + confidence;
HYPOTHESIS rows are not facts."""


def _out(obj, as_json: bool, text: str) -> None:
    print(json.dumps(obj, indent=1, default=str, ensure_ascii=False) if as_json else text)


def _conf(c) -> str:
    return "HYPOTHESIS (unverified)" if c == "HYPOTHESIS" else (c or "?")


def _fmt_func(f: dict) -> str:
    ps = ", ".join(f"{p['name']}:{p['type']}{'?' if p['optional'] else ''}" for p in f["params"]) or "-"
    lines = [f"{f['name']}" + (f"  (alias {f['alias']})" if f["alias"] else "") +
             f"  [{f['origin']}{' v' + str(f['obse_version']) if f['obse_version'] else ''}]  {_conf(f['confidence'])}",
             f"  params: {ps}",
             f"  returns: {f['return_type']}   reference required: {'?' if f['ref_required'] is None else bool(f['ref_required'])}"]
    if f.get("condition_index") is not None:
        lines.append(f"  condition function index {f['condition_index']}")
    if f["summary"]:
        lines.append(f"  {f['summary']}")
    if f["params_note"]:
        lines.append(f"  params: {f['params_note']}")
    if f["example"]:
        lines.append("  example:\n    " + f["example"].replace("\n", "\n    "))
    lines.append(f"  source: {f['source']}\n  doc: {f['url']}")
    if f["obse_version"] == 8:
        lines.append("  note: v8 means 'first OBSE release table' (v0008 or earlier).")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]

    def opt(name, default=None):
        if name in rest:
            i = rest.index(name)
            v = rest[i + 1] if i + 1 < len(rest) else default
            del rest[i:i + 2]
            return v
        return default

    def opts(name):
        vals = []
        while name in rest:
            vals.append(opt(name))
        return vals

    db = opt("--db")
    try:
        if cmd == "build":
            van = opt("--vanilla", str(kbuild.DEFAULT_VANILLA))
            com = opt("--commands", str(kbuild.DEFAULT_COMMANDS))
            counts = kbuild.build(Path(db) if db else kbuild.DEFAULT_DB, Path(van), Path(com))
            text = "built " + str(Path(db) if db else kbuild.DEFAULT_DB) + "\n" + "\n".join(
                f"  {k:<18} {v}" for k, v in counts.items())
            if not counts["vanilla_forms"]:
                text += "\n  (no vanilla_index.jsonl: vanilla form lookups need the PC export)"
            _out(counts, as_json, text)
            return 0
        if cmd == "query":
            kinds = opts("--kind")
            limit = int(opt("--limit", "10"))
            res = q.search(" ".join(rest), limit, kinds or None, db)
            text = "\n".join(f"{i + 1:>2}. [{r['kind']}] {r['title']}  ({_conf(r['confidence'])}, score {r['score']})\n"
                             f"    {r['detail'].get('summary') or r['snippet']}\n    source: {r['source']}"
                             for i, r in enumerate(res)) or "no results"
            _out(res, as_json, text)
            return 0 if res else 2
        if cmd == "func":
            f = q.func(rest[0], db)
            _out(f, as_json, _fmt_func(f) if f else f"no function named {rest[0]}")
            return 0 if f else 2
        if cmd == "record":
            r = q.record(rest[0], db)
            if not r:
                _out(None, as_json, f"no record type {rest[0]}")
                return 2
            lines = [f"{r['sig']} {r['name']}  ({_conf(r['confidence'])})  source: {r['source']}",
                     f"  FormID subrecords: {', '.join(r['formid_subrecords']) or '-'}",
                     f"  required: {', '.join(r['required_subrecords']) or '-'}"]
            for s in r["subrecords"]:
                flags = "".join(x for x, on in (("R", s["required"]), ("*", s["repeating"]), ("F", s["formid"])) if on)
                lines.append(f"  {s['ord']:>2} {s['sub_sig']} {flags:<3} {s['kind']:<8} {s['name']}"
                             + (f" -> {s['formid_targets']}" if s["formid_targets"] else "")
                             + (f"  [{s['grp']}]" if s["grp"] else ""))
                for f in s["fields"]:
                    lines.append(f"       +{f['offset'] if f['offset'] is not None else '?'} {f['name']} "
                                 f"{f['type']}{'/' + str(f['size']) if f['size'] else ''}{' FORMID' if f['formid'] else ''}")
            if r.get("note"):
                lines.append("  note: " + r["note"])
            lines.append("  flags: R required, * repeating, F holds a FormID")
            _out(r, as_json, "\n".join(lines))
            return 0
        if cmd == "form":
            rows = q.form(" ".join(rest), db)
            _out(rows, as_json, "\n".join(f"{r['plugin']}:{r['formid']} {r['sig']} {r['edid']} \"{r['full']}\""
                                          + (" (override)" if r["override"] else "") for r in rows) or "not found")
            return 0 if rows else 2
        if cmd == "forms":
            rows = q.forms_of_type(opt("--sig") or rest[0], db)
            _out(rows, as_json, "\n".join(f"{r['plugin']}:{r['formid']} {r['edid']} {r['full']}" for r in rows)
                 + f"\n{len(rows)} records")
            return 0 if rows else 2
        if cmd == "technique":
            rows = q.technique(" ".join(rest), db)
            _out(rows, as_json, "\n".join(
                f"{r['specimen']}" + (f" (Nexus {r['nexus_id']})" if r["nexus_id"] else "") +
                f"  [{r['permission']}]\n  {r['technique']}\n  functions: {r['functions_used'] or '-'}"
                for r in rows) or "no techniques match")
            return 0 if rows else 2
        if cmd == "crash":
            rows = q.crash(" ".join(rest), db)
            _out(rows, as_json, "\n".join(f"{r['title']}  ({_conf(r['confidence'])})\n  symptoms: {r['symptoms']}\n"
                                          f"  cause: {r['cause']}\n  fix: {r['fix']}\n  source: {r['source']}"
                                          for r in rows) or "no match")
            return 0 if rows else 2
        if cmd == "stats":
            s = q.stats(db)
            _out(s, as_json, "\n".join(f"{k}: {v}" for k, v in s.items() if k != "provenance"))
            return 0
        if cmd == "export-vanilla":
            from forge.kb.export import export_vanilla
            out = Path(opt("--out", str(kbuild.DEFAULT_VANILLA)))
            counts = export_vanilla(Path(opt("--data")), out)
            _out(counts, as_json, f"wrote {out}\n" + "\n".join(f"  {k}: {v}" for k, v in counts.items()))
            return 0 if any(isinstance(v, int) and v for v in counts.values()) else 1
        if cmd == "export-commands":
            from forge.kb.export import export_commands
            out = Path(opt("--out", str(kbuild.DEFAULT_COMMANDS)))
            counts = export_commands(Path(opt("--exe")), out)
            _out(counts, as_json, f"wrote {out}\n" + "\n".join(f"  {k}: {v}" for k, v in counts.items()))
            return 0
        if cmd == "refresh-sources":
            from forge.kb.sources.refresh import refresh
            x, e, v = opt("--xobse"), opt("--xedit"), opt("--vim")
            counts = refresh(Path(x) if x else None, Path(e) if e else None, Path(v) if v else None)
            _out(counts, as_json, "\n".join(f"  {k}: {v}" for k, v in counts.items()))
            return 0
    except q.KBError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"unknown kb command {cmd!r}\n\n{USAGE}", file=sys.stderr)
    return 1
