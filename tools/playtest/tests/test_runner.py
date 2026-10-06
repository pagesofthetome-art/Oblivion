"""End to end with a fake game: profile on, quick boot, batches, checks, restore."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from playtest.tests.base import MachineCase
from playtest import runner
from playtest.tests.fakegame import FakePlatform

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "example-firebolt.yaml"


class RunnerTests(MachineCase):
    def setUp(self):
        super().setUp()
        self.logs: list[str] = []
        # the kit needs numpy; the runner tests stage a tiny stand-in kit instead
        kit = self.m.state_dir / "testcells" / "Data"
        (kit / "meshes" / "forge" / "testcells").mkdir(parents=True)
        (kit / "meshes" / "forge" / "testcells" / "floor.nif").write_bytes(b"nif")
        (kit / "kit.ok").write_text("meshes/forge/testcells/floor.nif")
        (self.m.data / "OBSE" / "Plugins").mkdir(parents=True)
        (self.m.data / "OBSE" / "Plugins" / "NorthernUI.dll").write_bytes(b"dll")
        self.gog_before = __import__("playtest.tests.base", fromlist=["tree_hash"]).tree_hash(self.fx["gog"])

    def opts(self, **kw):
        o = runner.Options(log=self.logs.append, quit_when_done=True, **kw)
        return o

    def test_example_passes_boots_fast_and_restores(self):
        p = FakePlatform(self.m.game_dir)
        res = runner.run(EXAMPLE, self.opts(), self.m, p)
        self.assertEqual(res["verdict"], "PASS", "\n".join(self.logs) + json.dumps(res, indent=1))
        self.assertLess(res["boot_seconds"], 30)
        self.assertEqual(res["checks"], 4)
        self.assertTrue(all(v["same"] for v in res["restore_check"].values()))
        self.assertRealSetupUntouched()
        hist = p.game.history
        self.assertEqual(hist[0], "coc ForgeTestArena")
        self.assertIn("bat fpt1", hist)
        self.assertIn("bat fpt2", hist)
        self.assertFalse([h for h in hist if h.startswith("GAME KEYS")], "typed into the game, not the console")
        self.assertTrue(any("guardian.py" in " ".join(a) for a in p.spawned))
        run = Path(res["run_dir"])
        self.assertTrue((run / "forge_test.log").is_file())
        self.assertTrue((run / "playtest_manifest.json").is_file())

    def test_spell_that_does_nothing_fails(self):
        p = FakePlatform(self.m.game_dir, {"damage": 0.0})
        res = runner.run(EXAMPLE, self.opts(), self.m, p)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertRealSetupUntouched()

    def test_freeze_is_killed_and_restored(self):
        p = FakePlatform(self.m.game_dir, {"freeze_at": 7.0})
        res = runner.run(EXAMPLE, self.opts(hang_seconds=5), self.m, p)
        self.assertEqual(res["verdict"], "FROZE")
        self.assertIn(p.GAME_PID, p.killed)
        self.assertRealSetupUntouched()

    def test_refuses_while_yuris_game_runs(self):
        steam_exe = str(self.fx["steam"] / "Oblivion.exe")
        p = FakePlatform(self.m.game_dir, others=[(77, "Oblivion.exe", steam_exe)])
        with self.assertRaises(runner.PlaytestError):
            runner.run(EXAMPLE, self.opts(), self.m, p)
        self.assertEqual(p.launched, 0)
        self.assertRealSetupUntouched()

    def test_dry_run_swaps_and_restores(self):
        p = FakePlatform(self.m.game_dir)
        res = runner.run(EXAMPLE, self.opts(dry_run=True), self.m, p)
        self.assertEqual(res["verdict"], "DRY-RUN")
        self.assertEqual(p.launched, 0)
        self.assertRealSetupUntouched()

    def test_forge_crash_mid_run_still_restores(self):
        class Boom(FakePlatform):
            def launch(self, exe, cwd):
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            runner.run(EXAMPLE, self.opts(), self.m, Boom(self.m.game_dir))
        self.assertRealSetupUntouched()

    def test_leftover_journal_is_restored_first(self):
        from playtest import profile
        s = profile.Session(self.m, log=lambda x: None)
        s.begin()
        s.swap_in(self.m.plugins_txt, b"garbage")       # a previous run died here
        res = runner.run(EXAMPLE, self.opts(dry_run=True), self.m, FakePlatform(self.m.game_dir))
        self.assertEqual(res["verdict"], "DRY-RUN")
        self.assertRealSetupUntouched()

    def test_masters_come_from_the_play_copy_read_only(self):
        from playtest.tests import fixtures
        mod = fixtures.tiny_esp(self.tmp / "work" / "NeedsRebirth.esp", ["Oblivion.esm", "RebirthPlus.esp"])
        plan = self.tmp / "work" / "NeedsRebirth.playtest.json"
        plan.write_text(json.dumps({"test_plan": {"cell": "street", "steps": [
            {"check": {"ref": "player", "fn": "GetInCell", "args": ["ForgeTestStreet"], "expect": "== 1"}}]}}))
        p = FakePlatform(self.m.game_dir)
        res = runner.run(mod, self.opts(), self.m, p)
        man = json.loads((Path(res["run_dir"]) / "playtest_manifest.json").read_text())
        self.assertEqual(man["load_order"][-3:], ["RebirthPlus.esp", "NeedsRebirth.esp", "ForgeTestCells.esp"])
        self.assertEqual(res["verdict"], "PASS", json.dumps(res, indent=1))
        self.assertRealSetupUntouched()


if __name__ == "__main__":
    unittest.main()
