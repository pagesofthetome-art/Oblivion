"""Invented fixture data for the playtest tests (no Bethesda data).

fake_esm() writes an 'Oblivion.esm' holding only the three vanilla FormIDs the test cells use
(Imperial race 0x907, Gold001 0x0F, XMarkerHeading 0x34), so modlint can resolve every reference.
fake_install() builds a throw-away "machine": a GOG-like game folder, a Steam-like Vortex folder,
Plugins.txt and Oblivion.ini.
"""

from __future__ import annotations

import struct
from pathlib import Path

from playtest.esp import Rec, sub, zs


def fake_esm(path: Path) -> Path:
    recs = {
        "RACE": Rec("RACE", 0x00000907, [("EDID", zs("Imperial")), ("FULL", zs("Imperial"))]),
        "MISC": Rec("MISC", 0x0000000F, [("EDID", zs("Gold001")), ("DATA", struct.pack("<if", 1, 0.0))]),
        "STAT": Rec("STAT", 0x00000034, [("EDID", zs("XMarkerHeading")), ("MODL", zs("marker_arrow.nif"))]),
    }
    body = b""
    for sig in ("RACE", "MISC", "STAT"):
        rb = recs[sig].to_bytes()
        body += b"GRUP" + struct.pack("<I", 20 + len(rb)) + sig.encode() + struct.pack("<iI", 0, 0) + rb
    hdr = sub("HEDR", struct.pack("<fiI", 1.0, 3, 0x800)) + sub("CNAM", zs("fixture"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"TES4" + struct.pack("<IIII", len(hdr), 1, 0, 0) + hdr + body)
    return path


def tiny_esp(path: Path, masters: list[str]) -> Path:
    from playtest.esp import PluginWriter
    w = PluginWriter(masters, author="fixture")
    w.record("GLOB", "FixtureGlobal").add("FNAM", b"s").add("FLTV", struct.pack("<f", 1.0))
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
