"""ForgeTestCells.esp: the test actors for real-game playtests. No geometry, no new meshes.

The test locations are vanilla cells (see vanilla.py). This plugin only adds the actors a test
needs, parked in an empty holding cell nobody visits (ForgeHoldingCell). The boot batch moves the
ones a location needs next to the player:

  ForgeArenaDummyRef     essential training dummy, aggression 0, 500 health: spell / weapon target
  ForgeArenaCasterRef    essential, passive: `cast` steps use it as the caster
  ForgeStreetMerchantRef essential merchant (barter: weapons, armor, misc, potions; sells lockpicks
                         and repair hammers), work package 08-20, evening package 20-08
  ForgeStreetTownsfolkRef, ForgeStreetTownsfolk2Ref   wander around wherever they are

Packages use "near current location", so the actors stay where they were moved to. No vanilla
record is overridden.

Appearance. With the test game's Oblivion.esm at hand (the normal case), each actor copies the
hair, eyes, face (FaceGen) and clothes of a real vanilla Imperial NPC, so they look like everyone
else in Cyrodiil. Without it (the cloud tests) they are plain Imperials.

Vanilla references: the Imperial race (0x00000907), Gold001 (0x0000000F), Lockpick (0x0000000A)
and RepairHammer (0x0000000C); with Oblivion.esm, also the copied hair, eyes and clothes.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from .esp import PluginWriter, pos, u32, zs

PLUGIN_NAME = "ForgeTestCells.esp"
MASTERS = ["Oblivion.esm"]
HOLDING_CELL = "ForgeHoldingCell"

IMPERIAL_RACE = 0x00000907
GOLD001, LOCKPICK, REPAIR_HAMMER = 0x0000000F, 0x0000000A, 0x0000000C
SKELETON = "Characters\\_Male\\skeleton.nif"

SKILLS = ["Armorer", "Athletics", "Blade", "Block", "Blunt", "HandToHand", "HeavyArmor", "Alchemy", "Alteration",
          "Conjuration", "Destruction", "Illusion", "Mysticism", "Restoration", "Acrobatics", "LightArmor",
          "Marksman", "Mercantile", "Security", "Sneak", "Speechcraft"]
SKILL_AV = {n: 12 + i for i, n in enumerate(SKILLS)}
SERVICES = {"weapons": 0x1, "armor": 0x2, "clothing": 0x4, "books": 0x8, "ingredients": 0x10, "lights": 0x80,
            "apparatus": 0x100, "misc": 0x400, "spells": 0x800, "magic_items": 0x1000, "potions": 0x2000,
            "training": 0x4000, "recharge": 0x10000, "repair": 0x20000}
PACKAGE_TYPES = {"find": 0, "follow": 1, "escort": 2, "eat": 3, "sleep": 4, "wander": 5, "travel": 6,
                 "accompany": 7, "useitemat": 8, "ambush": 9, "flee": 10, "castmagic": 11}
LOCATION_TYPES = {"near_ref": 0, "in_cell": 1, "near_current": 2, "near_editor": 3}

NPCS = {
    "ForgeArenaDummy": {"name": "Training Dummy", "level": 10, "health": 500, "essential": True,
                        "aggression": 0, "confidence": 100, "packages": ["ForgeStayPkg"], "skills": 10,
                        "attributes": 40, "ref": "ForgeArenaDummyRef"},
    "ForgeArenaCaster": {"name": "Spell Tester", "level": 10, "health": 500, "essential": True,
                         "aggression": 0, "confidence": 100, "packages": ["ForgeStayPkg"], "skills": 50,
                         "attributes": 60, "ref": "ForgeArenaCasterRef"},
    "ForgeStreetMerchant": {"name": "Ilvia the Trader", "level": 8, "health": 120, "essential": True,
                            "aggression": 5, "confidence": 50, "barter_gold": 800,
                            "services": ["weapons", "armor", "misc", "potions"],
                            "packages": ["ForgeMerchantWorkPkg", "ForgeMerchantEveningPkg"],
                            "items": [[LOCKPICK, 20], [REPAIR_HAMMER, 10], [GOLD001, 50]],
                            "skills": 25, "attributes": 45, "mercantile": 60, "ref": "ForgeStreetMerchantRef"},
    "ForgeStreetTownsfolk": {"name": "Townsperson", "level": 3, "health": 60, "essential": True,
                             "aggression": 5, "confidence": 30, "packages": ["ForgeTownsfolkWanderPkg"],
                             "skills": 15, "attributes": 40,
                             "ref": ["ForgeStreetTownsfolkRef", "ForgeStreetTownsfolk2Ref"]},
}
PACKAGES = {
    "ForgeStayPkg": {"type": "wander", "location": ["near_current", 0], "hour": 0, "duration": 24, "flags": 0,
                     "note": "stay where it was put, all day"},
    "ForgeMerchantWorkPkg": {"type": "wander", "location": ["near_current", 256], "hour": 8, "duration": 12,
                             "flags": 0x1, "note": "08:00-20:00 work in place, offers barter"},
    "ForgeMerchantEveningPkg": {"type": "wander", "location": ["near_current", 64], "hour": 20, "duration": 12,
                                "flags": 0, "note": "20:00-08:00 off duty (no barter), stays close"},
    "ForgeTownsfolkWanderPkg": {"type": "wander", "location": ["near_current", 1024], "hour": 0, "duration": 24,
                                "flags": 0, "note": "wander around, all day"},
}
# which actors come to which location, and where (offset from the player, game units)
BRING = {
    "arena": [("ForgeArenaDummyRef", 0, 600, 0), ("ForgeArenaCasterRef", 200, 100, 0)],
    "street": [("ForgeStreetMerchantRef", 0, 300, 0), ("ForgeStreetTownsfolkRef", 300, 500, 0),
               ("ForgeStreetTownsfolk2Ref", -300, 700, 0)],
    "open": [("ForgeArenaDummyRef", 0, 1200, 0), ("ForgeArenaCasterRef", 200, 100, 0)],
    "custom": [("ForgeArenaDummyRef", 0, 500, 0), ("ForgeArenaCasterRef", 200, 100, 0)],
}
APPEARANCE_SUBS = ("HNAM", "LNAM", "ENAM", "HCLR", "FGGS", "FGGA", "FGTS", "FNAM")
# result globals: checks store their values here and the last batch saves the game, so results
# reach disk even when the console log doesn't (run 5). See essglobals.py.
MAX_CHECKS = 32
RESULT_GLOBALS = ["ForgeRunStamp", "ForgeRunDone", "ForgeRInPlace"] + [f"ForgeR{i:02d}" for i in range(1, MAX_CHECKS + 1)]


def _package(w: PluginWriter, edid: str, p: dict) -> int:
    r = w.record("PACK", edid)
    r.add("PKDT", struct.pack("<IB3x", p["flags"], PACKAGE_TYPES[p["type"]]))
    ltype, radius = p["location"]
    r.add("PLDT", struct.pack("<iIi", LOCATION_TYPES[ltype], 0, radius))
    r.add("PSDT", struct.pack("<bbBbi", -1, -1, 0, p["hour"], p["duration"]))
    return r.fid


def _npc(w: PluginWriter, edid: str, d: dict, class_fid: int, pkg: dict, look: dict | None) -> None:
    r = w.record("NPC_", edid)
    r.add("FULL", zs(d["name"]))
    r.add("MODL", zs(SKELETON))
    r.add("ACBS", struct.pack("<IHHHhHH", 0x02 if d.get("essential") else 0, 0, 0, d.get("barter_gold", 0),
                              d["level"], 0, 0))
    r.add("RNAM", u32(IMPERIAL_RACE))
    items = list(d.get("items", [])) + [[fid, 1] for fid in (look or {}).get("outfit", [])]
    for fid, count in items:
        r.add("CNTO", struct.pack("<Ii", fid, count))
    services = 0
    for s in d.get("services", []):
        services |= SERVICES[s]
    r.add("AIDT", struct.pack("<BBBBIbBH", d["aggression"], d["confidence"], 50, 50, services, -1, 0, 0))
    for p in d.get("packages", []):
        r.add("PKID", u32(pkg[p]))
    r.add("CNAM", u32(class_fid))
    skills = [d.get("skills", 10)] * 21
    if "mercantile" in d:
        skills[SKILLS.index("Mercantile")] = d["mercantile"]
    r.add("DATA", bytes(skills) + struct.pack("<I", d["health"]) + bytes([d.get("attributes", 40)] * 8))
    for sig in APPEARANCE_SUBS:                       # vanilla subrecord order after DATA
        if look and sig in look.get("subs", {}):
            r.add(sig, look["subs"][sig])


def donor_looks(esm: Path | None) -> dict | None:
    """Appearance of real vanilla Imperial NPCs (male for everyone; Oblivion.esm is only read)."""
    if not esm or not Path(esm).is_file():
        return None
    import tes4_plugin as tp
    wear: set[int] = set()
    for _, r in tp.iter_records(esm, {"CLOT"}):
        wear.add(r.form_id)
    donors = []
    for _, r in tp.iter_records(esm, {"NPC_"}):
        subs = {}
        outfit = []
        race = None
        female = False
        for s in r.subrecords():
            if s.sig == "RNAM":
                race = struct.unpack("<I", s.data[:4])[0]
            elif s.sig == "ACBS":
                female = bool(struct.unpack_from("<I", s.data)[0] & 1)
            elif s.sig == "CNTO":
                fid = struct.unpack_from("<I", s.data)[0]
                if fid in wear:
                    outfit.append(fid)
            elif s.sig in APPEARANCE_SUBS:
                subs[s.sig] = s.data
        if race == IMPERIAL_RACE and not female and {"HNAM", "ENAM", "FGGS"} <= set(subs) and outfit:
            donors.append({"edid": r.editor_id, "subs": subs, "outfit": outfit[:4]})
        if len(donors) >= 8:
            break
    return {"donors": donors} if donors else None


def build_plugin(esm: Path | None = None) -> tuple[bytes, dict]:
    """Return (plugin bytes, layout). Deterministic for the same Oblivion.esm."""
    looks = donor_looks(esm)
    w = PluginWriter(MASTERS, author="TES4Forge playtest",
                     desc="Test actors for forge playtest (real vanilla cells). Test profile only; never install for play.")
    clas = w.record("CLAS", "ForgeTestClass")
    clas.add("FULL", zs("Test Subject"))
    major = [SKILL_AV[s] for s in ("Blade", "Block", "Blunt", "HeavyArmor", "Athletics", "Destruction", "Mercantile")]
    clas.add("DATA", struct.pack("<2iI7iIIbB2x", 0, 1, 0, *major, 0, 0, 0, 0))
    pkg = {edid: _package(w, edid, p) for edid, p in PACKAGES.items()}
    lay = {"plugin": PLUGIN_NAME, "holding_cell": HOLDING_CELL, "npcs": {}, "packages": PACKAGES, "bring": BRING,
           "appearance": [d["edid"] for d in looks["donors"]] if looks else None}
    for i, (edid, d) in enumerate(NPCS.items()):
        look = looks["donors"][i % len(looks["donors"])] if looks else None
        _npc(w, edid, d, clas.fid, pkg, look)
        lay["npcs"][edid] = {**{k: v for k, v in d.items() if k != "items"}, "formid": f"{w.fid(edid):08X}",
                             "looks_like": look["edid"] if look else None}
    cell = w.cell(HOLDING_CELL)
    cell.rec.add("FULL", zs("Forge holding cell"))
    cell.rec.add("DATA", bytes([0x01]))
    x = 0.0
    for edid, d in NPCS.items():
        refs = d["ref"] if isinstance(d["ref"], list) else [d["ref"]]
        for ref_edid in refs:
            r = w.ref(cell, "ACHR", ref_edid, persistent=True)
            r.add("NAME", u32(w.fid(edid)))
            r.add("DATA", pos(x, 0.0, 0.0))
            x += 200.0
    lay["refs"] = {e: f"{w.fid(e):08X}" for d in NPCS.values()
                   for e in (d["ref"] if isinstance(d["ref"], list) else [d["ref"]])}
    for g in RESULT_GLOBALS:                         # last, so earlier FormIDs never move
        w.record("GLOB", g).add("FNAM", b"f").add("FLTV", struct.pack("<f", 0.0))
    lay["globals"] = {g: w.fid(g) & 0xFFFFFF for g in RESULT_GLOBALS}
    return w.build(), lay


def write(out_dir: Path, esm: Path | None = None) -> tuple[Path, Path]:
    data, lay = build_plugin(esm)
    out_dir.mkdir(parents=True, exist_ok=True)
    esp = out_dir / PLUGIN_NAME
    esp.write_bytes(data)
    lj = out_dir / "ForgeTestCells.layout.json"
    lj.write_text(json.dumps(lay, indent=1, sort_keys=True), encoding="utf-8")
    return esp, lj
