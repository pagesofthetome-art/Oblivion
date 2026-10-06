"""Invented fixture data for the playtest tests (no Bethesda data).

fake_esm() writes an 'Oblivion.esm' with just what playtest reads from the real one:
  * the vanilla FormIDs the test actors use (Imperial race 0x907, Gold001 0x0F, Lockpick 0x0A,
    RepairHammer 0x0C) and XMarkerHeading / MapMarker statics;
  * an interior 'ArenaArenaFixture' (with a few references) and a decoy interior;
  * worldspaces 'Tamriel' and 'ICMarketDistrict' with exterior cells holding map markers named
    'Weye' and 'Market District';
  * an Imperial male NPC with hair/eyes/FaceGen and a CLOT item, to copy looks from.
fake_install() builds a throw-away "machine": a GOG-like game folder, a Steam-like Vortex folder,
Plugins.txt and Oblivion.ini.
"""

from __future__ import annotations

import struct
from pathlib import Path

from playtest.esp import Rec, grup, pos, sub, u32, zs

ARENA_CELL, DECOY_CELL = 0x0000A001, 0x0000A002
TAMRIEL, MARKET = 0x0000003C, 0x0000B000
WEYE_CELL, MARKET_CELL = 0x0000B101, 0x0000B201
WEYE_MARKER, MARKET_MARKER = 0x0000C001, 0x0000C002
DONOR, SHIRT = 0x0000D001, 0x0000D002


def _top(sig: str, recs: list[Rec]) -> bytes:
    return grup(sig.encode(), 0, b"".join(r.to_bytes() for r in recs))


def _cell_children(cell: int, persistent: list[Rec], temporary: list[Rec]) -> bytes:
    lab = struct.pack("<I", cell)
    kids = b""
    if persistent:
        kids += grup(lab, 8, b"".join(r.to_bytes() for r in persistent))
    if temporary:
        kids += grup(lab, 9, b"".join(r.to_bytes() for r in temporary))
    return grup(lab, 6, kids)


def _marker(fid: int, name: str, x: float, y: float) -> Rec:
    return Rec("REFR", fid, [("NAME", u32(0x10)), ("XMRK", b""), ("FNAM", b"\x01"), ("FULL", zs(name)),
                             ("TNAM", b"\x01\x00"), ("DATA", pos(x, y, 100.0))], 0x400)


def _exterior(world: int, cell: int, gx: int, gy: int, refs: list[Rec]) -> bytes:
    c = Rec("CELL", cell, [("DATA", b"\x02"), ("XCLC", struct.pack("<ii", gx, gy))])
    body = c.to_bytes() + _cell_children(cell, refs, [])
    sub_ = grup(struct.pack("<hh", gy // 8, gx // 8), 5, body)
    block = grup(struct.pack("<hh", gy // 32, gx // 32), 4, sub_)
    return grup(struct.pack("<I", world), 1, block)


def fake_esm(path: Path) -> Path:
    groups = [
        _top("RACE", [Rec("RACE", 0x00000907, [("EDID", zs("Imperial")), ("FULL", zs("Imperial"))])]),
        _top("CLOT", [Rec("CLOT", SHIRT, [("EDID", zs("LowerClassShirt01")), ("FULL", zs("Shirt"))])]),
        _top("MISC", [Rec("MISC", fid, [("EDID", zs(n)), ("DATA", struct.pack("<if", 1, 0.0))])
                      for fid, n in ((0x0000000A, "Lockpick"), (0x0000000C, "RepairHammer"), (0x0000000F, "Gold001"))]),
        _top("STAT", [Rec("STAT", 0x00000010, [("EDID", zs("MapMarker")), ("MODL", zs("marker_map.nif"))]),
                      Rec("STAT", 0x00000034, [("EDID", zs("XMarkerHeading")), ("MODL", zs("marker_arrow.nif"))]),
                      Rec("STAT", 0x0000E001, [("EDID", zs("ArenaFloor")), ("MODL", zs("arena\\floor.nif")),
                                               ("MODB", struct.pack("<f", 300.0))])]),
        _top("NPC_", [Rec("NPC_", DONOR, [
            ("EDID", zs("ICCitizenFixture")), ("FULL", zs("Citizen")),
            ("ACBS", struct.pack("<IHHHhHH", 0, 0, 0, 0, 1, 0, 0)), ("RNAM", u32(0x907)),
            ("CNTO", struct.pack("<Ii", SHIRT, 1)), ("CNTO", struct.pack("<Ii", 0x0F, 3)),
            ("DATA", bytes(21) + struct.pack("<I", 50) + bytes(8)),
            ("HNAM", u32(0x0000F001)), ("LNAM", struct.pack("<f", 0.5)), ("ENAM", u32(0x0000F002)),
            ("HCLR", b"\x40\x30\x20\x00"), ("FGGS", bytes(200)), ("FGGA", bytes(120)), ("FGTS", bytes(200)),
            ("FNAM", b"\x00\x00")])]),
    ]
    arena = Rec("CELL", ARENA_CELL, [("EDID", zs("ArenaArenaFixture")), ("FULL", zs("Arena")), ("DATA", b"\x01")])
    decoy = Rec("CELL", DECOY_CELL, [("EDID", zs("ArenaDecoyFixture")), ("FULL", zs("Arena Storage")),
                                     ("DATA", b"\x01")])
    floor = [Rec("REFR", 0x0000A100 + i, [("NAME", u32(0x0000E001)), ("DATA", pos(i * 512.0, 0.0, 0.0))])
             for i in range(4)]
    cells_body = arena.to_bytes() + _cell_children(ARENA_CELL, [], floor) + decoy.to_bytes()
    groups.append(grup(b"CELL", 0, grup(struct.pack("<i", 1), 2, grup(struct.pack("<i", 0), 3, cells_body))))
    wrld = (Rec("WRLD", TAMRIEL, [("EDID", zs("Tamriel")), ("FULL", zs("Cyrodiil"))]).to_bytes()
            + _exterior(TAMRIEL, WEYE_CELL, 5, -3, [_marker(WEYE_MARKER, "Weye", 20800.0, -11000.0)])
            + Rec("WRLD", MARKET, [("EDID", zs("ICMarketDistrict")), ("FULL", zs("Market District"))]).to_bytes()
            + _exterior(MARKET, MARKET_CELL, 10, 6, [_marker(MARKET_MARKER, "Market District", 41500.0, 25000.0)]))
    groups.append(grup(b"WRLD", 0, wrld))
    hdr = sub("HEDR", struct.pack("<fiI", 1.0, 20, 0x800)) + sub("CNAM", zs("fixture"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"TES4" + struct.pack("<IIII", len(hdr), 1, 0, 0) + hdr + b"".join(groups))
    return path


def tiny_esp(path: Path, masters: list[str]) -> Path:
    from playtest.esp import PluginWriter
    w = PluginWriter(masters, author="fixture")
    w.record("GLOB", "FixtureGlobal").add("FNAM", b"s").add("FLTV", struct.pack("<f", 1.0))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(w.build())
    return path


def placing_esp(path: Path) -> Path:
    """A mod that places objects in its own interior (for the preview)."""
    from playtest.esp import PluginWriter, f32
    w = PluginWriter(["Oblivion.esm"], author="fixture")
    st = w.record("STAT", "FixtureCrate")
    st.add("MODL", zs("clutter\\crate.nif")).add("MODB", f32(40.0))
    c = w.cell("FixtureCellar")
    c.rec.add("FULL", zs("Fixture Cellar")).add("DATA", b"\x01")
    for i in range(3):
        w.ref(c, "REFR").add("NAME", u32(st.fid)).add("DATA", pos(i * 100.0, 50.0, 0.0))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(w.build())
    return path


PLUGINS_TXT = "# This file is used by Oblivion to keep track of your downloaded content.\r\nOblivion.esm\r\nDLCShiveringIsles.esp\r\nRebirthPlus.esp\r\nSomeMod.esp\r\n"
INI = ("[General]\r\nSStartingCell=\r\nSIntroSequence=bethesda softworks HD720p.bik,2k games.bik,game studios.bik,"
       "Oblivion iv logo.bik\r\nSMainMenuMovieIntro=Oblivion iv logo.bik\r\nSLocalSavePath=Saves\\\r\n"
       "[Display]\r\niSize W=1920\r\niSize H=1080\r\n[Controls]\r\nbUse Joystick=0\r\n")


def fake_install(root: Path) -> dict:
    gog = root / "Games" / "Oblivion"
    steam = root / "Steam" / "steamapps" / "common" / "Oblivion"
    for game in (gog, steam):
        fake_esm(game / "Data" / "Oblivion.esm")
        tiny_esp(game / "Data" / "DLCShiveringIsles.esp", ["Oblivion.esm"])
        (game / "obse_loader.exe").write_bytes(b"MZ fixture")
        (game / "Oblivion.exe").write_bytes(b"MZ fixture")
    tiny_esp(steam / "Data" / "RebirthPlus.esp", ["Oblivion.esm"])
    (steam / "Data" / "vortex.deployment.json").write_text("{}", encoding="utf-8")
    local = root / "AppData" / "Local" / "Oblivion"
    docs = root / "Documents" / "My Games" / "Oblivion"
    local.mkdir(parents=True)
    docs.mkdir(parents=True)
    (local / "Plugins.txt").write_bytes(PLUGINS_TXT.encode("cp1252"))
    (docs / "Oblivion.ini").write_bytes(INI.encode("cp1252"))
    return {"gog": gog, "steam": steam, "plugins_txt": local / "Plugins.txt", "ini": docs / "Oblivion.ini",
            "vortex": root / "AppData" / "Roaming" / "Vortex", "state": root / "forge-builds" / "playtest"}
