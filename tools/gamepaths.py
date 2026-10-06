"""Where the GOG game folder and its sibling tools live, wherever the repo is cloned.

The repo may be the workspace itself (Desktop\\Games) or a clone beside it
(Desktop\\Games\\Oblivion-repo). Resolution order for the game folder:
  1. env OBLIVION_GAME_DIR
  2. <repo>\\Oblivion, <repo>\\..\\Oblivion, %USERPROFILE%\\Desktop\\Games\\Oblivion
     (first that looks like a game: Data\\Oblivion.esm or TESConstructionSet.exe)
  3. <repo>\\Oblivion (old default, so error messages still name it)
The workspace (TesIvedit, script extender, ...) is the game folder's parent unless
OBLIVION_WORKSPACE is set.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _looks_like_game(p: Path) -> bool:
    return (p / "Data" / "Oblivion.esm").is_file() or (p / "TESConstructionSet.exe").is_file() \
        or (p / "Oblivion.exe").is_file()


def candidates() -> list[Path]:
    out = []
    env = os.environ.get("OBLIVION_GAME_DIR")
    if env:
        out.append(Path(env))
    out += [REPO / "Oblivion", REPO.parent / "Oblivion", Path.home() / "Desktop" / "Games" / "Oblivion"]
    return out


def game_dir() -> Path:
    env = os.environ.get("OBLIVION_GAME_DIR")
    if env:
        return Path(env)
    for c in candidates():
        if _looks_like_game(c):
            return c
    return REPO / "Oblivion"


def workspace_dir() -> Path:
    env = os.environ.get("OBLIVION_WORKSPACE")
    return Path(env) if env else game_dir().parent


def data_dir() -> Path:
    return game_dir() / "Data"
