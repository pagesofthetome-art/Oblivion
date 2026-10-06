"""forge preview page building, and the forge CLI wiring (playtest / test / preview)."""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from playtest.tests.base import MachineCase
from playtest import preview, testcells
from playtest.tests import fixtures

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "example-firebolt.yaml"


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="preview-"))
        cls.esp, _ = testcells.write(cls.dir)

    def test_extract_cells_refs_and_schedules(self):
        d = preview.extract(self.esp)
        cells = {c["edid"]: c for c in d["cells"]}
        self.assertEqual(set(cells), {"ForgeTestArena", "ForgeTestStreet", "ForgeTestOpen"})
        street = cells["ForgeTestStreet"]
        self.assertTrue(street["exterior"])
        merchant = next(i for i in street["items"] if i.get("edid") == "ForgeStreetMerchantRef")
        hours = [p["hours"] for p in merchant["npc"]["packages"]]
        self.assertEqual(hours, ["08:00-20:00", "20:00-08:00"])
        self.assertTrue(merchant["npc"]["packages"][0]["offers_services"])
        self.assertIn("ForgeStreetStallRef", merchant["npc"]["packages"][0]["where"])
        door = next(i for i in street["items"] if i.get("edid") == "ForgeStreetDoorRef")
        self.assertEqual(door["teleport"], "ForgeArenaDoorRef")
        arena = cells["ForgeTestArena"]
        self.assertAlmostEqual(arena["start"]["y"], -768)

    def test_page_from_shared_template(self):
        out = preview.build_page(self.esp, self.dir / "p.html", "Forge test cells", "ForgeTestArena")
        html = out.read_text(encoding="utf-8")
        tpl = preview.TEMPLATE.read_text(encoding="utf-8")
        engine = tpl[tpl.index("PREVIEW ENGINE (reusable)"):tpl.index("TEST LOCATION (reusable)")]
        self.assertIn(engine[:4000], html, "the template engine is reused unchanged")
        self.assertIn("SoftRenderer", html)                       # canvas fallback
        self.assertIn("WebGLRenderer", html)
        self.assertIn("E.clamp(pp)", html)
        self.assertNotIn("Crimson Grasp", html)
        self.assertIn('"edid":"ForgeTestArena"', html)
        self.assertIn("getGamepads", html)
        self.assertEqual(html.count("<title>"), 1)
        data = json.loads(re.search(r"const PV=(\{.*?\});const U=70;", html).group(1))
        self.assertEqual(len(data["cells"]), 3)

    def test_broken_template_is_an_error(self):
        bad = self.dir / "bad.html"
        bad.write_text("<html>no sections</html>")
        with self.assertRaises(preview.PreviewError):
            preview.render(preview.extract(self.esp), "t", "s", template=bad)

    def test_plugin_without_placed_objects(self):
        p = fixtures.tiny_esp(self.dir / "NoCells.esp", ["Oblivion.esm"])
        with self.assertRaises(preview.PreviewError):
            preview.build_page(p, self.dir / "n.html")


def forge(*args) -> tuple[int, str, str]:
    from forge import cli
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class CliTests(MachineCase):
    def env(self):
        return mock.patch.dict(os.environ, {
            "FORGE_PLAYTEST_PLUGINS_TXT": str(self.m.plugins_txt), "FORGE_PLAYTEST_INI": str(self.m.ini),
            "FORGE_PLAYTEST_GAME_DIR": str(self.m.game_dir), "FORGE_PLAYTEST_STATE_DIR": str(self.m.state_dir),
            "FORGE_PLAYTEST_STEAM_DIR": str(self.fx["steam"]), "APPDATA": str(self.tmp / "AppData" / "Roaming")})

    def stub_kit(self):
        kit = self.m.state_dir / "testcells" / "Data"
        kit.mkdir(parents=True)
        (kit / "kit.ok").write_text("")

    def test_dry_run_leaves_everything_byte_identical(self):
        self.stub_kit()
        with self.env():
            code, out, err = forge("playtest", str(EXAMPLE), "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("restore: plugins_txt identical", out)
        self.assertRealSetupUntouched()

    def test_status_restore_and_cells(self):
        self.stub_kit()
        with self.env():
            self.assertIn("off", forge("playtest", "status")[1])
            self.assertIn("nothing to restore", forge("playtest", "restore")[1])
            code, out, _ = forge("playtest", "cells")
        self.assertEqual(code, 0)
        self.assertIn("arena = ForgeTestArena", out)

    def test_forge_test_reads_a_run(self):
        from playtest.tests.test_manifest_log import log_text, manifest
        run = self.tmp / "run"
        run.mkdir()
        m = manifest()
        (run / "playtest_manifest.json").write_text(json.dumps(m))
        (run / "forge_test.log").write_text(log_text(m))
        with self.env():
            code, out, _ = forge("test", str(run))
            self.assertEqual(code, 0, out)
            self.assertIn("forge test: PASS", out)
            (run / "forge_test.log").write_text(log_text(m, health_after=500))
            code, out, _ = forge("test", str(run), "--json")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["verdict"], "FAIL")

    def test_preview_command(self):
        with self.env():
            code, out, err = forge("preview", str(EXAMPLE), "--out", str(self.tmp / "pv.html"))
        self.assertEqual(code, 0, out + err)
        html = (self.tmp / "pv.html").read_text(encoding="utf-8")
        self.assertIn("ForgeTestArena", html)
        self.assertIn("example-firebolt", html)

    def test_bad_target(self):
        with self.env():
            code, _, err = forge("playtest", str(self.tmp / "missing.esp"), "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)


if __name__ == "__main__":
    unittest.main()
