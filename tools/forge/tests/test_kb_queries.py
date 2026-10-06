"""Phase 2 acceptance: 20 questions an agent would ask, answered in one `forge kb` call each.

Cloud questions (14) need only the committed sources. PC questions (6) need the local
exports: run `scripts\\kb\\Build forge KB.bat` (or `forge kb export-vanilla`, `export-commands`).
Without them they are skipped, not failed.

Run from tools\\:  python -m unittest forge.tests.test_kb_queries -v
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

from forge.kb import CONFIDENCE, build as kbuild, query as q  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="forge-kb-"))
DB = TMP / "kb.sqlite"
VANILLA = kbuild.DEFAULT_VANILLA
COMMANDS = kbuild.DEFAULT_COMMANDS


def setUpModule():
    kbuild.build(DB, VANILLA, COMMANDS)


def tearDownModule():
    q.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


def top(question, n=3, kinds=None):
    return q.search(question, n, kinds, DB)


def keys(results):
    return [r["key"] if r["kind"] != "technique" else r["title"] for r in results]


def vanilla_rows() -> int:
    with closing(sqlite3.connect(DB)) as c:
        return c.execute("SELECT COUNT(*) FROM vanilla_forms").fetchone()[0]


def exe_commands() -> int:
    with closing(sqlite3.connect(DB)) as c:
        return c.execute("SELECT COUNT(*) FROM functions WHERE opcode IS NOT NULL").fetchone()[0]


class CloudQuestions(unittest.TestCase):
    """Answerable from committed facts + our notes (no Bethesda data)."""

    def test_q01_projectile_owner(self):
        # Which OBSE function changes a projectile's owner?
        r = top("Which OBSE function changes a projectile's owner?", 1)
        self.assertEqual(keys(r), ["SetProjectileSource"])
        self.assertEqual(r[0]["detail"]["origin"], "obse")

    def test_q02_info_formid_subrecords(self):
        # Which subrecords of INFO hold FormIDs?
        r = top("Which subrecords of INFO hold FormIDs?", 1)
        self.assertEqual((r[0]["kind"], r[0]["key"]), ("record", "INFO"))
        rec = q.record("INFO", DB)
        self.assertTrue({"QSTI", "TPIC", "PNAM", "NAME", "TCLT", "TCLF", "SCRO", "CTDA"} <= set(rec["formid_subrecords"]))
        # agrees with the merge patch's own FormID table
        sys.path.insert(0, str(TOOLS / "merge-patch"))
        import patchlib
        self.assertTrue({s for (rt, s), v in patchlib.F.items() if rt == "INFO" and v} <= set(rec["formid_subrecords"]))

    def test_q03_key_press_and_parameter(self):
        # What OBSE function reads a key press, and what does its parameter mean?
        r = top("What OBSE function reads a key press, and what does its parameter mean?", 1)
        self.assertIn(r[0]["key"], ("IsKeyPressed3", "IsKeyPressed2"))
        f = q.func(r[0]["key"], DB)
        self.assertIn("scan code", f["params_note"])
        self.assertEqual([p["type"] for p in f["params"]], ["Integer"])

    def test_q04_positionworld_return_point(self):
        # Which research mods use PositionWorld for a return point?
        names = {t["specimen"] for t in q.technique("PositionWorld", DB) if t["nexus_id"]}
        self.assertEqual(names, {"Dimensional Pocket", "Pocket Dimension Player Home"})
        self.assertTrue({"Dimensional Pocket", "Pocket Dimension Player Home"} <=
                        set(keys(top("Which research mods use PositionWorld for a return point?", 5))))

    def test_q05_portal_technique(self):
        # How did a research mod make a portal?
        r = top("How did a research mod make a portal?", 3, ["technique"])
        portal = next(x for x in r if x["title"] == "Portal")
        d = portal["detail"]
        self.assertEqual(d["nexus_id"], 13673)
        self.assertIn("DOOR", d["technique"])
        self.assertIn("marker", d["technique"])
        self.assertTrue({"SetPos", "SetAngle"} <= set(d["functions_used"].split(",")))

    def test_q06_persuasion_trap(self):
        # What causes the "stuck on Persuasion tutorial" trap?
        r = top('What causes the "stuck on Persuasion tutorial" trap?', 1)
        self.assertEqual(r[0]["key"], "northernui-persuasion-tutorial")
        self.assertIn("NorthernUI", r[0]["detail"]["cause"])
        self.assertIn("Down", r[0]["detail"]["fix"])

    def test_q07_elys_usv(self):
        # Why does Elys Silent Voice do nothing?
        r = top("Why does Elys Silent Voice do nothing?", 1)
        self.assertEqual(r[0]["key"], "elys-usv-wrong-folder")
        self.assertIn("OBSE\\Plugins", r[0]["detail"]["fix"])

    def test_q08_orc_hang_is_a_hypothesis(self):
        # Does the ORC FPS limiter cause hangs? (must not be presented as fact)
        r = top("Oblivion Reloaded FPS limiter hang", 1)
        self.assertEqual(r[0]["key"], "orc-fps-limiter-hang")
        self.assertEqual(r[0]["confidence"], "HYPOTHESIS")

    def test_q09_event_handler_version(self):
        # Which OBSE version added SetEventHandler, and what does it take?
        f = q.func("SetEventHandler", DB)
        self.assertEqual(f["obse_version"], 19)
        self.assertEqual([p["name"] for p in f["params"]][:2], ["event name", "function script"])

    def test_q10_npc_spell_list(self):
        # Which NPC_ subrecord lists spells, and what may it point to?
        rec = q.record("NPC_", DB)
        splo = next(s for s in rec["subrecords"] if s["sub_sig"] == "SPLO")
        self.assertTrue(splo["formid"] and splo["repeating"])
        self.assertEqual(set(splo["formid_targets"].split(",")), {"SPEL", "LVSP"})

    def test_q11_acbs_level_offset(self):
        # Where is the level stored in NPC_ ACBS?
        rec = q.record("NPC_", DB)
        acbs = next(s for s in rec["subrecords"] if s["sub_sig"] == "ACBS")
        lvl = next(f for f in acbs["fields"] if f["name"].startswith("Level"))
        self.assertEqual((lvl["offset"], lvl["size"], lvl["type"]), (10, 2, "itS16"))   # patchlib STRUCTS agree

    def test_q12_scan_projectiles(self):
        # How do I find the projectiles near the player?
        r = top("How do I find the projectiles flying near the player?", 5)
        self.assertTrue({"GetFirstRef", "Projectile Manipulating Magic (aaBlazesPlusMod)",
                         "Cross-cutting: Projectile capability exists in OBSE today"} & set(keys(r)))

    def test_q13_force_weather(self):
        # How do I force a thunderstorm?
        self.assertEqual(keys(top("How do I force a thunderstorm?", 1)), ["ForceWeather"])

    def test_q14_soft_dependency(self):
        # How do I use another plugin's form without making it a master?
        r = keys(top("How do I use another plugin's form without making it a master? soft dependency", 3))
        self.assertTrue({"GetFormFromMod", "IsModLoaded"} & set(r[:2]), r)


class PCQuestions(unittest.TestCase):
    """Need the local vanilla export (Bethesda-derived, never committed)."""

    def setUp(self):
        if not vanilla_rows():
            self.skipTest("no vanilla_index.jsonl: run scripts\\kb\\Build forge KB.bat on the PC")

    def test_q15_daedric_longsword_formid(self):
        # What is the FormID of WeapDaedricLongsword?
        rows = [r for r in q.form("WeapDaedricLongsword", DB) if not r["override"]]
        self.assertEqual(len(rows), 1, rows)
        r = rows[0]
        print(f"\n    WeapDaedricLongsword = {r['plugin']}:{r['formid']} ({r['full']})", end="")
        self.assertEqual((r["plugin"], r["sig"], r["full"]), ("Oblivion.esm", "WEAP", "Daedric Longsword"))
        self.assertTrue(r["formid"].startswith("00"))

    def test_q16_weather_records(self):
        # Which WTHR records exist?
        rows = q.forms_of_type("WTHR", DB)
        edids = {r["edid"].lower() for r in rows}
        print(f"\n    {len(rows)} WTHR records, e.g. {sorted(edids)[:6]}", end="")
        self.assertGreaterEqual(len(rows), 10)
        self.assertTrue({"clear", "thunderstorm"} <= edids, sorted(edids))

    def test_q17_player_base_formid(self):
        # Which record is FormID 00000007?
        r = q.form("00000007", DB)
        self.assertEqual((r[0]["sig"], r[0]["edid"]), ("NPC_", "Player"))

    def test_q18_gold(self):
        # What is gold's FormID?
        r = q.form("Gold001", DB)
        self.assertEqual((r[0]["formid"], r[0]["sig"]), ("0000000F", "MISC"))

    def test_q19_shivering_isles_in_esm(self):
        # Where do Shivering Isles records live in the GOTY build?
        r = [x for x in q.form("SEWorld", DB) if not x["override"]]
        self.assertEqual((r[0]["plugin"], r[0]["sig"]), ("Oblivion.esm", "WRLD"))

    def test_q20_vanilla_positionworld_params(self):
        # What parameters does vanilla PositionWorld take? (from the game's own command table)
        if not exe_commands():
            self.skipTest("no vanilla_commands.jsonl: run forge kb export-commands on the PC")
        f = q.func("PositionWorld", DB)
        print(f"\n    PositionWorld {[(p['name'], p['type']) for p in f['params']]}", end="")
        self.assertGreaterEqual(len(f["params"]), 5)
        self.assertEqual(f["params"][-1]["type"], "WorldSpace")
        self.assertEqual(f["confidence"], "CONFIRMED_MULTI_SOURCE")


class Integrity(unittest.TestCase):
    """Every row carries a source and an allowed confidence."""

    def test_every_row_has_source_and_confidence(self):
        with closing(sqlite3.connect(DB)) as c:
            for t in ("record_types", "subrecords", "subrecord_fields", "functions", "function_params",
                      "vanilla_forms", "techniques", "crash_signatures", "test_results"):
                bad = c.execute(f"SELECT COUNT(*) FROM {t} WHERE source IS NULL OR source = '' OR "
                                f"confidence NOT IN ({','.join('?' * len(CONFIDENCE))})", CONFIDENCE).fetchone()[0]
                self.assertEqual(bad, 0, t)
            for t in ("engine_classes", "engine_fields", "engine_functions"):
                cols = {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
                self.assertTrue({"source", "confidence"} <= cols, t)

    def test_no_copied_doc_text_in_committed_data(self):
        # signatures only: no help strings from xOBSE in the committed JSON
        import json
        rows = json.loads((kbuild.DATA / "obse_functions.json").read_text(encoding="utf-8"))
        self.assertTrue(all(set(r) <= {"name", "alias", "category", "ref_required", "return_type", "params",
                                       "params_unparsed", "obse_version", "deprecated", "conditional", "file"}
                            for r in rows))


if __name__ == "__main__":
    unittest.main()
