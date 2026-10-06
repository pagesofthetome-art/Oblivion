"""PC-side exporters for Bethesda-derived data. Their output is git-ignored, never committed.

    forge kb export-vanilla  --data <Oblivion\\Data> --out vanilla_index.jsonl
    forge kb export-commands --exe <Oblivion.exe>    --out vanilla_commands.jsonl
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import tes4_plugin as tp  # noqa: E402

# official files, in the vanilla load order
OFFICIAL = ["Oblivion.esm", "DLCShiveringIsles.esp", "Knights.esp", "DLCHorseArmor.esp", "DLCMehrunesRazor.esp",
            "DLCVileLair.esp", "DLCFrostcrag.esp", "DLCBattlehornCastle.esp", "DLCSpellTomes.esp",
            "DLCThievesDen.esp", "DLCOrrery.esp"]
SKIP = {"LAND", "PGRD", "ROAD"}       # no EditorID, huge


# --------------------------------------------------------------------------- vanilla form index
def export_vanilla(data: Path, out: Path, plugins: list[str] | None = None) -> dict:
    data = Path(data)
    names = plugins or OFFICIAL
    counts = {}
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for name in names:
            path = next((p for p in data.iterdir() if p.name.casefold() == name.casefold()), None) \
                if data.is_dir() else None
            if path is None:
                counts[name] = "missing"
                continue
            n = 0
            for p, r in tp.iter_records(path):
                if r.sig in SKIP:
                    continue
                try:
                    subs = r.subrecords()
                except Exception:
                    continue
                edid = full = ""
                for s in subs:
                    if s.sig == "EDID" and not edid:
                        edid = tp.zstring(s.data)
                    elif s.sig == "FULL" and not full:
                        full = tp.zstring(s.data)
                if not edid and not full:
                    continue
                owner = p.owner_of(r.form_id) or p.name
                fh.write(json.dumps({
                    "plugin": p.name, "owner": owner, "objid": f"{r.form_id & 0xFFFFFF:06X}",
                    "formid": f"{r.form_id:08X}", "sig": r.sig, "edid": edid, "full": full,
                    "override": p.is_override(r), "deleted": r.is_deleted,
                }, ensure_ascii=False) + "\n")
                n += 1
            # name from the file, not the loop: a record-less stub (GOG's DLCShiveringIsles.esp)
            # yields nothing and would otherwise overwrite the previous plugin's count
            counts[path.name] = n
    return counts


# --------------------------------------------------------------------------- command table from the exe
class PE:
    """Just enough PE32 parsing to map virtual addresses to file offsets."""

    def __init__(self, data: bytes):
        self.b = data
        if data[:2] != b"MZ":
            raise ValueError("not a PE file")
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("bad PE header")
        nsec, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
        opt = pe + 24
        if struct.unpack_from("<H", data, opt)[0] != 0x10B:
            raise ValueError("not a 32-bit PE")
        self.base = struct.unpack_from("<I", data, opt + 28)[0]
        self.secs = []
        for i in range(nsec):
            o = opt + opt_size + 40 * i
            vsize, va, rsize, roff = struct.unpack_from("<IIII", data, o + 8)
            self.secs.append((self.base + va, max(vsize, rsize), roff, rsize))

    def off(self, va: int) -> int | None:
        for start, size, roff, rsize in self.secs:
            if start <= va < start + size and va - start < rsize:
                return roff + va - start
        return None

    def va(self, off: int) -> int | None:
        for start, size, roff, rsize in self.secs:
            if roff <= off < roff + rsize:
                return start + off - roff
        return None

    def cstr(self, va: int, limit: int = 512) -> str | None:
        o = self.off(va) if va else None
        if o is None:
            return None
        end = self.b.find(b"\0", o, o + limit)
        if end < 0:
            return None
        s = self.b[o:end]
        if any(c < 9 or (13 < c < 32) for c in s):
            return None
        return s.decode("cp1252", "replace")


CMD = struct.Struct("<IIIIHHIIIII")     # CommandInfo, 40 bytes (xOBSE CommandTable.h)
PARAM = struct.Struct("<III")            # ParamInfo: typeStr*, typeID, isOptional


def _cmd_at(pe: PE, off: int):
    if off < 0 or off + CMD.size > len(pe.b):
        return None
    name, short, opcode, helptext, needs_parent, nparams, params, *_ = CMD.unpack_from(pe.b, off)
    n = pe.cstr(name, 64)
    if not n or not n.replace("_", "").isalnum() or not (0x100 <= opcode < 0x2000) or nparams > 32:
        return None
    return {"name": n, "alias": (pe.cstr(short, 64) or "") if short else "", "opcode": opcode,
            "help": (pe.cstr(helptext) or "") if helptext else "", "ref_required": bool(needs_parent),
            "nparams": nparams, "params_va": params}


def find_table(pe: PE, anchor: str, opcode: int | None = None) -> list[dict]:
    """Locate a CommandInfo array via a known command name, then walk it both ways."""
    needle = anchor.encode() + b"\0"
    pos = pe.b.find(b"\0" + needle) + 1
    while pos > 0:
        va = pe.va(pos)
        if va is not None:
            ref = struct.pack("<I", va)
            j = pe.b.find(ref)
            while j >= 0:
                c = _cmd_at(pe, j)
                if c and c["name"] == anchor and (opcode is None or c["opcode"] == opcode):
                    return _walk(pe, j)
                j = pe.b.find(ref, j + 1)
        pos = pe.b.find(b"\0" + needle, pos) + 1
    return []


def _walk(pe: PE, start: int) -> list[dict]:
    rows = [_cmd_at(pe, start)]
    o = start - CMD.size
    while (c := _cmd_at(pe, o)) and c["opcode"] == rows[0]["opcode"] - 1:
        rows.insert(0, c); o -= CMD.size
    o = start + CMD.size
    while (c := _cmd_at(pe, o)) and c["opcode"] == rows[-1]["opcode"] + 1:
        rows.append(c); o += CMD.size
    for c in rows:
        params = []
        po = pe.off(c.pop("params_va")) if c["nparams"] else None
        for i in range(c.pop("nparams")):
            if po is None:
                break
            tstr, tid, opt = PARAM.unpack_from(pe.b, po + PARAM.size * i)
            params.append({"name": pe.cstr(tstr, 64) or "", "type_id": tid, "optional": bool(opt)})
        c["params"] = params
    return rows


def export_commands(exe: Path, out: Path) -> dict:
    pe = PE(Path(exe).read_bytes())
    script = find_table(pe, "PlaceAtMe", 0x1025)       # opcode fixed by xOBSE CommandTable.cpp
    console = find_table(pe, "CenterOnCell")
    if not script:
        raise ValueError("script command table not found (is this Oblivion.exe 1.2.0.416, unpacked?)")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for kind, rows in (("script", script), ("console", console)):
            for r in rows:
                fh.write(json.dumps(dict(r, table=kind), ensure_ascii=False) + "\n")
    return {"script_commands": len(script), "console_commands": len(console)}
