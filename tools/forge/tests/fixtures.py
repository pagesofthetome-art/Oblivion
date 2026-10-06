"""Synthetic TES4 plugins that exercise every path of the merge patch.

No Bethesda data is used: every record here is invented. The set mimics the
Rebirth+ situation: a vanilla master, installed fixes (UOP), new mods that
override the same records, a camp mod whose land gets restored, a village whose
terrain is borrowed, and a third-party patch ported onto another master.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

OBL = "Oblivion.esm"
PATCH = "Test Merge Patch.esp"


# --------------------------------------------------------------------------- binary helpers
def sub(sig: str, data: bytes) -> bytes:
    return sig.encode() + struct.pack("<H", len(data)) + data


def z(s: str) -> bytes:
    return s.encode("cp1252") + b"\0"


def u32(*v) -> bytes:
    return struct.pack(f"<{len(v)}I", *v)


def rec(sig: str, fid: int, *subs: bytes, flags: int = 0) -> bytes:
    body = b"".join(subs)
    return sig.encode() + struct.pack("<IIII", len(body), flags, fid, 0) + body


def grup(label: bytes, gtype: int, *content: bytes) -> bytes:
    c = b"".join(content)
    return b"GRUP" + struct.pack("<I", 20 + len(c)) + label + struct.pack("<iI", gtype, 0) + c


def top(sig: str, *content: bytes) -> bytes:
    return grup(sig.encode(), 0, *content)


def plugin(masters: list[str], *groups: bytes, esm: bool = False, author: str = "fixture") -> bytes:
    body = b"".join(groups)
    nrec = body.count(b"GRUP")  # header count is informational only
    hdr = sub("HEDR", struct.pack("<fiI", 1.0, nrec, 0xD00)) + sub("CNAM", z(author))
    for m in masters:
        hdr += sub("MAST", z(m)) + sub("DATA", b"\0" * 8)
    return b"TES4" + struct.pack("<IIII", len(hdr), 1 if esm else 0, 0, 0) + hdr + body


# --------------------------------------------------------------------------- record builders
def npc(fid, edid, level, spells, aggr=5, appearance=b"\x10" * 8):
    acbs = struct.pack("<IHHHhHH", 0, 50, 50, 0, level, 0, 0)
    aidt = struct.pack("<BBBBIBBH", aggr, 50, 50, 50, 0, 0, 0, 0)
    return rec("NPC_", fid, sub("EDID", z(edid)), sub("FULL", z(edid.title())), sub("ACBS", acbs),
               *[sub("SPLO", u32(s)) for s in spells], sub("AIDT", aidt), sub("FNAM", appearance))


def quest(fid, edid, stages: dict[int, str]):
    out = [sub("EDID", z(edid)), sub("DATA", b"\x01\x32")]
    for idx in sorted(stages):
        out += [sub("INDX", struct.pack("<h", idx)), sub("QSDT", b"\0"), sub("CNAM", z(stages[idx]))]
    return rec("QUST", fid, *out)


def dial(fid, edid, quest_fid):
    return rec("DIAL", fid, sub("EDID", z(edid)), sub("QSTI", u32(quest_fid)), sub("DATA", b"\0"))


def info(fid, quest_fid, text, choice=None):
    s = [sub("DATA", b"\0\0\0"), sub("QSTI", u32(quest_fid))]
    if choice:
        s.append(sub("TCLT", u32(choice)))
    s += [sub("TRDT", b"\0" * 24), sub("NAM1", z(text)), sub("NAM2", z(""))]
    return rec("INFO", fid, *s)


def icell(fid, edid, full, light=b"\x20" * 36):
    return rec("CELL", fid, sub("EDID", z(edid)), sub("FULL", z(full)), sub("DATA", b"\x01"), sub("XCLL", light))


def interior_cells(*cells_with_id: tuple[int, bytes]):
    out = []
    for fid, c in cells_with_id:
        oid = fid & 0xFFFFFF
        out.append(grup(struct.pack("<i", oid % 10), 2, grup(struct.pack("<i", (oid // 10) % 10), 3, c)))
    return top("CELL", *out)


def xcell(fid, x, y):
    return rec("CELL", fid, sub("DATA", b"\x02"), sub("XCLC", struct.pack("<ii", x, y)))


def land(fid, fill: int):
    return rec("LAND", fid, sub("DATA", u32(1)), sub("VHGT", bytes([fill]) * 64))


def refr(fid, base, x, y, flags=0):
    return rec("REFR", fid, sub("NAME", u32(base)), sub("DATA", struct.pack("<6f", x, y, 0, 0, 0, 0)),
               flags=flags)


def world(wrld_fid, wrld_rec, pcell=None, pcell_refs=(), cells=()):
    """cells: [(cell_fid, cell_rec, gx, gy, temp_children[])]"""
    kids = []
    if pcell is not None:
        kids.append(pcell[1])
        if pcell_refs:
            kids.append(grup(u32(pcell[0]), 6, grup(u32(pcell[0]), 8, *pcell_refs)))
    for cfid, crec, gx, gy, temp in cells:
        inner = [crec]
        if temp:
            inner.append(grup(u32(cfid), 6, grup(u32(cfid), 9, *temp)))
        kids.append(grup(struct.pack("<hh", gy // 32, gx // 32), 4,
                         grup(struct.pack("<hh", gy // 8, gx // 8), 5, *inner)))
    return top("WRLD", wrld_rec, grup(u32(wrld_fid), 1, *kids))


TAM = 0x3C
WRLD_REC = rec("WRLD", TAM, sub("EDID", z("Tamriel")), sub("FULL", z("Cyrodiil")))
PCELL = 0x600
GRIDS = {(51, -3): (0x700, 0x701), (51, -4): (0x710, 0x711), (-23, 15): (0x720, 0x721), (19, -40): (0x730, 0x731)}


def _vanilla() -> bytes:
    cells = [(c, xcell(c, gx, gy), gx, gy, [land(l, 1), refr(c + 2, 0x900, gx * 4096 + 10, gy * 4096 + 10)])
             for (gx, gy), (c, l) in GRIDS.items()]
    return plugin(
        [],
        top("SPEL", *[rec("SPEL", f, sub("EDID", z(f"Spell{f:X}"))) for f in (0x500, 0x501, 0x502)]),
        top("NPC_", npc(0x100, "TestNPC", 5, [0x500]), npc(0x101, "OtherNPC", 3, [], aggr=10)),
        top("QUST", quest(0x200, "TestQuest", {10: "log ten", 20: "log twenty"})),
        top("DIAL", dial(0x300, "TestTopic", 0x200), grup(u32(0x300), 7, info(0x301, 0x200, "hello"))),
        interior_cells((0x400, icell(0x400, "TestCell", "Test Cell"))),
        world(TAM, WRLD_REC, pcell=(PCELL, rec("CELL", PCELL, sub("DATA", b"\x02"))), cells=cells),
        esm=True, author="vanilla fixture")


def _uop() -> bytes:
    return plugin(
        [OBL],
        top("NPC_", npc(0x100, "TestNPC", 10, [0x500]), npc(0x101, "OtherNPC", 3, [0x500], aggr=10)),
        top("QUST", quest(0x200, "TestQuest", {10: "log ten (fixed)", 20: "log twenty"})),
        top("DIAL", dial(0x300, "TestTopic", 0x200), grup(u32(0x300), 7, info(0x301, 0x200, "hello (fixed)"))),
        interior_cells((0x400, icell(0x400, "TestCell", "Test Cell UOP"))))


def _camp() -> bytes:
    gx, gy = 51, -3
    c, l = GRIDS[(gx, gy)]
    return plugin(
        [OBL],
        world(TAM, WRLD_REC,
              pcell=(PCELL, rec("CELL", PCELL, sub("DATA", b"\x02"))),
              pcell_refs=[refr(0x01000801, 0x900, gx * 4096 + 100, gy * 4096 + 100)],
              cells=[(c, xcell(c, gx, gy), gx, gy,
                      [land(l, 9), refr(0x01000800, 0x900, gx * 4096 + 50, gy * 4096 + 50)])]))


def _new_a() -> bytes:
    return plugin(
        [OBL],
        top("NPC_", npc(0x100, "TestNPC", 5, [0x500, 0x501])),
        top("QUST", quest(0x200, "TestQuest", {10: "log ten", 20: "log twenty", 30: "log thirty (A)"})),
        top("DIAL", dial(0x300, "TestTopic", 0x200), grup(u32(0x300), 7, info(0x301, 0x200, "hello", choice=0x300))),
        interior_cells((0x400, icell(0x400, "TestCell", "Test Cell", light=b"\x44" * 36))))


def _new_b() -> bytes:
    # 0x101 first: with set-ordered iteration this flips the NPC_ order in the legacy output
    return plugin(
        [OBL],
        top("NPC_", npc(0x101, "OtherNPC", 7, [], aggr=10), npc(0x100, "TestNPC", 5, [0x500, 0x502], aggr=40)),
        top("QUST", quest(0x200, "TestQuest", {10: "log ten", 20: "log twenty (B)"})))


def _village() -> bytes:
    gx, gy = -23, 15
    c, l = GRIDS[(gx, gy)]
    return plugin([OBL], world(TAM, WRLD_REC, cells=[(c, xcell(c, gx, gy), gx, gy, [land(l, 7)])]))


def _thieves() -> bytes:
    gx, gy = 19, -40
    c, _l = GRIDS[(gx, gy)]
    return plugin([OBL], world(TAM, WRLD_REC, cells=[(c, xcell(c, gx, gy), gx, gy,
                                                       [refr(0x01000A00, 0x900, gx * 4096 + 5, gy * 4096 + 5)])]))


def _port_patch() -> bytes:
    gx, gy = 19, -40
    c, _l = GRIDS[(gx, gy)]
    return plugin([OBL, "ThievesV4.esp"], world(TAM, WRLD_REC, cells=[(c, xcell(c, gx, gy), gx, gy, [
        refr(0x01000A00, 0x900, gx * 4096 + 900, gy * 4096 + 900),     # moved object from the V4 master
        refr(0x02000B00, 0x900, gx * 4096 + 300, gy * 4096 + 300),     # the patch's own new object
    ])]))


def _empty() -> bytes:
    return plugin([OBL])


CFG = {
    "description": "Fixture merge patch. Load LAST.",
    "new_order": ["NewA.esp", "NewB.esp", "Village.esp", "Thieves.esp"],
    "low_priority": ["NewB.esp"],
    "merge_types": ["NPC_", "CREA", "PACK", "QUST", "CLOT", "ARMO", "BOOK", "FACT", "IDLE", "SPEL",
                    "DOOR", "LVLI", "WEAP", "ENCH", "CELL", "INFO"],
    "extra_paths": [],
    "world_edits": [
        {"type": "restore_land_and_disable", "cells": [[51, -3], [51, -4]], "disable_from": "Camp.esp"},
        {"type": "land_from", "plugin": "Village.esp", "cells": [[-23, 15]]},
        {"type": "port_patch", "path": "PortPatch.esp", "cells": [[19, -40]],
         "remap": {"thievesv4.esp": "thieves.esp"}},
    ],
}

PLUGINS_TXT = """# fixture load order
Oblivion.esm
*UOP.esp
*DLCFoo - Unofficial Patch.esp
*Oblivion Citadel Door Fix.esp
*Camp.esp
*NewA.esp
*ElsweyrAnequina.esp
*NewB.esp
*Village.esp
*Thieves.esp
*Test Merge Patch.esp
"""


def make(root: Path) -> dict:
    """Write the fixture tree under `root` and return its paths."""
    inst = root / "installed"          # stands in for the Steam Data folder
    new = root / "newmods"             # stands in for the extracted new-mod archives
    work = root / "work"               # legacy script's working folder (holds the port patch)
    for d in (inst, new, work):
        d.mkdir(parents=True, exist_ok=True)
    (inst / OBL).write_bytes(_vanilla())
    for name, data in {"UOP.esp": _uop(), "Camp.esp": _camp(), "DLCFoo.esp": _empty(),
                       "DLCFoo - Unofficial Patch.esp": _empty(), "Oblivion Citadel Door Fix.esp": _empty(),
                       "DLCShiveringIsles.esp": _empty(), "ElsweyrAnequina.esp": _empty()}.items():
        (inst / name).write_bytes(data)
    new_paths = []
    for name, data in {"NewA.esp": _new_a(), "NewB.esp": _new_b(), "Village.esp": _village(),
                       "Thieves.esp": _thieves()}.items():
        (new / name).write_bytes(data)
        (inst / name).write_bytes(data)    # also deployed, as on the PC (lint needs masters in Data)
        new_paths.append(new / name)
    (work / "PortPatch.esp").write_bytes(_port_patch())
    (root / "Plugins.txt").write_text(PLUGINS_TXT, encoding="utf-8")
    (root / "build_cfg.json").write_text(json.dumps(CFG, indent=1), encoding="utf-8")
    spec = {
        "forge_spec": 1, "name": "fixture-merge-patch", "kind": "merge_patch",
        "intent": "Fixture: merge NPC/quest/dialogue/cell edits and apply world edits.",
        "output": {"plugin": PATCH, "dir": "out", "version": "1.0",
                   "install_notes": ["Load last."]},
        "inputs": [{"id": "fixtures", "path": ".", "permission": "PROJECT_OWNED"}],
        "merge_patch": {
            "config": "build_cfg.json", "vanilla": f"installed/{OBL}", "installed_dir": "installed",
            "plugins_txt": "Plugins.txt", "new_mod_paths": [f"newmods/{p.name}" for p in new_paths],
            "workdir": "work",
            "extra_plugins": {"ElsweyrAnequina.esp": "installed/ElsweyrAnequina.esp"},
            "insert_after": {"Oblivion Citadel Door Fix.esp": "DLCShiveringIsles.esp"},
        },
        "test_plan": ["coc TestCell: lighting from NewA, name from UOP"],
    }
    (root / "spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    return {"root": root, "installed": inst, "new": new, "work": work, "new_paths": new_paths,
            "spec": root / "spec.json", "plugins_txt": root / "Plugins.txt", "cfg": root / "build_cfg.json"}
