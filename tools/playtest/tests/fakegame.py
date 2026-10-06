"""A fake Platform + fake Oblivion for end-to-end runner tests.

The fake game follows the real boot: window -> main menu (1044) -> console `coc <cell>` -> loading
(1007) -> game mode. Console text typed with type_text + enter is executed like Oblivion would:
`bat fptN` reads <game>\\fptN.txt and runs each line; `scof` / `printc` / function calls write to
the scof log in the same "Function >> value" format.
"""

from __future__ import annotations

import re
from pathlib import Path

from playtest import platform as plat


class FakeGame:
    def __init__(self, game_dir: Path, behaviour: dict | None = None):
        self.dir = game_dir
        self.b = {"menu_at": 3.0, "load_seconds": 2.0, "damage": 25.0, "freeze_at": None, "printc": True,
                  "has_spell_works": True, "menu_console": True, "save_dir": None, "new_game_after": None,
                  "continue_after": None, "chargen_seconds": 10.0, "save_before_chargen": False}
        self.b.update(behaviour or {})
        self.state = "starting"
        self.console_open = False
        self.typed = ""
        self.log = None
        self.av = {"health": 500.0}
        self.spells: set = set()
        self.cell = None
        self.world = None
        self.loaded_save = False
        self.messages: list[str] = []
        self.quit_at = None
        self.menu_since = None
        self.t_load = None
        self.alive = True
        self.history: list[str] = []
        self.started = None

    # time passes
    def advance(self, now: float):
        if self.started is None:
            self.started = now
        if self.state == "starting" and now - self.started >= self.b["menu_at"]:
            self.state = "menu"
            self.menu_since = now
        if (self.state == "menu" and self.b["new_game_after"] is not None
                and now - self.menu_since >= self.b["new_game_after"]):
            self.cell, self.state, self.t_load = "TutorialPrison", "loading", now     # Yuri pressed New
        if (self.state == "menu" and self.b["continue_after"] is not None
                and now - self.menu_since >= self.b["continue_after"]):
            self.cell, self.state, self.t_load = "ICArena", "loading", now  # Yuri pressed Continue
            self.loaded_save = True
        if self.state == "loading" and now - self.t_load >= self.b["load_seconds"]:
            self.state = "chargen" if self.cell == "TutorialPrison" or self.b["save_before_chargen"] and \
                self.loaded_save else "game"
            self.chargen_since = now
        if (self.state == "chargen" and not (self.b["save_before_chargen"] and self.loaded_save)
                and now - self.chargen_since >= self.b["chargen_seconds"]):
            self.state = "game"                                                      # Yuri chose DONE
        if self.b["freeze_at"] is not None and now - self.started >= self.b["freeze_at"] and self.state != "frozen":
            self.state = "frozen"
        if self.quit_at is not None and now >= self.quit_at:
            self.alive = False                                                       # Yuri quit

    def ui(self) -> dict:
        menus = {"starting": [], "menu": [plat.MENU_MAIN], "loading": [plat.MENU_LOADING], "game": [1004],
                 "frozen": [1004], "chargen": [1036]}[self.state]
        mode = self.state in ("menu", "loading", "chargen") or self.console_open
        return {"menu": menus[-1] if menus else 0, "menus": menus, "menu_mode": mode}

    def key(self, k: str):
        if self.state == "frozen":
            return
        if k == "tilde":
            if self.state == "chargen":
                return
            if self.state == "menu" and not self.b["menu_console"]:
                return
            self.console_open = not self.console_open
            self.typed = ""
        elif k == "esc":
            self.console_open = False
        elif k == "enter" and self.console_open:
            self.run(self.typed)
            self.typed = ""
        # Enter at the main menu does nothing (as on the PC in run 2); Yuri presses Continue (continue_after)

    def text(self, t: str):
        if self.console_open:
            self.typed += t
        else:
            self.history.append(f"GAME KEYS {t!r}")      # typing into the game itself = a bug

    # console
    def write(self, line: str):
        if self.log:
            with open(self.log, "a", encoding="cp1252") as fh:
                fh.write(line + "\n")

    def run(self, cmd: str):
        cmd = cmd.strip()
        self.history.append(cmd)
        low = cmd.lower()
        if low.startswith("coc "):
            self.cell, self.world = cmd.split(None, 1)[1], None
            self.state, self.t_load = "loading", self._now
            self.console_open = False
            return
        if low.startswith("cow "):
            self.world, self.cell = cmd.split()[1], None
            self.state, self.t_load = "loading", self._now
            self.console_open = False
            return
        if low.startswith("save "):
            sd = Path(self.b["save_dir"])
            sd.mkdir(parents=True, exist_ok=True)
            (sd / (cmd.split(None, 1)[1] + ".ess")).write_bytes(b"save")
            return
        if low.startswith("message "):
            self.messages.append(cmd.split(None, 1)[1].strip('"'))
            return
        if low == "qqq":
            self.alive = False
            return
        if low.startswith("bat "):
            f = self.dir / (cmd.split(None, 1)[1] + ".txt")
            for line in f.read_text(encoding="cp1252").splitlines():
                if line.strip():
                    self.run(line)
            return
        if low.startswith("con_scof "):
            cmd, low = cmd[4:], low[4:]
        if low.startswith("scof "):
            arg = cmd.split(None, 1)[1]
            self.log = None if arg == "0" else self.dir / arg
            return
        if low.startswith("printc "):
            if self.b["printc"]:
                self.write(cmd.split(None, 1)[1].strip('"'))
            return
        m = re.match(r"^([\w\"]+)\.(\w+)\s*(.*)$", cmd)
        if not m:
            self.write(f"Script command \"{cmd}\" not found.")
            return
        fn, args = m.group(2).lower(), m.group(3).split()
        if fn == "getinworldspace":
            self.write(f"GetInWorldspace >> {1.0 if args and args[0] == self.world else 0.0:.2f}")
        elif fn == "getincell":
            self.write(f"GetInCell >> {1.0 if args and args[0] == self.cell else 0.0:.2f}")
        elif fn == "addspell":
            if self.b["has_spell_works"]:
                self.spells.add(args[0])
        elif fn == "hasspell":
            self.write(f"HasSpell >> {1.0 if args[0] in self.spells else 0.0:.2f}")
        elif fn == "cast":
            self.av["health"] -= self.b["damage"]
        elif fn == "getav":
            self.write(f"GetActorValue >> {self.av['health']:.2f}")
        elif fn == "getdead":
            self.write("GetDead >> 0.00")
        elif fn in ("moveto", "setpos", "setangle"):
            pass
        else:
            self.write(f"Script command \"{fn}\" not found.")


class FakePlatform(plat.Platform):
    name = "fake"

    def __init__(self, game_dir: Path, behaviour: dict | None = None, others: list | None = None):
        self.t = 1000.0
        self.game_dir = game_dir
        self.behaviour = behaviour
        self.game: FakeGame | None = None
        self.others = others or []                # other processes, e.g. (pid, "Oblivion.exe", path)
        self.spawned: list[list[str]] = []
        self.killed: list[int] = []
        self.launched = 0

    GAME_PID = 4242

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0.01)
        if self.game:
            self.game._now = self.t
            self.game.advance(self.t)

    def processes(self):
        out = list(self.others)
        if self.game and self.game.alive:
            out.append((self.GAME_PID, "Oblivion.exe", str(self.game_dir / "Oblivion.exe")))
        return out

    def alive(self, pid):
        return pid == self.GAME_PID and bool(self.game and self.game.alive)

    def launch(self, exe, cwd):
        self.launched += 1
        self.game = FakeGame(self.game_dir, self.behaviour)
        self.game._now = self.t
        self.game.advance(self.t)

    def kill(self, pid):
        self.killed.append(pid)
        if self.game and pid == self.GAME_PID:
            self.game.alive = False
        return True

    beeps = 0

    def beep(self):
        """Yuri hears it: at the main menu he presses Continue (continue_after); in game it means
        'forge is done', so he quits a few seconds later (also a frozen game, via Task Manager)."""
        self.beeps += 1
        if self.game and self.game.state not in ("menu", "starting", "loading"):
            self.game.quit_at = self.t + 5.0

    def spawn_detached(self, argv):
        self.spawned.append(argv)
        return 999

    def window(self, pid):
        return (1, pid, (0, 0, 1920, 1080)) if self.alive(pid) else None

    def focus(self, hwnd):
        return True

    def focused(self, pid):
        return self.alive(pid)

    def press(self, *keys):
        for k in keys:
            self.game.key(k)
        self.sleep(0.05)

    def type_text(self, text):
        self.game.text(text)
        self.sleep(0.03 * len(text))

    def ui_state(self, pid):
        return self.game.ui() if self.game and self.game.alive else {"menu": 0, "menus": [], "menu_mode": False}

    def hung(self, win):
        return bool(self.game and self.game.state == "frozen")

    def freeze_tick(self, win, focused):
        return False

    scale = 1.0

    def desktop_size(self):
        return (1920, 1080) if self.scale > 1 else (1280, 720)

    def dpi_scale(self):
        return self.scale

    def make_borderless(self, win):
        self.borderless = True
        return True

    def screenshot(self, win, path):
        Path(path).write_bytes(b"\x89PNG fake")
        return True
