"""Pull every compiled script out of a plugin: SCPT records and the result scripts in QUST/INFO.

A script is the run of subrecords that starts at SCHR (or the older SCHD) and continues
through SCDA, SCTX, SLSD/SCVR and SCRO/SCRV. Read-only; the rows hold Bethesda data when run
on official files, so their output is never committed.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import tes4_plugin as tp  # noqa: E402

SCRIPT_SUBS = {"SCHR", "SCHD", "SCDA", "SCTX", "SLSD", "SCVR", "SCRO", "SCRV"}
SCRIPT_RECORDS = {"SCPT", "QUST", "INFO"}
SCHR = struct.Struct("<4sIIII")     # unused, ref count, compiled size, variable count, type


def schr_fields(data: bytes) -> dict:
    if len(data) < SCHR.size:
        return {"short": len(data)}
    unused, refs, size, nvars, typ = SCHR.unpack_from(data, 0)
    return {"unused": unused.hex(), "refs": refs, "size": size, "vars": nvars, "type": typ,
            "tail": data[SCHR.size:].hex()}


def scripts_in_record(plugin, rec, topic: str = "") -> list[dict]:
    """Every script block in one record, with its context (quest stage / log entry, topic)."""
    out, cur = [], None
    stage, entry = None, -1
    for s in rec.subrecords():
        if rec.sig == "QUST" and s.sig == "INDX":
            stage, entry = struct.unpack_from("<H", s.data.ljust(2, b"\0"))[0], -1
        elif rec.sig == "QUST" and s.sig == "QSDT":
            entry += 1
        if s.sig in ("SCHR", "SCHD"):
            ctx = ""
            if rec.sig == "QUST":
                ctx = f"stage {stage} entry {entry}"
            elif rec.sig == "INFO":
                ctx = f"topic {topic}" if topic else ""
            cur = {"schr_sig": s.sig, "schr": s.data, "scda": b"", "sctx": b"", "vars": [], "refs": [],
                   "order": [s.sig], "ctx": ctx}
            out.append(cur)
            continue
        if cur is None or s.sig not in SCRIPT_SUBS:
            if cur is not None and s.sig not in SCRIPT_SUBS:
                cur = None
            continue
        cur["order"].append(s.sig)
        if s.sig == "SCDA":
            cur["scda"] = s.data
        elif s.sig == "SCTX":
            cur["sctx"] = s.data
        elif s.sig == "SLSD":
            idx = struct.unpack_from("<I", s.data.ljust(4, b"\0"))[0]
            cur["vars"].append({"index": idx, "flags": s.data[16] if len(s.data) > 16 else None,
                                "slsd": s.data.hex(), "name": ""})
        elif s.sig == "SCVR":
            if cur["vars"]:
                cur["vars"][-1]["name"] = tp.zstring(s.data)
            else:
                cur["vars"].append({"index": None, "flags": None, "slsd": "", "name": tp.zstring(s.data)})
        elif s.sig == "SCRO":
            fid = struct.unpack_from("<I", s.data.ljust(4, b"\0"))[0]
            cur["refs"].append({"kind": "SCRO", "formid": f"{fid:08X}", "owner": plugin.owner_of(fid) or "",
                                "objid": f"{fid & 0xFFFFFF:06X}"})
        elif s.sig == "SCRV":
            cur["refs"].append({"kind": "SCRV", "var": struct.unpack_from("<I", s.data.ljust(4, b"\0"))[0]})
    return out


def iter_scripts(path: Path, forms: dict | None = None):
    """Yield (row, plugin) for every script in `path`. `forms` collects (owner, objid) -> form info
    for every record with an EditorID, so callers can resolve SCRO targets afterwards."""
    topics: dict[int, str] = {}
    for plugin, rec in tp.iter_records(path):
        if rec.sig in ("LAND", "PGRD", "ROAD"):
            continue
        try:
            subs = None
            if forms is not None or rec.sig in SCRIPT_RECORDS or rec.sig == "DIAL":
                subs = rec.subrecords()
        except Exception:
            continue
        edid = ""
        if subs is not None:
            for s in subs:
                if s.sig == "EDID":
                    edid = tp.zstring(s.data)
                    break
        if rec.sig == "DIAL":
            topics[rec.form_id] = edid
        if forms is not None and edid and subs is not None:
            key = ((plugin.owner_of(rec.form_id) or plugin.name).casefold(), rec.form_id & 0xFFFFFF)
            info = {"row": "form", "plugin": plugin.name, "owner": plugin.owner_of(rec.form_id) or plugin.name,
                    "objid": f"{rec.form_id & 0xFFFFFF:06X}", "sig": rec.sig, "edid": edid}
            for s in subs:
                if s.sig == "SCRI" and len(s.data) >= 4:
                    f = struct.unpack_from("<I", s.data)[0]
                    info["scri"] = f"{plugin.owner_of(f) or ''}:{f & 0xFFFFFF:06X}"
                elif s.sig == "NAME" and rec.sig in tp.PLACED_TYPES and len(s.data) >= 4:
                    f = struct.unpack_from("<I", s.data)[0]
                    info["base"] = f"{plugin.owner_of(f) or ''}:{f & 0xFFFFFF:06X}"
            forms[key] = info
        if rec.sig not in SCRIPT_RECORDS:
            continue
        topic = topics.get(rec.parent, f"{rec.parent:08X}" if rec.parent else "") if rec.sig == "INFO" else ""
        for i, sc in enumerate(scripts_in_record(plugin, rec, topic)):
            yield {
                "row": "script", "plugin": plugin.name, "sig": rec.sig, "formid": f"{rec.form_id:08X}",
                "owner": plugin.owner_of(rec.form_id) or plugin.name, "objid": f"{rec.form_id & 0xFFFFFF:06X}",
                "edid": edid, "ctx": sc["ctx"], "n": i, "override": plugin.is_override(rec),
                "deleted": rec.is_deleted, "schr_sig": sc["schr_sig"], "schr_hex": sc["schr"].hex(),
                "schr": schr_fields(sc["schr"]), "scda": sc["scda"].hex(),
                # latin-1 is lossless: encode it back to latin-1 to get the exact SCTX bytes
                "sctx": sc["sctx"].decode("latin-1"), "vars": sc["vars"], "refs": sc["refs"], "order": sc["order"],
            }, plugin


def resolve_refs(row: dict, forms: dict) -> None:
    for r in row["refs"]:
        if r["kind"] != "SCRO":
            continue
        f = forms.get((r["owner"].casefold(), int(r["objid"], 16)))
        r["edid"] = f["edid"] if f else ""
        r["sig"] = f["sig"] if f else ""
