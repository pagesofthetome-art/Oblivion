"""forge dump: show a record's subrecords byte by byte, decoded with the KB record schemas.

    forge dump <Plugin.esp|path> <EditorID | FormID> [--data DIR] [--json]
    forge dump <Plugin.esp|path> --sig SPEL [--match Fire] [--has SCIT] [--limit 5]

Read-only. FormIDs are shown load-order independent (Owner.esp:OOOOOO).
"""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import tes4_plugin as tp  # noqa: E402

SCHEMAS = TOOLS / "forge" / "kb" / "data" / "record_schemas.json"
FMT = {"itU8": "<B", "itS8": "<b", "itU16": "<H", "itS16": "<h", "itU32": "<I", "itS32": "<i",
       "float": "<f", "formid": "<I"}


def _schemas() -> dict:
    from forge import records as R
    out = {}
    for sig, subs_list in R.schemas().items():
        subs = {}
        for s in subs_list:
            subs.setdefault(s["sig"], s)       # first definition of a signature wins
        out[sig] = subs
    return out


def _fid(plugin, v: int) -> str:
    if v == 0:
        return "NULL"
    k = plugin.global_key(v)
    return f"{k[0]}:{k[1]:06X}" if k else f"?:{v:08X}"


CTDA_OPERATORS = {0: "Equal To", 32: "Not Equal To", 64: "Greater Than", 96: "Greater Than Or Equal To",
                  128: "Less Than", 160: "Less Than Or Equal To"}   # xEdit wbConditionTypeToStr (top 3 bits)


def decode(plugin, rec_sig: str, sub, schema: dict | None, nth: int = 0) -> list[dict]:
    """Decode a subrecord for display with the same codec forge builds with (forge/records.py)."""
    from forge import records as R
    if not schema:
        return []
    dec = R.decode(rec_sig, sub.sig, sub.data, nth)
    if dec["layout"] == "string":
        return [{"name": schema["name"] or "text", "value": dec["value"]}]
    if dec["layout"] == "array":
        out = []
        for i, item in enumerate(dec["items"]):
            for k, v in item.items():
                if any(f["name"] == k and f["formid"] for f in schema["fields"]) and isinstance(v, str):
                    v = _fid(plugin, int(v, 16))
                out.append({"name": f"[{i}] {k}", "value": v})
        return out
    if dec["layout"] != "struct":
        if schema["kind"] == "formid" and len(sub.data) == 4:
            return [{"name": schema["name"], "value": _fid(plugin, struct.unpack("<I", sub.data)[0])}]
        return []
    lay = R.fixed_layout(R.sub_schema(rec_sig, sub.sig, nth), len(sub.data)) or []
    by_name = dict(zip(R._field_names(lay), lay))
    out = []
    for name, v in dec["fields"].items():
        f = by_name.get(name, {})
        if f.get("formid") and isinstance(v, str) and len(v) == 8:
            v = _fid(plugin, int(v, 16))
        elif sub.sig in ("CTDA", "CTDT") and name == "Type" and isinstance(v, int):
            v = f"{CTDA_OPERATORS.get(v & 0xE0, '?')} (flags {v & 0x1F:#x}) [{v}]"
        elif isinstance(v, list):
            v = f"{v}"
        out.append({"name": name, "offset": f.get("offset"), "type": f.get("type"), "value": v})
    if dec.get("tail"):
        out.append({"name": "(tail)", "value": dec["tail"]})
    return out


def find(path: Path, selector: str | None, sig: str | None, match: str | None, limit: int,
         has: list[str] | None = None):
    want_fid = None
    if selector and re.fullmatch(r"(?:0x)?[0-9A-Fa-f]{8}", selector):
        want_fid = int(selector[-8:], 16)
    n = 0
    for p, r in tp.iter_records(path, want={sig} if sig else None):
        if want_fid is not None:
            if r.form_id != want_fid:
                continue
        elif selector:
            if r.editor_id.lower() != selector.lower():
                continue
        elif match and match.lower() not in (r.editor_id + " " + r.full_name).lower():
            continue
        if has and not set(has) <= {x.sig for x in r.subrecords()}:
            continue
        yield p, r
        n += 1
        if limit and n >= limit:
            return


def dump(path: Path, selector=None, sig=None, match=None, limit=5, has=None) -> list[dict]:
    schemas = _schemas()
    out = []
    for p, r in find(path, selector, sig, match, limit, has):
        sch = schemas.get(r.sig, {})
        from forge import records as R
        raw = r.subrecords()
        decs = R.decode_record(r.sig, [(x.sig, x.data) for x in raw])
        subs = []
        for s, d in zip(raw, decs):
            subs.append({"sig": s.sig, "size": len(s.data), "hex": s.data.hex(),
                         "fields": decode(p, r.sig, s, R.sub_schema(r.sig, s.sig, d["nth"]) or sch.get(s.sig), d["nth"])})
        out.append({"plugin": p.name, "sig": r.sig, "formid": f"{r.form_id:08X}", "key": _fid(p, r.form_id),
                    "edid": r.editor_id, "flags": f"{r.flags:08X}", "compressed": r.is_compressed,
                    "masters": p.masters, "subrecords": subs})
    return out


def text(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        lines.append(f"{r['sig']} {r['key']} [{r['formid']}] {r['edid']}  flags {r['flags']}"
                     f"{' (compressed)' if r['compressed'] else ''}  in {r['plugin']}")
        for s in r["subrecords"]:
            hx = s["hex"] if len(s["hex"]) <= 96 else s["hex"][:96] + "…"
            lines.append(f"  {s['sig']} ({s['size']:>4}) {hx}")
            for f in s["fields"]:
                lines.append(f"        {('+' + str(f['offset'])) if 'offset' in f else '':>4} {f['name']}: {f['value']}")
    return "\n".join(lines) or "no matching record"


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="forge dump")
    ap.add_argument("plugin")
    ap.add_argument("selector", nargs="?")
    ap.add_argument("--data", type=Path, help="folder to find the plugin in (default: as given)")
    ap.add_argument("--sig")
    ap.add_argument("--match")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--has", action="append", help="only records that contain this subrecord (repeatable)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    path = (a.data / a.plugin) if a.data else Path(a.plugin)
    if not path.is_file():
        print(f"error: not found: {path}", file=sys.stderr)
        return 1
    if not a.selector and not a.sig:
        print("error: give an EditorID/FormID or --sig", file=sys.stderr)
        return 1
    rows = dump(path, a.selector, a.sig.upper() if a.sig else None, a.match, a.limit,
                [h.upper() for h in a.has] if a.has else None)
    print(json.dumps(rows, indent=1) if a.json else text(rows))
    return 0 if rows else 2
