"""CLI behaviour: spec validation, guards, expectations, packaging, compare, caps."""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

from forge import cli, spec as specmod  # noqa: E402
from forge.tests import fixtures  # noqa: E402


def forge(*args) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forge-cli-"))
        self.fx = fixtures.make(self.tmp / "fx")
        self.spec = json.loads(self.fx["spec"].read_text(encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_spec(self, **changes) -> Path:
        s = json.loads(json.dumps(self.spec))
        s.update(changes)
        p = self.fx["root"] / "variant.json"
        p.write_text(json.dumps(s), encoding="utf-8")
        return p

    def test_spec_check_ok(self):
        code, out, _ = forge("spec", "check", str(self.fx["spec"]), "--json")
        res = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(res["buildable_here"], res)

    def test_spec_errors(self):
        p = self.write_spec(name="Bad Name", intent="", inputs=[
            {"id": "x", "permission": "PRIVATE_RESEARCH_ONLY"}, {"id": "y", "permission": "maybe"}])
        errs = specmod.validate(specmod.load(p))
        self.assertTrue(any("slug" in e for e in errs))
        self.assertTrue(any("intent" in e for e in errs))
        self.assertTrue(any("reference" in e for e in errs))
        self.assertTrue(any("permission must be" in e for e in errs))

    def test_vars_and_set(self):
        s = json.loads(json.dumps(self.spec))
        s["vars"] = {"INST": "installed"}
        s["merge_patch"]["installed_dir"] = "${INST}"
        s["merge_patch"]["plugins_txt"] = "${PTXT}"
        p = self.fx["root"] / "vars.json"
        p.write_text(json.dumps(s), encoding="utf-8")
        self.assertTrue(any("PTXT" in e for e in specmod.validate(specmod.load(p))))
        sp = specmod.load(p, {"PTXT": "Plugins.txt"})
        self.assertEqual(specmod.validate(sp), [])
        self.assertEqual(sp.resolve(sp.section("merge_patch")["installed_dir"]), self.fx["installed"].resolve())

    def test_unset_env_var_inside_vars_is_reported(self):
        s = json.loads(json.dumps(self.spec))
        s["vars"] = {"PTXT": "${env:FORGE_TEST_SURELY_UNSET}/Plugins.txt"}
        s["merge_patch"]["plugins_txt"] = "${PTXT}"
        p = self.fx["root"] / "envvars.json"
        p.write_text(json.dumps(s), encoding="utf-8")
        self.assertTrue(any("FORGE_TEST_SURELY_UNSET" in e for e in specmod.validate(specmod.load(p))))

    def test_refuses_to_build_into_data_or_vortex(self):
        code, _, err = forge("build", str(self.fx["spec"]), "--out", str(self.fx["installed"] / "sub"), "--quiet")
        self.assertEqual(code, 1)
        self.assertIn("Data folder", err)
        code, _, err = forge("build", str(self.fx["spec"]), "--out", str(self.tmp / "Vortex" / "x"), "--quiet")
        self.assertEqual(code, 1)

    def test_installed_dir_named_data_is_guarded(self):
        data = self.fx["root"] / "Data"
        shutil.copytree(self.fx["installed"], data)
        code, _, err = forge("build", str(self.fx["spec"]), "--out", str(data), "--quiet")
        self.assertEqual(code, 1)
        self.assertIn("Data folder", err)

    def test_expect_sha256_mismatch_fails(self):
        p = self.write_spec(expect={"sha256": "0" * 64})
        code, out, _ = forge("build", str(p), "--quiet", "--json")
        self.assertEqual(code, 2)
        self.assertIn("expected", json.loads(out)["failures"][0])

    def test_expect_same_records_and_package(self):
        code, out, _ = forge("build", str(self.fx["spec"]), "--quiet", "--json")
        self.assertEqual(code, 0, out)
        first = json.loads(out)
        ref = self.tmp / "ref.esp"
        shutil.copy(first["plugin"], ref)
        p = self.write_spec(expect={"sha256": first["sha256"], "same_records_as": str(ref)})
        code, out, _ = forge("build", str(p), "--quiet", "--json", "--package")
        self.assertEqual(code, 0, out)
        out_dir = Path(first["plugin"]).parent
        z1 = out_dir / "fixture-merge-patch-1.0.zip"
        with zipfile.ZipFile(z1) as zf:
            self.assertEqual(sorted(zf.namelist()), sorted([fixtures.PATCH, "Test Merge Patch - readme.txt"]))
            self.assertEqual(zf.read(fixtures.PATCH), ref.read_bytes())
        b1 = z1.read_bytes()
        code, _, _ = forge("package", str(p))
        self.assertEqual(code, 0)
        self.assertEqual(z1.read_bytes(), b1)            # zip bytes are stable too

    def test_package_refuses_tampered_build(self):
        code, out, _ = forge("build", str(self.fx["spec"]), "--quiet", "--json")
        plugin = Path(json.loads(out)["plugin"])
        plugin.write_bytes(plugin.read_bytes() + b"\0")
        code, _, err = forge("package", str(self.fx["spec"]))
        self.assertEqual(code, 2)
        self.assertIn("changed since it was built", err)

    def test_compare_detects_difference(self):
        a = self.fx["installed"] / "NewA.esp"
        b = self.fx["installed"] / "NewB.esp"
        code, out, _ = forge("compare", str(a), str(b), "--json")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["verdict"], "different")
        code, out, _ = forge("compare", str(a), str(a))
        self.assertEqual(code, 0)
        self.assertIn("byte-identical", out)

    def test_caps_lists_registry(self):
        code, out, _ = forge("caps", "--json")
        names = {r["capability"] for r in json.loads(out)}
        self.assertEqual(code, 0)
        for n in ("record.merge", "script.compile", "portal.create", "package.vortex"):
            self.assertIn(n, names)

    def test_new_writes_draft(self):
        code, out, _ = forge("new", "Make a spell that stops time", "--dir", str(self.tmp / "specs"))
        self.assertEqual(code, 0)
        d = self.tmp / "specs" / "make-a-spell-that-stops-time.yaml"
        self.assertTrue(d.is_file())
        try:
            import yaml  # noqa: F401
        except ImportError:
            return
        s = specmod.load(d)
        self.assertEqual(specmod.validate(s), [])
        code, _, err = forge("build", str(d))
        self.assertEqual(code, 1)
        self.assertIn("phase 3", err)

    def test_missing_new_plugin_is_a_clear_error(self):
        s = json.loads(json.dumps(self.spec))
        s["merge_patch"]["new_mod_paths"] = []
        p = self.fx["root"] / "nopaths.json"
        p.write_text(json.dumps(s), encoding="utf-8")
        code, _, err = forge("build", str(p), "--quiet")
        self.assertEqual(code, 1)
        self.assertIn("not found in merge_patch.new_mod_paths", err)

    def test_new_mod_search_finds_and_rejects_ambiguous(self):
        s = json.loads(json.dumps(self.spec))
        s["merge_patch"]["new_mod_paths"] = []
        s["merge_patch"]["new_mod_search"] = ["newmods"]
        p = self.fx["root"] / "search.json"
        p.write_text(json.dumps(s), encoding="utf-8")
        code, out, err = forge("build", str(p), "--quiet", "--json")
        self.assertEqual(code, 0, err)
        dup = self.fx["new"] / "copy"
        dup.mkdir()
        (dup / "NewA.esp").write_bytes((self.fx["new"] / "NewA.esp").read_bytes() + b"\0")
        code, _, err = forge("build", str(p), "--quiet")
        self.assertEqual(code, 0, err)                  # top level only: copy/ is not searched
        s["merge_patch"]["new_mod_search"] = ["newmods/**"]
        p.write_text(json.dumps(s), encoding="utf-8")
        code, _, err = forge("build", str(p), "--quiet")
        self.assertEqual(code, 1)
        self.assertIn("different copies", err)


if __name__ == "__main__":
    unittest.main()
