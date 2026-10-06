"""Detached restore guardian: python -m playtest.guardian <state_dir> --game PID --forge PID

Started next to the game. If forge exits or is killed while the game runs (or after it), the
guardian restores Plugins.txt, Oblivion.ini and the staged files as soon as the game is gone.
It exits on its own once the journal is closed. Never touches anything while the game runs.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playtest import platform as plat, profile  # noqa: E402


def watch(m: profile.Machine, game_pid: int | None, forge_pid: int | None, p: plat.Platform,
          poll: float = 1.0, max_hours: float = 12.0) -> str:
    end = p.now() + max_hours * 3600
    while p.now() < end:
        if not m.journal.exists():
            return "closed by forge"
        game = bool(game_pid) and p.alive(game_pid)
        forge = bool(forge_pid) and p.alive(forge_pid)
        if not game and not forge:
            profile.restore(m, log=lambda s: None)
            return "restored by guardian"
        p.sleep(poll)
    return "gave up (time limit)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("state_dir")
    ap.add_argument("--game", type=int)
    ap.add_argument("--forge", type=int)
    a = ap.parse_args(argv)
    m = profile.Machine.detect()
    m.state_dir = Path(a.state_dir)
    res = watch(m, a.game, a.forge, plat.default())
    try:
        (m.state_dir / "guardian.log").open("a", encoding="utf-8").write(
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} game {a.game} forge {a.forge}: {res}\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
