"""Phase 1 acceptance: forge rebuilds the merge patch exactly like the legacy script.

The legacy `tools/merge-patch/build_patch.py` has hard-coded cloud paths. The
test runs an unmodified copy whose only edits are path substitutions, against
the synthetic fixtures, and compares bytes.

Run from `tools\\`:  python -m unittest discover -s forge/tests -t .
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

from forge.compare import compare  # noqa: E402
from forge.tests import fixtures  # noqa: E402
import tes4_plugin as tp  # noqa: E402

LEGACY = TOOLS / "merge-patch" / "build_patch.py"
SEQ_LINE = "for n in NEW:\n    for p, r in tp.iter_records(paths[n], want=MERGE):"
SORTED_LINE = "for n in sorted(NEW, key=load_order.index):\n    for p, r in tp.iter_records(paths[n], want=MERGE):"


def run_forge(spec: Path, out: Path, seed: str = "0", *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    return subprocess.run([sys.executable, "-m", "forge", "build", str(spec), "--out", str(out), "--quiet", *extra],
                          cwd=TOOLS, env=env, capture_output=True, text=True)


def run_legacy(fx: dict, scratch: Path, seed: str, deterministic: bool) -> Path:
    """Run build_patch.py with only its paths swapped for the fixture's."""
    modscan = scratch / f"modscan-{seed}-{int(deterministic)}"
    (modscan / "out").mkdir(parents=True)
    shutil.copy(fx["cfg"], modscan / "build_cfg.json")
    shutil.copy(TOOLS / "merge-patch" / "world_edits.py", modscan / "world_edits.py")
    shutil.copy(fx["work"] / "PortPatch.esp", modscan / "PortPatch.esp")
    (modscan / "selpaths.txt").write_text("\n".join(str(p) for p in fx["new_paths"]), encoding="utf-8")
    src = LEGACY.read_text(encoding="utf-8")
    assert SEQ_LINE in src, "legacy script changed: update this test"
    if deterministic:
        src = src.replace(SEQ_LINE, SORTED_LINE)
    for old, new in {
        "/home/claude/modscan": modscan.as_posix(),
        "/home/claude/Games/tools": TOOLS.as_posix(),
        "/mnt/user-data/uploads/Games/_audit/installed_plugins": fx["installed"].as_posix(),
        "/mnt/user-data/uploads/common--Oblivion/Data/Oblivion.esm": (fx["installed"] / fixtures.OBL).as_posix(),
        "/mnt/user-data/uploads/Local--Oblivion/Plugins.txt": fx["plugins_txt"].as_posix(),
        "'Rebirth Plus - New Mods Patch.esp'": repr(fixtures.PATCH),
    }.items():
        src = src.replace(old, new)
    script = modscan / "legacy_build_patch.py"
    script.write_text(src, encoding="utf-8")
    env = dict(os.environ, PYTHONHASHSEED=seed,
               PYTHONPATH=os.pathsep.join([str(TOOLS / "merge-patch"), str(TOOLS)]))
    r = subprocess.run([sys.executable, str(script)], cwd=modscan, env=env, capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(f"legacy build failed:\n{r.stdout}\n{r.stderr}")
    return modscan / "out" / fixtures.PATCH


class MergePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="forge-test-"))
        cls.fx = fixtures.make(cls.tmp / "fx")
        r = run_forge(cls.fx["spec"], cls.tmp / "out1", "1")
        if r.returncode:
            raise AssertionError(f"forge build failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        cls.out = cls.tmp / "out1" / fixtures.PATCH

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- the phase 1 acceptance test
    def test_identical_bytes_to_legacy_script(self):
        legacy = run_legacy(self.fx, self.tmp, "0", deterministic=True)
        self.assertEqual(legacy.read_bytes(), self.out.read_bytes(),
                         compare(legacy, self.out)["verdict"])

    def test_same_records_as_legacy_under_any_hash_seed(self):
        # the untouched legacy loop order depends on PYTHONHASHSEED; the records must not
        for seed in ("0", "1", "2", "3", "7"):
            legacy = run_legacy(self.fx, self.tmp, seed, deterministic=False)
            v = compare(legacy, self.out)["verdict"]
            self.assertFalse(v.startswith("different"), f"seed {seed}: {v}")

    def test_deterministic_across_processes(self):
        r = run_forge(self.fx["spec"], self.tmp / "out2", "12345")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.tmp / "out2" / fixtures.PATCH).read_bytes(), self.out.read_bytes())

    # ---- what the merge actually did
    def _records(self):
        out = {}
        for p, r in tp.iter_records(self.out):
            out.setdefault((r.sig, p.global_key(r.form_id)), []).append((p, r))
        return out

    def test_master_list(self):
        self.assertEqual(tp.read_header(self.out).masters, ["Oblivion.esm", "Camp.esp", "Thieves.esp"])

    def test_npc_merge_keeps_every_change(self):
        (p, r), = self._records()[("NPC_", ("oblivion.esm", 0x100))]
        spells = sorted(struct.unpack("<I", s.data)[0] & 0xFFFFFF for s in r.subrecords() if s.sig == "SPLO")
        self.assertEqual(spells, [0x500, 0x501, 0x502])                 # NewA + NewB additions
        self.assertEqual(struct.unpack_from("<h", r.first("ACBS"), 10)[0], 10)   # UOP level fix
        self.assertEqual(r.first("AIDT")[0], 40)                          # NewB aggression

    def test_quest_stage_merge(self):
        (p, r), = self._records()[("QUST", ("oblivion.esm", 0x200))]
        logs = [tp.zstring(s.data) for s in r.subrecords() if s.sig == "CNAM"]
        self.assertEqual(logs, ["log ten (fixed)", "log twenty (B)", "log thirty (A)"])

    def test_info_and_dial(self):
        recs = self._records()
        (p, r), = recs[("INFO", ("oblivion.esm", 0x301))]
        self.assertEqual(tp.zstring(r.first("NAM1")), "hello (fixed)")
        self.assertIsNotNone(r.first("TCLT"))
        self.assertIn(("DIAL", ("oblivion.esm", 0x300)), recs)

    def test_interior_cell_merge(self):
        (p, r), = self._records()[("CELL", ("oblivion.esm", 0x400))]
        self.assertEqual(tp.zstring(r.first("FULL")), "Test Cell UOP")
        self.assertEqual(r.first("XCLL"), b"\x44" * 36)

    def test_world_edits(self):
        recs = self._records()
        # camp land restored to vanilla, camp objects disabled (temp and persistent)
        (p, r), = recs[("LAND", ("oblivion.esm", 0x701))]
        self.assertEqual(r.first("VHGT"), b"\x01" * 64)
        for oid in (0x800, 0x801):
            (p, r), = recs[("REFR", ("camp.esp", oid))]
            self.assertTrue(r.flags & tp.FLAG_INITIALLY_DISABLED)
        # village terrain borrowed
        (p, r), = recs[("LAND", ("oblivion.esm", 0x721))]
        self.assertEqual(r.first("VHGT"), b"\x07" * 64)
        # port patch remapped onto Thieves.esp; its own object becomes the patch's
        self.assertIn(("REFR", ("thieves.esp", 0xA00)), recs)
        self.assertIn(("REFR", (fixtures.PATCH.lower(), 0xB00)), recs)

    def test_build_log_records_hashes(self):
        import json
        log = json.loads((self.tmp / "out1" / "build-log.json").read_text(encoding="utf-8"))
        self.assertEqual(log["status"], "ok")
        self.assertEqual(log["checks"]["roundtrip"]["mismatches"], 0)
        self.assertIn("sha256", log["outputs"]["plugin"])
        self.assertIn("NewA.esp", log["inputs"]["plugins"])
        self.assertIn("PortPatch.esp", log["inputs"]["port_patches"])
        self.assertIn("world_edits.py", " ".join(log["tool_versions"]["code_sha256"]))


if __name__ == "__main__":
    unittest.main()
