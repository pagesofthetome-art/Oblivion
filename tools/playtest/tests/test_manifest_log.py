"""Manifest parsing/compiling and forge_test.log parsing on fixture data."""

from __future__ import annotations

import unittest
from pathlib import Path

from playtest.tests import base  # noqa: F401  (sys.path)
from playtest import manifest as mf, testlog

PLAN = {
    "cell": "arena",
    "steps": [
        {"addspell": "ForgeExampleFireboltSpell"},
        {"check": {"ref": "player", "fn": "HasSpell", "args": ["ForgeExampleFireboltSpell"], "expect": "== 1"}},
        {"check": {"ref": "ForgeArenaDummyRef", "fn": "GetAV", "args": ["Health"], "save": "hp"}},
        {"cast": {"caster": "ForgeArenaCasterRef", "spell": "ForgeExampleFireboltSpell", "target": "ForgeArenaDummyRef"}},
        {"wait": 3},
        {"check": {"ref": "ForgeArenaDummyRef", "fn": "GetAV", "args": ["Health"], "expect": "< $hp"}},
        {"additem": {"form": "Gold001", "count": 100}},
    ],
}
LO = ["Oblivion.esm", "DLCShiveringIsles.esp", "ForgeExampleFirebolt.esp", "ForgeTestCells.esp"]


def forms() -> mf.FormTable:
    ft = mf.FormTable(LO, {"ForgeExampleFirebolt.esp": ["Oblivion.esm"], "ForgeTestCells.esp": ["Oblivion.esm"]})
    ft.add_plugin_records("ForgeExampleFirebolt.esp", [("ForgeExampleFireboltSpell", 0x01000800, "SPEL")])
    ft.add_plugin_records("ForgeTestCells.esp", [("ForgeArenaDummyRef", 0x0100081A, "ACHR"),
                                                 ("ForgeArenaCasterRef", 0x0100081B, "ACHR"),
                                                 ("ForgeStreet", 0x01000810, "CELL")])
    ft.add_plugin_records("Oblivion.esm", [("Gold001", 0x0000000F, "MISC")])
    return ft


LOC = {"key": "arena", "label": "Arena", "boot": "coc ArenaArena", "moveto": None, "cell_edid": "ArenaArena",
       "world_edid": None, "detail": ""}
BRING = [("ForgeArenaDummyRef", 0, 600, 0), ("ForgeArenaCasterRef", 200, 100, 0)]


def manifest(run_id="abcd1234", location=LOC):
    return mf.build(mf.parse_plan(PLAN), forms(), location=location, bring=BRING,
                    plugin="ForgeExampleFirebolt.esp", spec="example-firebolt", run_id=run_id)


class ManifestTests(unittest.TestCase):
    def test_compile_resolves_load_order_formids_and_splits_at_waits(self):
        m = manifest()
        self.assertEqual(len(m["chunks"]), 2)
        self.assertEqual(m["chunks"][1]["wait_before"], 3.0)
        first, second = m["chunks"][0]["lines"], m["chunks"][1]["lines"]
        self.assertEqual(first[:7], ["con_SCOF forge_test.log", "scof forge_test.log", 'printc "FORGE|BEGIN|abcd1234"',
                                     "0300081A.moveto player 0 600 0", "0300081B.moveto player 200 100 0",
                                     'printc "FORGE|CELL|ArenaArena"', "player.GetInCell ArenaArena"])
        self.assertIn("player.addspell 02000800", first)
        self.assertIn("player.HasSpell 02000800", first)
        self.assertIn("0300081A.GetAV Health", first)
        self.assertIn("0300081B.cast 02000800 0300081A", first)
        self.assertIn("player.additem 0000000F 100", second)
        self.assertEqual(second[-2:], ['printc "FORGE|END|abcd1234"', "scof 0"])
        self.assertEqual([c["command"] for c in m["chunks"]], ["bat fpt1", "bat fpt2"])

    def test_exterior_location_moves_to_the_marker_and_probes_the_worldspace(self):
        loc = dict(LOC, key="street", boot="cow ICMarketDistrict 10 6", moveto="0000C002", cell_edid=None,
                   world_edid="ICMarketDistrict")
        lines = manifest(location=loc)["chunks"][0]["lines"]
        self.assertEqual(lines[3], "player.moveto 0000C002")
        self.assertIn("player.GetInWorldspace ICMarketDistrict", lines)

    def test_cell_arguments_stay_editor_ids(self):
        st = mf.parse_plan({"steps": [{"check": {"fn": "GetInCell", "args": ["ForgeStreet"], "expect": "== 1"}}]})
        m = mf.build(st, forms(), location=LOC, bring=[], plugin="x.esp", spec=None, run_id="r")
        self.assertIn("player.GetInCell ForgeStreet", m["chunks"][0]["lines"])

    def test_batch_files_are_crlf_cp1252(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        files = mf.write_batches(manifest(), d)
        self.assertEqual([f.name for f in files], ["fpt1.txt", "fpt2.txt"])
        self.assertIn(b"\r\n", files[0].read_bytes())

    def test_bad_plans_are_rejected(self):
        bad = [
            {"steps": ["cast a firebolt"]},
            {"steps": [{"explode": 1}]},
            {"steps": [{"wait": 0}]},
            {"steps": [{"check": {"fn": "GetAV"}}]},                       # no expect/save
            {"steps": [{"check": {"fn": "GetAV", "expect": "about 5"}}]},
            {"steps": [{"check": {"fn": "GetAV", "expect": "< $nope"}}]},   # used before saved
            {"steps": [{"console": "a\nb"}]},
            {"steps": [{"cast": {"spell": "X"}}]},
        ]
        for plan in bad:
            with self.assertRaises(mf.ManifestError, msg=str(plan)):
                mf.parse_plan(plan)

    def test_free_text_plan_has_no_checks(self):
        p = mf.parse_plan(["walk in, see a sword"])
        self.assertEqual(p["steps"], [])
        self.assertEqual(p["notes"], ["walk in, see a sword"])

    def test_unknown_form_is_an_error(self):
        with self.assertRaises(mf.ManifestError):
            forms().form("NoSuchThing")

    def test_console_id_quotes_scientific_lookalikes(self):
        self.assertEqual(mf.console_id(0x0001E500), '"0001E500"')
        self.assertEqual(mf.console_id(0x0300081A), "0300081A")

    def test_plugin_colon_id(self):
        self.assertEqual(forms().form("ForgeTestCells.esp:000ABC"), "03000ABC")

    def test_example_spec_plan_parses(self):
        import yaml
        spec = yaml.safe_load((Path(__file__).resolve().parents[1] / "examples" / "example-firebolt.yaml").read_text())
        plan = mf.parse_plan(spec["test_plan"])
        self.assertEqual(plan["cell"], "arena")
        self.assertEqual(sum(1 for s in plan["steps"] if s["do"] == "check"), 4)


def log_text(m, health_after=475.0, end=True, run_id=None, extra_error=None, in_cell=1.0, markers=True):
    rid = run_id or m["run_id"]
    lines = []
    def mk(t):
        if markers:
            lines.append(t)
    mk(f"FORGE|BEGIN|{rid}")
    mk("FORGE|CELL|ArenaArena")
    lines.append(f"GetInCell >> {in_cell:.2f}")
    mk("FORGE|STEP|1|addspell")
    mk("FORGE|STEP|2|check"); lines.append("HasSpell >> 1.00")
    mk("FORGE|STEP|3|check"); lines.append("GetActorValue >> 500.00")
    mk("FORGE|STEP|4|cast")
    if extra_error:
        lines.append(extra_error)
    mk("FORGE|STEP|6|check"); lines.append(f"GetActorValue >> {health_after:.2f}")
    mk("FORGE|STEP|7|additem")
    if end:
        mk(f"FORGE|END|{rid}")
    return "\n".join(lines) + "\n"


class LogTests(unittest.TestCase):
    def judge(self, text, extra=None):
        import tempfile
        p = Path(tempfile.mkdtemp()) / "forge_test.log"
        p.write_text(text, encoding="cp1252")
        return testlog.evaluate(manifest(), p, extra)

    def test_pass(self):
        r = self.judge(log_text(manifest()))
        self.assertEqual(r["verdict"], "PASS", testlog.report_text(r))
        self.assertEqual((r["passed"], r["checks"]), (2, 3))
        self.assertIn("PASS", testlog.report_text(r))

    def test_no_damage_fails(self):
        r = self.judge(log_text(manifest(), health_after=500.0))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("expected < 500", testlog.report_text(r))

    def test_missing_end_fails(self):
        self.assertEqual(self.judge(log_text(manifest(), end=False))["verdict"], "FAIL")

    def test_old_log_from_another_run_fails(self):
        r = self.judge(log_text(manifest(), run_id="deadbeef"))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertTrue(any("another run" in p for p in r["problems"]))

    def test_console_error_fails_the_step(self):
        r = self.judge(log_text(manifest(), extra_error='Script command "cast" not found.'))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual([x["status"] for x in r["results"] if x["n"] == 4], ["fail"])

    def test_wrong_cell_fails(self):
        self.assertEqual(self.judge(log_text(manifest(), in_cell=0.0))["verdict"], "FAIL")

    def test_without_xobse_markers_values_match_in_order(self):
        r = self.judge(log_text(manifest(), markers=False))
        self.assertEqual(r["verdict"], "FAIL", "unmarked logs pass checks but are flagged")
        self.assertTrue(all(x["status"] in ("pass", "saved", "ok") for x in r["results"]), r["results"])

    def test_no_log_is_not_run_and_launch_alone_is_no_pass(self):
        self.assertEqual(testlog.evaluate(manifest(), None)["verdict"], "NOT-RUN")
        empty = mf.build(mf.parse_plan({"steps": []}), forms(), location=LOC, bring=[], plugin="X.esp",
                         spec=None, run_id="r1")
        import tempfile
        p = Path(tempfile.mkdtemp()) / "l.log"
        p.write_text("FORGE|BEGIN|r1\nFORGE|CELL|ArenaArena\nGetInCell >> 1.00\nFORGE|END|r1\n")
        self.assertEqual(testlog.evaluate(empty, p)["verdict"], "NO-CHECKS")

    def test_froze_wins(self):
        self.assertEqual(self.judge(log_text(manifest()), {"froze": True})["verdict"], "FROZE")


if __name__ == "__main__":
    unittest.main()
