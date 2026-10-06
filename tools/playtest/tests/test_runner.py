"""End to end with a fake game: profile on, quick boot into a vanilla cell, batches, checks, restore."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from playtest.tests.base import MachineCase, tree_hash
from playtest import profile, runner
from playtest.tests import fixtures
from playtest.tests.fakegame import FakePlatform

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "example-firebolt.yaml"


class RunnerTests(MachineCase):
    def setUp(self):
        super().setUp()
        self.logs: list[str] = []
        (self.m.data / "OBSE" / "Plugins").mkdir(parents=True)
        (self.m.data / "OBSE" / "Plugins" / "NorthernUI.dll").write_bytes(b"dll")
        (self.m.data / "OBSE" / "Plugins" / "NorthernUI.ini").write_bytes(b"[GOG fresh]\r\nbCursor=1\r\n")
        steam_nui = self.fx["steam"] / "Data" / "OBSE" / "Plugins"
        steam_nui.mkdir(parents=True)
        (steam_nui / "NorthernUI.ini").write_bytes(b"[Yuri play setup]\r\nbCursor=0\r\n")
        self.gog_before = tree_hash(self.fx["gog"])
        self.steam_before = tree_hash(self.fx["steam"])

    def opts(self, **kw):
        return runner.Options(log=self.logs.append, **kw)

    def fake(self, **behaviour):
        behaviour.setdefault("save_dir", str(self.m.save_dir))
        behaviour.setdefault("continue_after", 3.0)            # Yuri presses Continue at the beep
        return FakePlatform(self.m.game_dir, behaviour)

    def with_save(self):
        self.m.save_dir.mkdir(parents=True, exist_ok=True)
        (self.m.save_dir / "ForgePlaytestBase.ess").write_bytes(b"save")

    def test_example_boots_into_the_vanilla_arena_and_passes(self):
        self.with_save()
        p = self.fake()
        res = runner.run(EXAMPLE, self.opts(), self.m, p)
        self.assertEqual(res["verdict"], "PASS", "\n".join(self.logs) + json.dumps(res, indent=1))
        self.assertLess(res["boot_seconds"], 30)
        self.assertEqual(res["boot_strategy"], "B: Continue + in-game console")
        self.assertEqual(res["location"]["boot"], "coc ICArena")
        self.assertTrue(all(v["same"] for v in res["restore_check"].values()))
        self.assertRealSetupUntouched()
        hist = p.game.history
        self.assertEqual(hist[0], "coc ICArena")
        self.assertIn("bat fpt1", hist)
        self.assertNotIn("qqq", hist, "forge never closes the game")
        self.assertEqual(p.killed, [])
        self.assertTrue(p.game.messages and "quit the game when you are ready" in p.game.messages[-1])
        self.assertTrue(any("Quit the game with the pad" in l for l in self.logs))
        self.assertIn("ForgeArenaDummyRef.moveto player 0 600 0", hist, "dummy brought to the player by EditorID")
        self.assertFalse([h for h in hist if re.match(r"^[0-9A-F]{8}\.", h) or h.startswith("prid")])
        self.assertEqual(res["log_source"], str(self.m.game_dir / "forge_test.log"))
        self.assertFalse(list(self.m.save_dir.glob("ForgePlaytestResult.*")), "result save removed")
        self.assertFalse([h for h in hist if h.startswith("GAME KEYS")], "typed into the game, not the console")
        run = Path(res["run_dir"])
        shots = sorted(x.name for x in (run / "shots").iterdir())
        for f in ("forge_test.log", "playtest_manifest.json", "boot-trace.jsonl", "Plugins.test.txt",
                  "Oblivion.test.ini"):
            self.assertTrue((run / f).is_file(), f)
        self.assertTrue(any("main-menu" in s for s in shots) and any("in-game" in s for s in shots), shots)
        self.assertTrue(any("output-fpt1" in x for x in shots), "console photographed after each batch")
        trace = (run / "boot-trace.jsonl").read_text()
        self.assertIn("game closed by the player", trace)
        ini = (run / "Oblivion.test.ini").read_bytes().decode("cp1252")
        for line in ("iSize W=1280", "iSize H=720", "bFull Screen=0", "bUse Joystick=0", "SIntroSequence="):
            self.assertIn(line, ini)
        self.assertTrue(getattr(p, "borderless", False), "window made borderless")
        companion = [a for a in p.spawned if "oblivion_controller.py" in " ".join(a)]
        self.assertTrue(companion and companion[0][-2:] == ["--mode", "northernui"], companion)
        self.assertTrue(any("NorthernUI.ini" in l for l in self.logs))
        plugins = (run / "Plugins.test.txt").read_text().split()
        self.assertEqual([x for x in plugins if x.endswith((".esm", ".esp"))],
                         ["Oblivion.esm", "DLCShiveringIsles.esp", "ForgeExampleFirebolt.esp", "ForgeTestCells.esp"])

    def test_without_any_log_file_the_result_save_decides(self):
        self.with_save()
        res = runner.run(EXAMPLE, self.opts(), self.m, self.fake(logger="none"))
        self.assertEqual(res["verdict"], "PASS", json.dumps(res, indent=1))
        self.assertIn("result save", res["log_source"])
        self.assertEqual(res["save_values"]["ForgeRInPlace"], 1.0)
        self.assertRealSetupUntouched()

    def test_a_log_with_markers_only_falls_back_to_the_result_save(self):
        self.with_save()
        res = runner.run(EXAMPLE, self.opts(), self.m, self.fake(logger="conscribe"))
        self.assertEqual(res["verdict"], "PASS", json.dumps(res, indent=1))
        self.assertIn("result save", res["log_source"])

    def test_no_log_and_no_result_save_is_not_a_pass(self):
        self.with_save()
        import playtest.tests.fakegame as fg
        old = fg.FakeGame._save
        fg.FakeGame._save = lambda self_, name: None
        try:
            res = runner.run(EXAMPLE, self.opts(), self.m, self.fake(logger="none"))
        finally:
            fg.FakeGame._save = old
        self.assertEqual(res["verdict"], "NOT-RUN")
        self.assertRealSetupUntouched()

    def test_street_is_a_real_exterior(self):
        self.with_save()
        p = self.fake()
        res = runner.run(EXAMPLE, self.opts(cell="street"), self.m, p)
        self.assertEqual(p.game.history[0], "cow ICMarketDistrict 10 6")
        self.assertIn("player.setpos x 41000.0", p.game.history, "stands where the shop door lets you out")
        self.assertEqual(res["verdict"], "PASS", json.dumps(res, indent=1))
        self.assertRealSetupUntouched()

    def test_no_save_stops_before_launching(self):
        p = self.fake()
        with self.assertRaises(runner.PlaytestError) as cm:
            runner.run(EXAMPLE, self.opts(), self.m, p)
        self.assertIn("make-save", str(cm.exception))
        self.assertEqual(p.launched, 0, "no game started without a test save")
        self.assertRealSetupUntouched()

    def test_no_keys_at_the_main_menu(self):
        self.with_save()
        p = self.fake(continue_after=8.0)
        runner.run(EXAMPLE, self.opts(), self.m, p)
        self.assertFalse([h for h in p.game.history if h.startswith("GAME KEYS")])

    def test_make_save_waits_for_chargen_and_the_player(self):
        self.m.save_dir.mkdir(parents=True)
        (self.m.save_dir / "ForgePlaytestBase.ess").write_bytes(b"old good save")
        (self.m.save_dir / "autosave.ess").write_bytes(b"old")
        p = self.fake(new_game_after=20.0, chargen_seconds=30.0, continue_after=None)
        res = runner.make_save(self.opts(), self.m, p)
        self.assertTrue(res["made"], res)
        self.assertEqual(sorted(f.name for f in self.m.save_dir.iterdir()), ["ForgePlaytestBase.ess"])
        self.assertNotEqual((self.m.save_dir / "ForgePlaytestBase.ess").read_bytes(), b"old good save",
                            "replaced by the new one")
        self.assertEqual(res["save_in_place"], 1.0, "location confirmed by the new save's own global")
        hist = p.game.history
        self.assertLess(hist.index("coc ICArena"), hist.index("save ForgePlaytestNew"))
        self.assertNotIn("qqq", hist)
        trace = (Path(res["run_dir"]) / "boot-trace.jsonl").read_text()
        self.assertIn("character screen done", trace)
        self.assertIn("game closed by the player", trace)
        self.assertRealSetupUntouched()

    def test_make_save_keeps_the_old_save_when_the_new_one_is_wrong(self):
        self.m.save_dir.mkdir(parents=True)
        (self.m.save_dir / "ForgePlaytestBase.ess").write_bytes(b"old good save")
        p = self.fake(new_game_after=20.0, chargen_seconds=30.0, continue_after=None)
        # the coc lands somewhere else: GetInCell answers 0
        import playtest.tests.fakegame as fg
        old_run = fg.FakeGame.run

        def run(self_, cmd):
            if cmd.lower().startswith("coc "):
                cmd = "coc SomewhereElse"
            return old_run(self_, cmd)
        fg.FakeGame.run = run
        try:
            res = runner.make_save(self.opts(), self.m, p)
        finally:
            fg.FakeGame.run = old_run
        self.assertFalse(res["made"])
        self.assertIn("not confirmed", res["error"])
        self.assertEqual((self.m.save_dir / "ForgePlaytestBase.ess").read_bytes(), b"old good save")
        self.assertFalse(list(self.m.save_dir.glob("ForgePlaytestNew.*")))
        self.assertRealSetupUntouched()

    def test_save_from_before_chargen_is_reported(self):
        self.with_save()
        p = self.fake(continue_after=3.0, save_before_chargen=True)
        res = runner.run(EXAMPLE, self.opts(), self.m, p)
        self.assertEqual(res["verdict"], "NOT-RUN")
        self.assertIn("before character creation", res["error"])
        self.assertEqual(p.killed, [])
        self.assertRealSetupUntouched()

    def test_dpi_flag_of_the_play_copy_is_mirrored_for_the_run(self):
        self.with_save()
        steam_exe = str(self.fx["steam"] / "Oblivion.exe")
        self.m.layers = profile.MemoryLayers(user={steam_exe: "~ HIGHDPIAWARE"})
        p = self.fake()
        p.scale = 1.5
        seen = {}
        orig = p.launch

        def launch(exe, cwd):
            seen.update(self.m.layers.user)
            orig(exe, cwd)
        p.launch = launch
        res = runner.run(EXAMPLE, self.opts(), self.m, p)
        gog_exe = str(self.m.game_dir / "Oblivion.exe")
        self.assertEqual(seen.get(gog_exe), "~ HIGHDPIAWARE", "flag set while the game runs")
        self.assertEqual(self.m.layers.user, {steam_exe: "~ HIGHDPIAWARE"}, "and removed afterwards")
        ini = (Path(res["run_dir"]) / "Oblivion.test.ini").read_bytes().decode("cp1252")
        self.assertIn("iSize W=1920", ini)
        self.assertRealSetupUntouched()

    def test_without_a_dpi_flag_the_test_renders_at_the_logical_size(self):
        self.m.layers = profile.MemoryLayers()
        p = self.fake()
        p.scale = 1.5
        res = runner.run(EXAMPLE, self.opts(dry_run=True), self.m, p)
        ini = (Path(res["run_dir"]) / "Oblivion.test.ini").read_bytes().decode("cp1252")
        self.assertIn("iSize W=1280", ini)
        self.assertIn("iSize H=720", ini)
        self.assertEqual(self.m.layers.user, {})

    def test_bright_option(self):
        res = runner.run(EXAMPLE, self.opts(bright=True, dry_run=True), self.m, self.fake())
        ini = (Path(res["run_dir"]) / "Oblivion.test.ini").read_bytes().decode("cp1252")
        self.assertIn("bFullBrightLighting=1", ini)
        self.assertRealSetupUntouched()

    def test_discord_note(self):
        p = self.fake()
        p.others = [(55, "Discord.exe", "C:/x/Discord.exe")]
        runner.run(EXAMPLE, self.opts(dry_run=True), self.m, p)
        self.assertTrue(any("Discord" in l for l in self.logs))

    def test_spell_that_does_nothing_fails(self):
        self.with_save()
        res = runner.run(EXAMPLE, self.opts(), self.m, self.fake(damage=0.0))
        self.assertEqual(res["verdict"], "FAIL")
        self.assertRealSetupUntouched()

    def test_freeze_is_reported_not_killed(self):
        self.with_save()
        p = self.fake(freeze_at=12.0)
        res = runner.run(EXAMPLE, self.opts(hang_seconds=5), self.m, p)
        self.assertEqual(res["verdict"], "FROZE")
        self.assertEqual(p.killed, [], "forge never closes the game; Yuri does")
        self.assertRealSetupUntouched()

    def test_freeze_kill_is_opt_in(self):
        self.with_save()
        p = self.fake(freeze_at=12.0)
        res = runner.run(EXAMPLE, self.opts(hang_seconds=5, kill_on_freeze=True), self.m, p)
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
        p = self.fake()
        res = runner.run(EXAMPLE, self.opts(dry_run=True), self.m, p)
        self.assertEqual(res["verdict"], "DRY-RUN")
        self.assertEqual(p.launched, 0)
        self.assertRealSetupUntouched()

    def test_forge_crash_before_the_game_starts_still_restores(self):
        self.with_save()

        class Boom(FakePlatform):
            def launch(self, exe, cwd):
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            runner.run(EXAMPLE, self.opts(), self.m, Boom(self.m.game_dir, {"save_dir": str(self.m.save_dir)}))
        self.assertRealSetupUntouched()

    def test_forge_interrupted_while_the_game_runs_leaves_restore_to_the_guardian(self):
        self.with_save()
        p = self.fake()
        orig_idle = runner.Driver.idle

        def boom(self_, seconds):
            raise KeyboardInterrupt
        runner.Driver.idle = boom
        try:
            with self.assertRaises(KeyboardInterrupt):
                runner.run(EXAMPLE, self.opts(), self.m, p)
        finally:
            runner.Driver.idle = orig_idle
        self.assertTrue(p.game.alive)
        self.assertTrue(self.m.journal.exists(), "not restored under the running game")
        p.game.alive = False                                  # Yuri quits; the guardian restores
        from playtest import guardian
        guardian.watch(self.m, p.GAME_PID, None, p, poll=0.01)
        self.assertRealSetupUntouched()

    def test_leftover_journal_is_restored_first(self):
        s = profile.Session(self.m, log=lambda x: None)
        s.begin()
        s.swap_in(self.m.plugins_txt, b"garbage")       # a previous run died here
        res = runner.run(EXAMPLE, self.opts(dry_run=True), self.m, self.fake())
        self.assertEqual(res["verdict"], "DRY-RUN")
        self.assertRealSetupUntouched()

    def test_masters_come_from_the_play_copy_read_only(self):
        self.with_save()
        mod = fixtures.tiny_esp(self.tmp / "work" / "NeedsRebirth.esp", ["Oblivion.esm", "RebirthPlus.esp"])
        plan = self.tmp / "work" / "NeedsRebirth.playtest.json"
        plan.write_text(json.dumps({"test_plan": {"cell": "arena", "steps": [
            {"check": {"ref": "ForgeArenaDummyRef", "fn": "GetDead", "expect": "== 0"}}]}}))
        res = runner.run(mod, self.opts(), self.m, self.fake())
        man = json.loads((Path(res["run_dir"]) / "playtest_manifest.json").read_text())
        self.assertEqual(man["load_order"][-3:], ["RebirthPlus.esp", "NeedsRebirth.esp", "ForgeTestCells.esp"])
        self.assertEqual(res["verdict"], "PASS", json.dumps(res, indent=1))
        self.assertRealSetupUntouched()


class MachineDetectTests(MachineCase):
    def test_sibling_gog_copy_is_found(self):
        repo = self.tmp / "Games" / "Oblivion-repo"          # Yuri's clone next to the GOG copy
        repo.mkdir(parents=True)
        m = profile.Machine.detect(env={"USERPROFILE": str(self.tmp)}, repo=repo)
        self.assertEqual(m.game_dir, self.fx["gog"])

    def test_machine_json_overrides(self):
        repo = self.tmp / "elsewhere"
        state = repo / "forge-builds" / "playtest"
        state.mkdir(parents=True)
        (state / "machine.json").write_text(json.dumps({"game_dir": str(self.fx["gog"])}))
        m = profile.Machine.detect(env={"USERPROFILE": str(self.tmp)}, repo=repo)
        self.assertEqual(m.game_dir, self.fx["gog"])


if __name__ == "__main__":
    unittest.main()
