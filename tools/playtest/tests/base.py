from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from playtest import profile  # noqa: E402
from playtest.tests import fixtures  # noqa: E402


def tree_hash(root: Path) -> dict:
    """{relative path: (sha256, mtime_ns)} of every file under root."""
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


class MachineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="playtest-"))
        self.fx = fixtures.fake_install(self.tmp)
        self.m = profile.Machine(plugins_txt=self.fx["plugins_txt"], ini=self.fx["ini"], game_dir=self.fx["gog"],
                                 state_dir=self.fx["state"], play_dirs=[self.fx["steam"]],
                                 vortex_dirs=[self.fx["vortex"]], master_dirs=[self.fx["steam"] / "Data"])
        self.real = {"plugins": self.fx["plugins_txt"].read_bytes(), "ini": self.fx["ini"].read_bytes(),
                     "plugins_mtime": self.fx["plugins_txt"].stat().st_mtime_ns,
                     "ini_mtime": self.fx["ini"].stat().st_mtime_ns}
        self.steam_before = tree_hash(self.fx["steam"])
        self.gog_before = tree_hash(self.fx["gog"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assertRealSetupUntouched(self, gog_too: bool = True):
        self.assertEqual(self.fx["plugins_txt"].read_bytes(), self.real["plugins"], "Plugins.txt bytes changed")
        self.assertEqual(self.fx["ini"].read_bytes(), self.real["ini"], "Oblivion.ini bytes changed")
        self.assertEqual(self.fx["plugins_txt"].stat().st_mtime_ns, self.real["plugins_mtime"])
        self.assertEqual(self.fx["ini"].stat().st_mtime_ns, self.real["ini_mtime"])
        self.assertEqual(tree_hash(self.fx["steam"]), self.steam_before, "the Steam play copy changed")
        if gog_too:
            self.assertEqual(tree_hash(self.fx["gog"]), self.gog_before, "staged files left in the test game")
        self.assertFalse(self.m.journal.exists(), "restore journal still open")
