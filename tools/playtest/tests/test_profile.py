"""Test profile build and restore: the real Plugins.txt and Oblivion.ini must come back byte-identical."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from playtest.tests.base import MachineCase
from playtest import guardian, profile
from playtest.tests.fakegame import FakePlatform


class SwapRestoreTests(MachineCase):
    def swap(self) -> profile.Session:
        s = profile.Session(self.m, log=lambda x: None)
        s.begin()
        s.swap_in(self.m.plugins_txt, profile.plugins_txt(["Oblivion.esm", "Test.esp"]))
        s.swap_in(self.m.ini, profile.test_ini(self.real["ini"]))
        s.stage(self.m.data / "Test.esp", data=b"TES4fake")
        s.stage(self.m.data / "meshes" / "forge" / "a.nif", data=b"nif")
        s.collect(self.m.game_dir / "forge_test.log")
        return s

    def test_swap_then_restore_is_byte_identical(self):
        s = self.swap()
        self.assertNotEqual(self.fx["plugins_txt"].read_bytes(), self.real["plugins"])
        ini = self.fx["ini"].read_bytes().decode("cp1252")
        self.assertIn("SIntroSequence=\r\n", ini)
        self.assertIn("SLocalSavePath=Saves\\ForgePlaytest\\", ini)
        self.assertIn("iSize W=1920", ini, "the user's own settings stay in the test ini")
        (self.m.game_dir / "forge_test.log").write_text("game output")
        s.restore()
        self.assertRealSetupUntouched()
        self.assertFalse((self.m.data / "meshes").exists(), "created folders are removed")

    def test_restore_is_idempotent(self):
        self.swap().restore()
        self.assertEqual(profile.restore(self.m), [])
        self.assertRealSetupUntouched()

    def test_crash_recovery_from_journal(self):
        self.swap()                                       # forge "dies" here: nothing restored
        self.assertTrue(self.m.journal.exists())
        # the game rewrote the ini on exit, as Oblivion does
        self.fx["ini"].write_bytes(b"[General]\r\nSomethingNew=1\r\n")
        profile.restore(self.m, log=lambda x: None)      # next forge run / forge playtest restore
        self.assertRealSetupUntouched()

    def test_guardian_restores_when_game_and_forge_are_gone(self):
        s = self.swap()
        s.set_game_pid(4242)
        p = FakePlatform(self.m.game_dir)                 # no game, no forge: both dead
        self.assertEqual(guardian.watch(self.m, 4242, 31337, p, poll=0.01), "restored by guardian")
        self.assertRealSetupUntouched()

    def test_guardian_waits_while_the_game_runs(self):
        s = self.swap()
        p = FakePlatform(self.m.game_dir)
        p.launch(None, None)
        s.set_game_pid(p.GAME_PID)
        res = guardian.watch(self.m, p.GAME_PID, None, p, poll=1.0, max_hours=10 / 3600)
        self.assertEqual(res, "gave up (time limit)")
        self.assertTrue(self.m.journal.exists(), "never restores under a running game")
        profile.restore(self.m)

    def test_existing_file_is_never_overwritten(self):
        s = profile.Session(self.m, log=lambda x: None)
        s.begin()
        with self.assertRaises(profile.ProfileError):
            s.stage(self.m.data / "DLCShiveringIsles.esp", data=b"other")
        self.assertFalse(s.stage(self.m.data / "DLCShiveringIsles.esp",
                                 src=self.m.data / "DLCShiveringIsles.esp"), "identical file: left alone")
        s.restore()
        self.assertRealSetupUntouched()

    def test_changed_staged_file_is_left_and_reported(self):
        s = self.swap()
        (self.m.data / "Test.esp").write_bytes(b"edited during the test")
        notes = s.restore()
        self.assertTrue(any("changed during the test" in n for n in notes))
        (self.m.data / "Test.esp").unlink()
        self.assertRealSetupUntouched()

    def test_damaged_backup_keeps_the_journal(self):
        self.swap()
        j = json.loads(self.m.journal.read_text())
        Path(j["swaps"][0]["backup"]).write_bytes(b"corrupt")
        with self.assertRaises(profile.ProfileError):
            profile.restore(self.m, log=lambda x: None)
        self.assertTrue(self.m.journal.exists())

    def test_second_session_refused_while_journal_open(self):
        self.swap()
        with self.assertRaises(profile.ProfileError):
            profile.Session(self.m).begin()
        profile.restore(self.m, log=lambda x: None)


class SafetyTests(MachineCase):
    def test_steam_copy_refused_as_test_game(self):
        self.m.game_dir = self.fx["steam"]
        with self.assertRaises(profile.ProfileError):
            self.m.check_safe()

    def test_vortex_deployed_copy_refused(self):
        (self.m.data / "vortex.deployment.json").write_text("{}")
        with self.assertRaises(profile.ProfileError):
            self.m.check_safe()

    def test_writes_outside_the_test_game_refused(self):
        for bad in (self.fx["steam"] / "Data" / "x.esp", self.fx["vortex"] / "mods" / "x", self.tmp / "elsewhere.txt"):
            with self.assertRaises(profile.ProfileError, msg=str(bad)):
                self.m.check_writable(bad)
        self.m.check_writable(self.m.data / "ok.esp")

    def test_clean_gog_copy_accepted(self):
        self.m.check_safe()


class IniAndOrderTests(MachineCase):
    def test_ini_set_replaces_adds_and_keeps_crlf(self):
        t = "[General]\r\nA=1\r\n[Display]\r\nB=2\r\n"
        t = profile.ini_set(t, "General", "A", "9")
        t = profile.ini_set(t, "Display", "C", "3")
        t = profile.ini_set(t, "GamePlay", "D", "4")
        self.assertEqual(t, "[General]\r\nA=9\r\n[Display]\r\nB=2\r\nC=3\r\n[GamePlay]\r\nD=4\r\n")

    def test_plugins_txt_lists_only_the_profile(self):
        txt = profile.plugins_txt(["Oblivion.esm", "Mod.esp"]).decode()
        self.assertEqual([l for l in txt.splitlines() if not l.startswith("#")], ["Oblivion.esm", "Mod.esp"])

    def test_load_order_masters_first_then_mtime(self):
        d = self.m.data
        os.utime(d / "DLCShiveringIsles.esp", (5_000_000, 5_000_000))
        os.utime(d / "Oblivion.esm", (9_000_000, 9_000_000))
        self.assertEqual(profile.load_order(d, ["DLCShiveringIsles.esp", "Oblivion.esm"]),
                         ["Oblivion.esm", "DLCShiveringIsles.esp"])


if __name__ == "__main__":
    unittest.main()
