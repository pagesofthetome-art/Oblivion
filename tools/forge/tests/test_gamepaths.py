"""The game folder is found whether the repo is the workspace or a clone beside it."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

import gamepaths  # noqa: E402


class GamePathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forge-gp-"))
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("OBLIVION_GAME_DIR", None)
        os.environ.pop("OBLIVION_WORKSPACE", None)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _game(self, p: Path) -> Path:
        (p / "Data").mkdir(parents=True)
        (p / "Data" / "Oblivion.esm").write_bytes(b"TES4")
        return p

    def test_clone_beside_the_game(self):
        # Desktop\Games\Oblivion (game) + Desktop\Games\Oblivion-repo (clone): the PC layout
        game = self._game(self.tmp / "Games" / "Oblivion")
        repo = self.tmp / "Games" / "Oblivion-repo"
        repo.mkdir()
        with mock.patch.object(gamepaths, "REPO", repo):
            self.assertEqual(gamepaths.game_dir(), game)
            self.assertEqual(gamepaths.workspace_dir(), self.tmp / "Games")

    def test_repo_is_the_workspace(self):
        repo = self.tmp / "Games"
        game = self._game(repo / "Oblivion")
        with mock.patch.object(gamepaths, "REPO", repo):
            self.assertEqual(gamepaths.game_dir(), game)

    def test_env_override_wins(self):
        os.environ["OBLIVION_GAME_DIR"] = str(self.tmp / "Elsewhere")
        self.assertEqual(gamepaths.game_dir(), self.tmp / "Elsewhere")


if __name__ == "__main__":
    unittest.main()
