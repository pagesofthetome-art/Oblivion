#!/usr/bin/env python3
"""modlint - read-only Oblivion plugin inspector, linter and conflict checker.

Designed for AI agents and modders. Never modifies any file in Data\\.

Commands
  info        <plugin>                      header, masters, record counts
  records     <plugin> [--type SIG] [--overrides|--new] [--limit N]
  lint        <plugin> [--no-itm]           crash/compat risks in one plugin
  conflicts   [plugins...] [--active]       records overridden by 2+ plugins, who wins,
                                            which edits are lost, how to resolve
  load-order                                effective load order + master problems
  find        <EditorID|FormID> [--active]  which plugins define/override a record

Plugins are looked up in --data (default: ..\\Oblivion\\Data next to this tool).
FormIDs are printed load-order independent as  Owner.esp:XXXXXX  plus the
file-relative 8-digit ID in brackets.

Add --json to any command for machine-readable output.
Exit code: 0 ok, 1 usage/IO error, 2 lint found errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tes4_plugin as tp  # noqa: E402

TOOL_DIR = Path(__file__).resolve().parent
from gamepaths import data_dir  # noqa: E402

DEFAULT_DATA = data_dir()
BASE_GAME_FILES = {
    "oblivion.esm", "dlcshiveringisles.esp", "knights.esp", "dlchorsearmor.esp",
    "dlcmehrunesrazor.esp", "dlcvilelair.esp", "dlcfrostcrag.esp", "dlcbattlehorncastle.esp",
    "dlcspelltomes.esp", "dlcthievesden.esp", "dlcorrery.esp",
}

# Syntax that only compiles with OBSE/xOBSE loaded in the CS (obse_loader -editor).
OBSE_STATEMENTS = re.compile(
    r"^\s*(let\s+\w|while\s*\(|while\s+\w|foreach\s+\w|loop\s*$|break\s*$|continue\s*$|"
    r"(else)?if\s+eval\s*\(|eval\s*\(|call\s+\w|setfunctionvalue\b|begin\s+function\b)",
    re.IGNORECASE | re.MULTILINE,
)
OBSE_FUNCTIONS = re.compile(
    r"\b(sv_\w+|ar_\w+|getmodindex|ismodloaded|getformfrommod|setEventHandler|getobseversion|"
    r"isplugininstalled|getgameloaded|getgamerestarted|printc|messageex|messageboxex|con_\w+|"
    r"getbaseobject|getequippedobject|isformvalid|tostring|tonumber|getnumitems|getinventoryobject)\b",
    re.IGNORECASE,
)


def uses_obse(src: str) -> bool:
    """Detect xOBSE-only syntax, ignoring ';' comments and vanilla words used as variable names."""
    code = "\n".join(line.split(";", 1)[0] for line in src.splitlines())
    return bool(OBSE_STATEMENTS.search(code) or OBSE_FUNCTIONS.search(code))


ADVICE = {
    "LVLI": ("merge", "Leveled list: merge entries with Wrye Bash Bashed Patch (tag Delev/Relev) "
                      "or a manual xEdit merged patch. Never let one list silently win."),
    "LVLC": ("merge", "Leveled creature list: merge via Bashed Patch (Delev/Relev) or xEdit patch."),
    "LVSP": ("merge", "Leveled spell list: merge via Bashed Patch or xEdit patch."),
    "NPC_": ("patch", "Actor: Bashed Patch tags (Actors.AIData, Actors.Stats, Factions, Invent, "
                      "NPC.Race, NpcFaces, Names...) or forward each mod's intended fields in an xEdit patch."),
    "CREA": ("patch", "Creature: Bashed Patch (Actors.*, Invent, Factions) or xEdit patch."),
    "CONT": ("patch", "Container inventory: Bashed Patch 'Invent' tag or xEdit patch."),
    "CELL": ("patch", "Cell header (name, lighting, water, ownership, flags, music, climate): "
                      "Bashed Patch C.* tags or xEdit patch forwarding each change."),
    "LAND": ("critical", "Landscape: cannot be merged automatically; loser's terrain edits vanish "
                         "(seams, floating/buried objects). Needs a hand-made compatibility patch."),
    "PGRD": ("critical", "Path grid: last one wins wholesale; NPCs walk into new objects or get stuck. "
                         "Regenerate/merge the pathgrid in the CS for the combined layout."),
    "SCPT": ("critical", "Script source replaced: only one version runs. Variable order changes break "
                         "saves and any mod that reads these variables. Reconcile by hand and recompile in the CS."),
    "QUST": ("critical", "Quest: stages/targets/script/flags from the loser are lost. Patch by hand."),
    "DIAL": ("low", "Topic header: usually benign (INFOs are merged per topic). Check INFO conflicts."),
    "INFO": ("patch", "Dialogue response: conditions/result scripts from the loser are lost. Patch by hand."),
    "REFR": ("patch", "Placed object: position/enable/ownership/lock from the loser is lost. "
                      "Check that both mods do not rely on it (e.g. one moved it, one disabled it)."),
    "ACHR": ("patch", "Placed NPC: same as REFR; also check persistent-ref and enable-parent use."),
    "ACRE": ("patch", "Placed creature: same as REFR."),
    "WRLD": ("critical", "Worldspace header: map, parent, music, water defaults. Patch by hand."),
    "RACE": ("patch", "Race: Bashed Patch tags (R.*, Hair, Eyes, Body-*, Voice-*) or xEdit patch."),
    "GMST": ("low", "Game setting: last value wins. Confirm the intended value."),
    "GLOB": ("low", "Global: last value wins. Confirm the intended value."),
    "REGN": ("patch", "Region: weather/sounds/objects lists. Patch by hand."),
}
DEFAULT_ADVICE = ("patch", "Last loaded wins (Rule of One). Forward the edits you need into a patch plugin.")


# --------------------------------------------------------------------------- helpers
def die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def resolve_plugin(name: str, data: Path) -> Path:
    p = Path(name)
    if p.is_file():
        return p
    q = data / name
    if q.is_file():
        return q
    # case-insensitive lookup (Windows paths copied from Linux tools, etc.)
    if data.is_dir():
        for f in data.iterdir():
            if f.name.casefold() == Path(name).name.casefold():
                return f
    die(f"plugin not found: {name} (looked in {data})")


def data_plugins(data: Path) -> dict[str, Path]:
    if not data.is_dir():
        return {}
    return {f.name.casefold(): f for f in data.iterdir()
            if f.is_file() and f.suffix.lower() in (".esm", ".esp")}


def plugins_txt_path() -> Path | None:
    la = os.environ.get("LOCALAPPDATA")
    if la:
        p = Path(la) / "Oblivion" / "Plugins.txt"
        if p.is_file():
            return p
    return None


def read_active(plugins_txt: Path | None) -> list[str]:
    if not plugins_txt or not plugins_txt.is_file():
        return []
    out = []
    for line in plugins_txt.read_text("cp1252", "replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def effective_load_order(data: Path, plugins_txt: Path | None) -> tuple[list[Path], list[str], list[str]]:
    """Oblivion rule: active plugins sorted ESM-flagged first, then by file modified time.

    Returns (ordered paths, active-but-missing names, notes).
    """
    files = data_plugins(data)
    notes = []
    active = read_active(plugins_txt)
    if not active:
        notes.append("No Plugins.txt found/readable - treating every plugin in Data as active.")
        active = [f.name for f in files.values()]
    missing = [a for a in active if a.casefold() not in files]
    present = [files[a.casefold()] for a in dict.fromkeys(a for a in active) if a.casefold() in files]
    if not any(p.name.casefold() == "oblivion.esm" for p in present) and "oblivion.esm" in files:
        present.insert(0, files["oblivion.esm"])
        notes.append("Oblivion.esm is always loaded first even if not listed.")

    def key(p: Path):
        try:
            esm = tp.read_header(p).is_esm_flag
        except Exception:
            esm = p.suffix.lower() == ".esm"
        return (0 if p.name.casefold() == "oblivion.esm" else 1, 0 if esm else 1, p.stat().st_mtime, p.name.casefold())

    ordered = sorted(present, key=key)
    times = Counter(int(p.stat().st_mtime) for p in ordered)
    ties = [p.name for p in ordered if times[int(p.stat().st_mtime)] > 1]
    if ties:
        notes.append("Plugins with identical timestamps have an undefined relative order: " + ", ".join(ties)
                     + ". Fix with Wrye Bash/LOOT (they set distinct timestamps).")
    return ordered, missing, notes


def fid_str(plugin: tp.Plugin, fid: int) -> str:
    owner = plugin.owner_of(fid)
    if owner is None:
        return f"INVALID[{fid:08X}]"
    return f"{owner}:{fid & 0xFFFFFF:06X} [{fid:08X}]"


def emit(obj, as_json: bool, text: str):
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(text)


def norm_data(rec: tp.Record) -> bytes:
    try:
        return rec.data
    except Exception:
        return rec.raw


def sub_digest(rec: tp.Record) -> dict[str, str]:
    """Map 'SIG#n' -> short hash of that subrecord, for field-level diffs."""
    out: dict[str, str] = {}
    seen: Counter = Counter()
    try:
        subs = rec.subrecords()
    except Exception:
        return out
    for s in subs:
        seen[s.sig] += 1
        k = s.sig if seen[s.sig] == 1 else f"{s.sig}#{seen[s.sig]}"
        out[k] = hashlib.blake2b(s.data, digest_size=6).hexdigest()
    return out


def collapse(keys) -> list[str]:
    return sorted({k.split("#")[0] for k in keys})


# --------------------------------------------------------------------------- info / records
def cmd_info(a):
    path = resolve_plugin(a.plugin, a.data)
    p = tp.load(path)
    counts = Counter(r.sig for r in p.records)
    overrides = sum(1 for r in p.records if p.is_override(r))
    obj = {
        "file": p.name, "esm_flag": p.is_esm_flag, "version": p.version, "author": p.author,
        "description": p.description, "masters": p.masters, "records": len(p.records),
        "new_records": len(p.records) - overrides, "override_records": overrides,
        "next_object_id": f"{p.next_object_id:06X}", "by_type": dict(counts.most_common()),
        "parse_errors": p.errors,
    }
    lines = [f"{p.name}  ({'ESM flag' if p.is_esm_flag else 'plugin'}, HEDR {p.version})",
             f"  author: {p.author or '-'}", f"  description: {p.description or '-'}",
             f"  masters: {', '.join(p.masters) or '(none)'}",
             f"  records: {len(p.records)}  new: {obj['new_records']}  overrides: {overrides}",
             "  by type: " + ", ".join(f"{k} {v}" for k, v in counts.most_common())]
    if p.errors:
        lines.append("  PARSE ERRORS: " + "; ".join(p.errors))
    emit(obj, a.json, "\n".join(lines))


def cmd_records(a):
    path = resolve_plugin(a.plugin, a.data)
    want = {a.type.upper().ljust(4, "_")[:4]} if a.type else None
    if a.type and a.type.upper() == "NPC":
        want = {"NPC_"}
    p = tp.load(path, want)
    rows = []
    for r in p.records:
        ov = p.is_override(r)
        if a.overrides and not ov or a.new and ov:
            continue
        rows.append({"sig": r.sig, "formid": fid_str(p, r.form_id), "edid": r.editor_id,
                     "name": r.full_name, "override": ov, "deleted": r.is_deleted,
                     "parent": fid_str(p, r.parent) if r.parent else None})
        if a.limit and len(rows) >= a.limit:
            break
    text = "\n".join(f"{x['sig']} {x['formid']:<34} {'OVR' if x['override'] else 'NEW'}"
                     f"{' DEL' if x['deleted'] else ''}  {x['edid']}  {x['name']}" for x in rows)
    emit(rows, a.json, text or "(no matching records)")


# --------------------------------------------------------------------------- lint
def lint_plugin(path: Path, data: Path, check_itm: bool = True, order: list[Path] | None = None,
                full_list: bool = False) -> dict:
    p = tp.load(path)
    issues: list[dict] = []

    def add(level, code, msg, **kw):
        issues.append({"level": level, "code": code, "message": msg, **kw})

    for e in p.errors:
        add("error", "CORRUPT", e)
    files = data_plugins(data)
    for m in p.masters:
        mp = files.get(m.casefold())
        if not mp:
            add("error", "MISSING_MASTER", f"Master {m} is not in Data - the game will crash on load (CTD).")
        elif mp.suffix.lower() == ".esp":
            try:
                if not tp.read_header(mp).is_esm_flag:
                    add("warning", "ESP_MASTER", f"Master {m} is an .esp without the ESM flag. The game accepts it, "
                        "but the vanilla CS cannot load this plugin with it as master (use CSE, or flag it ESM "
                        "temporarily in TES4Edit while editing).")
            except Exception:
                pass
    if order:
        idx = {q.name.casefold(): i for i, q in enumerate(order)}
        me = idx.get(p.name.casefold())
        for m in p.masters:
            mi = idx.get(m.casefold())
            if me is not None and mi is None and m.casefold() in files:
                add("error", "MASTER_INACTIVE", f"Master {m} is installed but not active.")
            elif me is not None and mi is not None and mi > me:
                add("error", "MASTER_AFTER_PLUGIN", f"Master {m} loads AFTER {p.name}; fix load order.")
    if p.is_esm_flag and path.suffix.lower() == ".esp":
        add("info", "ESM_FLAGGED_ESP", "This .esp has the ESM flag set (loads with masters). Intentional?")

    edids: dict[str, list[str]] = defaultdict(list)
    overrides_by_owner: dict[str, dict[int, tp.Record]] = defaultdict(dict)
    obse_scripts = []
    for r in p.records:
        owner = p.owner_of(r.form_id)
        if owner is None:
            add("error", "INVALID_FORMID", f"{r.sig} {r.form_id:08X} uses mod index {r.form_id >> 24:02X} but the "
                f"file has only {len(p.masters)} masters (record points at a plugin that is not a master).",
                formid=f"{r.form_id:08X}")
            continue
        new = owner == p.name
        if r.is_deleted:
            if r.sig in tp.PLACED_TYPES:
                add("error", "UDR", f"Deleted reference {r.sig} {fid_str(p, r.form_id)}. Deleted refs crash the game "
                    "when another mod or script touches them. Fix: TES4Edit 'Undelete and Disable References' (QAC).",
                    formid=fid_str(p, r.form_id))
            elif not new:
                add("error", "DELETED_RECORD", f"Deletes master record {r.sig} {fid_str(p, r.form_id)}. Anything that "
                    "references it (scripts, lists, other mods) may CTD. Prefer disabling/emptying it instead.",
                    formid=fid_str(p, r.form_id))
            continue
        if new and r.sig not in ("CELL",):
            eid = r.editor_id
            if eid:
                edids[eid.casefold()].append(fid_str(p, r.form_id))
        if not new:
            overrides_by_owner[owner][r.form_id] = r
        if r.sig == "SCPT":
            subs = {s.sig: s.data for s in r.subrecords()}
            src = tp.zstring(subs.get("SCTX", b""))
            if src and not subs.get("SCDA"):
                add("error", "SCRIPT_NOT_COMPILED", f"Script {r.editor_id} has source but no compiled data (SCDA). "
                    "It will do nothing in game. Recompile in the CS (launched via obse_loader -editor if it uses OBSE).",
                    formid=fid_str(p, r.form_id))
            if src and uses_obse(src):
                obse_scripts.append(r.editor_id)
    for eid, ids in edids.items():
        if len(ids) > 1:
            add("error", "DUPLICATE_EDID", f"EditorID '{eid}' used by {len(ids)} records: {', '.join(ids)}. "
                "Scripts resolve EditorIDs at compile time - ambiguous.")
    if obse_scripts:
        add("info", "REQUIRES_OBSE", f"{len(obse_scripts)} script(s) appear to use OBSE/xOBSE syntax "
            f"(e.g. {', '.join(obse_scripts[:5])}). Declare xOBSE as a requirement.")

    itm_count = 0
    if check_itm:
        for owner, recs in overrides_by_owner.items():
            mp = files.get(owner.casefold())
            if not mp:
                continue
            try:
                mh = tp.read_header(mp)
            except Exception:
                continue
            own_idx = len(mh.masters)
            # map our file-relative id -> owner's file-relative id
            want = {(own_idx << 24) | (fid & 0xFFFFFF): fid for fid in recs}
            for _, mr in tp.iter_records(mp, want_ids=set(want)):
                ours = recs[want[mr.form_id]]
                if ours.sig == mr.sig and norm_data(ours) == norm_data(mr) and \
                        (ours.flags & ~tp.FLAG_COMPRESSED) == (mr.flags & ~tp.FLAG_COMPRESSED):
                    itm_count += 1
                    if itm_count <= 200:
                        add("warning", "ITM", f"Identical-to-master {ours.sig} {fid_str(p, ours.form_id)} "
                            f"{ours.editor_id}. Harmless alone but silently reverts other mods' edits. "
                            "Fix: TES4Edit Remove ITMs (QAC).", formid=fid_str(p, ours.form_id))
        if itm_count > 200:
            add("warning", "ITM", f"... {itm_count - 200} more ITMs not listed.")
    levels = Counter(i["level"] for i in issues)
    by_code = Counter(i["code"] for i in issues)
    shown: Counter = Counter()
    capped = []
    for i in issues:
        shown[i["code"]] += 1
        if shown[i["code"]] <= 15:
            capped.append(i)
        elif shown[i["code"]] == 16:
            capped.append({"level": i["level"], "code": i["code"],
                           "message": f"... {by_code[i['code']] - 15} more {i['code']} issues (use --json for all)"})
    if not full_list:
        issues = capped
    return {"file": p.name, "masters": p.masters, "records": len(p.records), "itm_count": itm_count,
            "summary": dict(levels), "counts_by_code": dict(by_code), "issues": issues}


def cmd_lint(a):
    path = resolve_plugin(a.plugin, a.data)
    order, _, _ = effective_load_order(a.data, a.plugins_txt)
    res = lint_plugin(path, a.data, not a.no_itm, order, full_list=a.json)
    if path.name.casefold() in BASE_GAME_FILES:
        res["note"] = ("Official Bethesda file: ITMs/UDRs in official DLC are normally cleaned by users with "
                       "TES4Edit QAC; do not edit it otherwise.")
    lines = [f"lint {res['file']}: {res['records']} records, "
             + ", ".join(f"{v} {k}" for k, v in res["summary"].items()) if res["summary"] else
             f"lint {res['file']}: {res['records']} records, no issues found"]
    for i in res["issues"]:
        lines.append(f"  [{i['level'].upper():7}] {i['code']}: {i['message']}")
    if res.get("note"):
        lines.append("  note: " + res["note"])
    emit(res, a.json, "\n".join(lines))
    if res["summary"].get("error"):
        raise SystemExit(2)


# --------------------------------------------------------------------------- conflicts
def collect_conflicts(paths: list[Path], data: Path) -> dict:
    """Find records overridden by 2+ plugins in `paths` (given in load order)."""
    order_names = [p.name for p in paths]
    entries: dict[tuple, list[dict]] = defaultdict(list)
    headers = {}
    deleted_new: dict[tuple, str] = {}
    for path in paths:
        hdr = None
        for plugin, rec in tp.iter_records(path):
            hdr = plugin
            key = plugin.global_key(rec.form_id)
            if key is None:
                continue
            if key[0] == plugin.name.casefold():
                if rec.is_deleted:
                    deleted_new[key] = plugin.name
                continue
            entries[key].append({"plugin": plugin.name, "sig": rec.sig, "edid": rec.editor_id,
                                 "deleted": rec.is_deleted, "rec": rec, "parent": rec.parent,
                                 "hdr": plugin})
        headers[path.name] = hdr or tp.read_header(path)

    files = data_plugins(data)
    conflicts = []
    by_owner: dict[str, dict[int, tuple]] = defaultdict(dict)
    for key, ents in entries.items():
        if len(ents) >= 2:
            by_owner[key[0]][key[1]] = key
    origin: dict[tuple, tp.Record] = {}
    for owner, ids in by_owner.items():
        mp = files.get(owner) or next((p for p in paths if p.name.casefold() == owner), None)
        if not mp:
            continue
        try:
            mh = tp.read_header(mp)
        except Exception:
            continue
        own = len(mh.masters) << 24
        want = {own | obj: key for obj, key in ids.items()}
        for _, r in tp.iter_records(mp, want_ids=set(want)):
            origin[want[r.form_id]] = r

    for key, ents in entries.items():
        if len(ents) < 2:
            continue
        sig = ents[0]["sig"]
        base = origin.get(key)
        base_d = sub_digest(base) if base else {}
        digests = [sub_digest(e["rec"]) for e in ents]
        datas = [norm_data(e["rec"]) for e in ents]
        winner = ents[-1]
        changed = []
        for e, d in zip(ents, digests):
            ch = {k for k in set(d) | set(base_d) if d.get(k) != base_d.get(k)} if base else set(d)
            changed.append(ch)
        lost = []
        win_d = digests[-1]
        for e, d, ch in zip(ents[:-1], digests[:-1], changed[:-1]):
            gone = [k for k in ch if win_d.get(k) != d.get(k)]
            if gone and not e["deleted"]:
                lost.append({"plugin": e["plugin"], "fields": collapse(gone)})
        itms = [e["plugin"] for e, ch in zip(ents, changed) if base and not ch and not e["deleted"]]
        identical = len(set(datas)) == 1
        if identical:
            severity = "benign"
        elif not lost:
            severity = "benign"  # winner already contains every loser edit (or losers are ITM)
        else:
            severity = ADVICE.get(sig, DEFAULT_ADVICE)[0]
        warn = []
        if any(e["deleted"] for e in ents[:-1]) or key in deleted_new:
            warn.append("A plugin deletes this record while another overrides it - likely CTD. Undelete+disable instead.")
        if winner["deleted"]:
            warn.append(f"Winning override from {winner['plugin']} DELETES the record.")
        hdr0 = ents[0]["hdr"]
        conflicts.append({
            "record": f"{sig} {hdr0.masters[ents[0]['rec'].form_id >> 24] if (ents[0]['rec'].form_id >> 24) < len(hdr0.masters) else hdr0.name}:{key[1]:06X}",
            "sig": sig, "edid": winner["edid"] or (base.editor_id if base else ""),
            "origin": key[0], "overridden_by": [e["plugin"] for e in ents], "winner": winner["plugin"],
            "severity": severity, "lost_edits": lost, "itm_in": itms,
            "advice": ADVICE.get(sig, DEFAULT_ADVICE)[1] if severity != "benign" else
                      "No edits are lost (overrides identical, or winner already includes them).",
            "warnings": warn,
        })
    rank = {"critical": 0, "merge": 1, "patch": 2, "low": 3, "benign": 4}
    conflicts.sort(key=lambda c: (rank.get(c["severity"], 9), c["sig"], c["record"]))
    approx = len({tuple(m.casefold() for m in h.masters) for h in headers.values() if h.masters}) > 1
    return {"load_order": order_names, "conflict_count": len(conflicts),
            "by_severity": dict(Counter(c["severity"] for c in conflicts)), "conflicts": conflicts,
            "note": ("Field comparison is byte-level per subrecord. FormIDs inside fields are file-relative, so "
                     "plugins with different master lists can show false 'lost' FormID fields - confirm in "
                     "TES4Edit before patching." + (" Master lists differ here." if approx else ""))}


def cmd_conflicts(a):
    if a.plugins:
        paths = [resolve_plugin(n, a.data) for n in a.plugins]
        if a.active:
            die("give plugin names OR --active, not both")
        order, _, _ = effective_load_order(a.data, a.plugins_txt)
        pos = {p.name.casefold(): i for i, p in enumerate(order)}
        paths.sort(key=lambda p: pos.get(p.name.casefold(), 10_000))
    else:
        paths, missing, _ = effective_load_order(a.data, a.plugins_txt)
        if not a.include_base:
            # Official files are the baseline everyone builds on; skip their overrides of each other unless asked.
            paths = [p for p in paths if p.name.casefold() not in BASE_GAME_FILES]
    res = collect_conflicts(paths, a.data)
    if a.min_severity:
        rank = ["critical", "merge", "patch", "low", "benign"]
        keep = set(rank[: rank.index(a.min_severity) + 1])
        res["conflicts"] = [c for c in res["conflicts"] if c["severity"] in keep]
    lines = ["Load order checked: " + " > ".join(res["load_order"]),
             f"{res['conflict_count']} multi-plugin overrides: "
             + ", ".join(f"{v} {k}" for k, v in res["by_severity"].items())]
    for c in res["conflicts"][: a.limit or None]:
        lines.append(f"\n[{c['severity'].upper()}] {c['record']}  {c['edid']}")
        lines.append(f"   chain: {' -> '.join(c['overridden_by'])}   winner: {c['winner']}")
        for l in c["lost_edits"]:
            lines.append(f"   LOST from {l['plugin']}: {', '.join(l['fields'])}")
        if c["itm_in"]:
            lines.append(f"   ITM (no real change) in: {', '.join(c['itm_in'])}")
        for w in c["warnings"]:
            lines.append(f"   WARNING: {w}")
        lines.append(f"   fix: {c['advice']}")
    lines.append("\nnote: " + res["note"])
    emit(res, a.json, "\n".join(lines))


# --------------------------------------------------------------------------- load order / find
def cmd_load_order(a):
    order, missing, notes = effective_load_order(a.data, a.plugins_txt)
    pos = {p.name.casefold(): i for i, p in enumerate(order)}
    files = data_plugins(a.data)
    rows, problems = [], []
    for i, p in enumerate(order):
        try:
            h = tp.read_header(p)
        except Exception as exc:
            problems.append(f"{p.name}: unreadable header ({exc})")
            continue
        for m in h.masters:
            if m.casefold() not in files:
                problems.append(f"{p.name}: missing master {m} (CTD on load)")
            elif m.casefold() not in pos:
                problems.append(f"{p.name}: master {m} is installed but inactive (CTD on load)")
            elif pos[m.casefold()] > i:
                problems.append(f"{p.name}: master {m} loads after it")
        rows.append({"index": f"{i:02X}", "file": p.name, "esm_flag": h.is_esm_flag,
                     "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                     "masters": h.masters})
    if len(order) > 255:
        problems.append(f"{len(order)} active plugins - Oblivion supports at most 255 (incl. Oblivion.esm).")
    for m in missing:
        problems.append(f"Plugins.txt lists {m} but it is not in Data")
    obj = {"plugins_txt": str(a.plugins_txt) if a.plugins_txt else None, "order": rows,
           "problems": problems, "notes": notes}
    text = [f"Plugins.txt: {obj['plugins_txt'] or '(not found)'}"]
    text += [f"  {r['index']} {r['file']}{'  [ESM]' if r['esm_flag'] else ''}  {r['modified']}" for r in rows]
    text += ["problems:"] + [f"  - {x}" for x in problems] if problems else ["no load-order problems found"]
    text += [f"note: {n}" for n in notes]
    emit(obj, a.json, "\n".join(text))


def cmd_find(a):
    """Query forms:  EditorID | Owner.esp:XXXXXX | 8-digit in-game (load-order) FormID | 6-digit object id."""
    q = a.query.strip()
    if a.plugins:
        paths = [resolve_plugin(n, a.data) for n in a.plugins]
    else:
        paths, _, _ = effective_load_order(a.data, a.plugins_txt)
    want_key = None
    obj_only = None
    m_owner = re.fullmatch(r"(.+\.es[mp]):(?:0x)?([0-9A-Fa-f]{1,6})", q, re.IGNORECASE)
    m_hex = re.fullmatch(r"(?:0x)?([0-9A-Fa-f]{6,8})", q)
    if m_owner:
        want_key = (m_owner.group(1).casefold(), int(m_owner.group(2), 16))
    elif m_hex and len(m_hex.group(1)) == 8:
        v = int(m_hex.group(1), 16)
        idx = v >> 24
        if idx >= len(paths):
            die(f"load-order index {idx:02X} is beyond the {len(paths)} plugins in the load order")
        want_key = (paths[idx].name.casefold(), v & 0xFFFFFF)
    elif m_hex:
        obj_only = int(m_hex.group(1), 16)
    hits = []
    for path in paths:
        for plugin, rec in tp.iter_records(path):
            key = plugin.global_key(rec.form_id)
            if want_key is not None:
                ok = key == want_key
            elif obj_only is not None:
                ok = key is not None and key[1] == obj_only
            else:
                ok = rec.editor_id.casefold() == q.casefold()
            if ok:
                hits.append({"plugin": plugin.name, "sig": rec.sig, "formid": fid_str(plugin, rec.form_id),
                             "edid": rec.editor_id, "name": rec.full_name,
                             "kind": "override" if plugin.is_override(rec) else "defines",
                             "deleted": rec.is_deleted})
    text = "\n".join(f"{h['plugin']:<32} {h['kind']:<8} {h['sig']} {h['formid']}  {h['edid']}  {h['name']}"
                     f"{'  DELETED' if h['deleted'] else ''}" for h in hits) or "not found"
    if hits and want_key is not None:
        text += f"\nwinning version: {hits[-1]['plugin']}"
    emit(hits, a.json, text)


# --------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Oblivion Data folder")
    ap.add_argument("--plugins-txt", type=Path, default=None,
                    help="Plugins.txt (default %%LOCALAPPDATA%%\\Oblivion\\Plugins.txt)")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info"); s.add_argument("plugin")
    s = sub.add_parser("records"); s.add_argument("plugin"); s.add_argument("--type")
    g = s.add_mutually_exclusive_group(); g.add_argument("--overrides", action="store_true"); g.add_argument("--new", action="store_true")
    s.add_argument("--limit", type=int, default=0)
    s = sub.add_parser("lint"); s.add_argument("plugin"); s.add_argument("--no-itm", action="store_true")
    s = sub.add_parser("conflicts"); s.add_argument("plugins", nargs="*")
    s.add_argument("--active", action="store_true", help="use the active load order (default when no plugins given)")
    s.add_argument("--include-base", action="store_true", help="also compare official DLC files with each other")
    s.add_argument("--min-severity", choices=["critical", "merge", "patch", "low", "benign"])
    s.add_argument("--limit", type=int, default=0)
    sub.add_parser("load-order")
    s = sub.add_parser("find"); s.add_argument("query"); s.add_argument("plugins", nargs="*")
    a = ap.parse_args(argv)
    if a.plugins_txt is None:
        a.plugins_txt = plugins_txt_path()
    try:
        {"info": cmd_info, "records": cmd_records, "lint": cmd_lint, "conflicts": cmd_conflicts,
         "load-order": cmd_load_order, "find": cmd_find}[a.cmd](a)
    except SystemExit:
        raise
    except (OSError, ValueError) as exc:
        die(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
