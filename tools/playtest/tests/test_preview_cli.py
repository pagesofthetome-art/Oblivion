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
        cls.esp = fixtures.placing_esp(cls.dir / "FixtureMod.esp")
        cls.esm = fixtures.fake_esm(cls.dir / "Oblivion.esm")

    def test_extract_mod_cells(self):
        d = preview.extract(self.esp)
        self.assertEqual([c["edid"] for c in d["cells"]], ["FixtureCellar"])
        items = d["cells"][0]["items"]
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["kind"], "object")
        self.assertAlmostEqual(items[0]["size"][0], 46.0)

    def test_extract_npc_schedules_from_the_test_actors(self):
        tc, _ = testcells.write(self.dir / "tc")
        d = preview.extract(tc)
        holding = d["cells"][0]
        merchant = next(i for i in holding["items"] if i.get("edid") == "ForgeStreetMerchantRef")
        self.assertEqual([p["hours"] for p in merchant["npc"]["packages"]], ["08:00-20:00", "20:00-08:00"])
        self.assertTrue(merchant["npc"]["packages"][0]["offers_services"])

    def test_vanilla_cell(self):
        d = preview.extract_vanilla_cell(self.esm, fixtures.ARENA_CELL, "ICArena", "Arena")
        items = d["cells"][0]["items"]
        self.assertEqual(len(items), 5)
        self.assertEqual(sum(1 for i in items if i["base"] == "ArenaFloor"), 4)
        self.assertEqual(sum(1 for i in items if i["kind"] == "door"), 1)

    def test_page_from_shared_template(self):
        out = preview.build_page(self.esp, self.dir / "p.html", "Fixture mod")
        html = out.read_text(encoding="utf-8")
        tpl = preview.TEMPLATE.read_text(encoding="utf-8")
        engine = tpl[tpl.index("PREVIEW ENGINE (reusable)"):tpl.index("TEST LOCATION (reusable)")]
        self.assertIn(engine[:4000], html, "the template engine is reused unchanged")
        self.assertIn("SoftRenderer", html)
        self.assertIn("WebGLRenderer", html)
        self.assertIn("E.clamp(pp)", html)
        self.assertNotIn("Crimson Grasp", html)
        self.assertIn('"edid":"FixtureCellar"', html)
        self.assertIn("getGamepads", html)
        data = json.loads(re.search(r"const PV=(\{.*?\});const U=70;", html).group(1))
        self.assertEqual(len(data["cells"]), 1)

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

    def test_dry_run_leaves_everything_byte_identical(self):
        with self.env():
            code, out, err = forge("playtest", str(EXAMPLE), "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("restore: plugins_txt identical", out)
        self.assertRealSetupUntouched()

    def test_status_restore_and_cells(self):
        with self.env():
            self.assertIn("off", forge("playtest", "status")[1])
            self.assertIn("nothing to restore", forge("playtest", "restore")[1])
            code, out, _ = forge("playtest", "cells")
        self.assertEqual(code, 0)
        self.assertIn("coc ICArena", out)
        self.assertIn("cow ICMarketDistrict 10 6", out)
        self.assertIn("look like: ICCitizenFixture", out)
        with self.env():
            code, out, _ = forge("playtest", "find", "weye")
        self.assertIn("marker:Weye", out)

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

    def test_preview_commands(self):
        with self.env():
            code, out, err = forge("preview", "cells", "--out", str(self.tmp / "pv.html"))
            self.assertEqual(code, 0, out + err)
            self.assertIn("ICArena", (self.tmp / "pv.html").read_text(encoding="utf-8"))
            code, out, err = forge("preview", str(EXAMPLE))
        self.assertEqual(code, 1, "the fire-bolt mod places nothing: nothing to preview")
        self.assertIn("places no objects", err)

    def test_bad_target(self):
        with self.env():
            code, _, err = forge("playtest", str(self.tmp / "missing.esp"), "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)


if __name__ == "__main__":
    unittest.main()
