"""On-screen keyboard for Oblivion text boxes, driven by the controller.

How a text box is detected (read-only, no game files changed):
  Oblivion's InterfaceManager singleton lives at 0x00B3A6E0 in Oblivion.exe 1.2.0.416 (found in the
  code of InterfaceManager::GetSingleton at 0x00582160). From it we read, with ReadProcessMemory:
    +0xE0 .. +0x104  stack of open menu IDs (what InterfaceManager::GetTopVisibleMenuID walks)
    +0x098           activeTile     (highlighted with the mouse)
    +0x088           altActiveTile  (highlighted with keyboard / gamepad navigation - NorthernUI uses this)
  A Tile has its XML name as a BSStringT at +0x08 (char* at +0x08, length at +0x0C) and its parent at +0x10.
  These are the same fields xOBSE's GetActiveMenuMode / GetActiveUIComponentName commands read.

A text box is "selected" when the highlighted tile (or one of its parents) is one of the text-box tiles
below and you press Cross. The TextEdit menu (1051) opens the keyboard by itself.

The keyboard is a small always-on-top window that never takes focus, so keystrokes still go to the game.
It can only be seen when Oblivion runs in a window (borderless): prepare_borderless_ini() switches the
game to borderless windowed at your desktop resolution (with a backup of Oblivion.ini).
"""

from __future__ import annotations

import ctypes
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

IM_SINGLETON = 0x00B3A6E0
MENU_NAMES = {1036: "RaceSex", 1040: "Alchemy", 1041: "SpellMaking", 1042: "Enchantment", 1051: "TextEdit",
              1039: "Save", 1001: "Message"}
# Text-box tile names in vanilla + NorthernUI menu XML (menus\chargen\race_sex_menu.xml, dialog\spellmaking.xml,
# dialog\enchantment.xml, dialog\alchemy.xml, NorthernUI\xxnalchemymenu.xml, dialog\texteditmenu.xml).
TEXTBOX_TILES = {"player_name_textedit", "ench_name", "current_potion_name", "potion_name", "textbox",
                 "textedit_text"}
# vanilla menu XML (Oblivion - Misc.bsa), used when only NorthernUI's controller support is installed
VANILLA_TEXTBOX_TILES = {
    1036: {"race_name", "race_name_left", "race_name_right", "race_name_marker", "race_name_marker_2"},
    1041: {"spell_name_background", "spell_name_text"},
    1042: {"ench_name_background", "ench_name_text"},
    1040: {"name_background", "name_text"},
    1051: {"textedit_text"},
}
AUTO_OPEN_MENUS = {1051}                       # menus that ARE a text prompt


# --------------------------------------------------------------------------- memory probe
class GameUIProbe:
    """Reads Oblivion's UI state from the running Oblivion.exe (read-only)."""

    def __init__(self):
        self.pid = None
        self.h = None
        self.ok = sys.platform == "win32"
        if self.ok:
            self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.k32.OpenProcess.restype = ctypes.c_void_p
            self.k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
            self.k32.CloseHandle.argtypes = [ctypes.c_void_p]

    def attach(self, pid: int) -> bool:
        if not self.ok:
            return False
        if pid == self.pid and self.h:
            return True
        self.detach()
        h = self.k32.OpenProcess(0x0010 | 0x1000, False, pid)        # VM_READ | QUERY_LIMITED_INFORMATION
        if not h:
            return False
        self.pid, self.h = pid, h
        return True

    def detach(self):
        if self.h:
            self.k32.CloseHandle(self.h)
        self.pid = self.h = None

    def _read(self, addr: int, n: int) -> bytes | None:
        if not self.h or not addr:
            return None
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        if not self.k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) or got.value != n:
            return None
        return buf.raw

    def u32(self, addr: int) -> int:
        b = self._read(addr, 4)
        return int.from_bytes(b, "little") if b else 0

    def tile_name(self, tile: int) -> str:
        ptr, ln = self.u32(tile + 0x08), self._read(tile + 0x0C, 2)
        n = int.from_bytes(ln, "little") if ln else 0
        if not ptr or not 0 < n < 128:
            return ""
        raw = self._read(ptr, n) or b""
        return raw.split(b"\0", 1)[0].decode("cp1252", "replace")

    def state(self) -> dict:
        """{'menu': top menu id, 'menus': open menu ids, 'tiles': [highlighted tile name, parent, ...]}"""
        im = self.u32(IM_SINGLETON)
        if not im:
            return {"menu": 0, "menus": [], "tiles": []}
        stack = []
        for i in range(10):
            v = self.u32(im + 0xE0 + 4 * i)
            if not v:
                break
            stack.append(v)
        # The Big Four menus (inventory, magic, map, stats) are stored as 1 in this stack, not as
        # their ids, so they are reported as 1 here. IM+0x008 == 1 means "game mode" (no menu open).
        menus = [m for m in stack if m == 1 or 1000 < m < 1200]
        mode = self._read(im + 0x08, 1)
        menu_mode = bool(mode) and mode[0] != 1
        tile = self.u32(im + 0x98) or self.u32(im + 0x88)
        names = []
        for _ in range(4):
            if not tile:
                break
            names.append(self.tile_name(tile))
            tile = self.u32(tile + 0x10)
        return {"menu": menus[-1] if menus else 0, "menus": menus, "tiles": names, "menu_mode": menu_mode}


def textbox_highlighted(st: dict) -> bool:
    names = {n.lower() for n in st.get("tiles", [])}
    return bool(names & TEXTBOX_TILES or names & VANILLA_TEXTBOX_TILES.get(st.get("menu", 0), set()))


# --------------------------------------------------------------------------- keyboard logic
ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl'"),
    list("zxcvbnm-.,"),
    ["SHIFT", "SPACE", "DEL", "ENTER", "DONE"],
]
_DIK = {"1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A,
        "0": 0x0B, "-": 0x0C, "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16,
        "i": 0x17, "o": 0x18, "p": 0x19, "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23,
        "j": 0x24, "k": 0x25, "l": 0x26, "'": 0x28, "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30,
        "n": 0x31, "m": 0x32, ",": 0x33, ".": 0x34, " ": 0x39}
DIK_SHIFT, DIK_BACKSPACE, DIK_ENTER = 0x2A, 0x0E, 0x1C


class KeyboardLogic:
    """Cursor movement + a text buffer. While the keyboard is open it has the window focus, so the game
    is paused and sees NO controller input (no stray D-pad digits, no Cross reaching NorthernUI).
    The text is typed into the game in one go when you finish:
         D-pad move · Cross press key · Square delete · Triangle space · L1 shift · R1 jump to DONE
         Options or R3 = finish (type it into the game) · Circle = cancel (type nothing)."""

    STEP = 0.022                            # ~45 keys/s - Oblivion's DirectInput still sees every tap

    def __init__(self, out, now=time.monotonic, log=lambda m: None):
        self.out, self.now, self.log = out, now, log
        self.r, self.c = 1, 0
        self.shift = True                   # first letter capital
        self.queue: list[tuple[float, int, bool]] = []
        self.prev: dict[str, bool] = {}
        self.rep: dict[str, float] = {}
        self.typed = ""

    # output scheduling (each tap held ~35 ms so DirectInput polling sees it)
    def _tap(self, dik, shift=False, hold=None):
        hold = hold or self.STEP
        t = max([q[0] for q in self.queue] + [self.now()]) + self.STEP
        if shift:
            self.queue.append((t, DIK_SHIFT, True)); t += self.STEP
        self.queue += [(t, dik, True), (t + hold, dik, False)]
        if shift:
            self.queue.append((t + 2 * self.STEP, DIK_SHIFT, False))

    def commit(self, enter=False, clear=0):
        """Queue: <clear> backspaces (empties what we typed there before), the text, optional Enter.
        Call pump() until idle()."""
        for _ in range(clear):
            self._tap(DIK_BACKSPACE, hold=0.03)
        for ch in self.typed:
            low = ch.lower()
            if low in _DIK:
                self._tap(_DIK[low], shift=ch != low)
        if enter:
            self._tap(DIK_ENTER)
        self.log(f"osk: typing {self.typed!r} into the game ({len(self.queue)} key events)")

    def idle(self) -> bool:
        return not self.queue

    def pump(self):
        t = self.now()
        due = sorted((q for q in self.queue if q[0] <= t), key=lambda q: q[0])
        self.queue = [q for q in self.queue if q[0] > t]
        for _, dik, down in due:
            self.out.key(dik, down)

    def release_all(self):
        for _, dik, down in self.queue:
            if not down:
                self.out.key(dik, False)
        self.queue = []

    @property
    def key(self) -> str:
        return ROWS[self.r][self.c]

    def label(self, k: str) -> str:
        if len(k) == 1 and k.isalpha():
            return k.upper() if self.shift else k
        return {"SPACE": "Space", "DEL": "Delete", "ENTER": "Enter", "DONE": "Done", "SHIFT": "Shift"}.get(k, k)

    def move(self, dr, dc):
        self.r = (self.r + dr) % len(ROWS)
        self.c = min(self.c, len(ROWS[self.r]) - 1) if dr else (self.c + dc) % len(ROWS[self.r])

    def press(self) -> str | None:
        k = self.key
        if k == "SHIFT":
            self.shift = not self.shift
        elif k == "SPACE":
            self.typed += " "
        elif k == "DEL":
            self.typed = self.typed[:-1]
        elif k == "ENTER":
            return "enter"
        elif k == "DONE":
            return "done"
        else:
            up = self.shift and k.isalpha()
            self.typed += k.upper() if up else k
            if up:
                self.shift = False             # one-shot shift, like a phone keyboard
        self.log(f"osk: {k} -> {self.typed!r}")
        return None

    def update(self, b: dict) -> str | None:
        """Feed controller buttons; returns 'done', 'enter' or 'cancel' when the keyboard should close."""
        t = self.now()

        def hit(name, repeat=False):
            down, was = b.get(name, False), self.prev.get(name, False)
            if down and not was:
                self.rep[name] = t + 0.35
                return True
            if repeat and down and t >= self.rep.get(name, 1e18):
                self.rep[name] = t + 0.08
                return True
            return False

        res = None
        if hit("dpup", True):
            self.move(-1, 0)
        if hit("dpdown", True):
            self.move(1, 0)
        if hit("dpleft", True):
            self.move(0, -1)
        if hit("dpright", True):
            self.move(0, 1)
        if hit("a"):
            res = self.press()
        if hit("x", True):
            self.typed = self.typed[:-1]
        if hit("y"):
            self.typed += " "
        if hit("leftshoulder"):
            self.shift = not self.shift
        if hit("rightshoulder"):
            self.r, self.c = 4, 4
        if hit("rightstick") or hit("start"):
            res = "done"
        if hit("b"):
            res = "cancel"
        self.prev = dict(b)
        return res if res in ("done", "enter", "cancel") else None


# 8 D-pad directions, console order: up = 1, then clockwise
PICK_DIRS = {(0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4, (0, 1): 5, (-1, 1): 6, (-1, 0): 7, (-1, -1): 8}


class HotkeyPicker:
    """Hotkey wheel for the inventory / magic menu: HOLD L1, point the RIGHT thumbstick at a slot
    (8 directions, up = 1, then clockwise), RELEASE L1 = assign the highlighted item/spell to it.
    Released without pointing (or Circle) = cancel. The game is paused while the wheel is up."""

    DEAD = 0.5
    HOLD = "leftshoulder"                                 # L1 (left bumper)

    def __init__(self, now=time.monotonic):
        self.now = now
        self.slot = None
        self.prev: dict[str, bool] = {}
        self.typed = ""

    @staticmethod
    def _dir(x, y):
        import math
        ang = math.degrees(math.atan2(y, x))              # 0 = right, 90 = down (SDL: +y is down)
        sector = int(((ang + 22.5) % 360) // 45)          # 0 right, 1 down-right, 2 down, ... 7 up-right
        return {6: 1, 7: 2, 0: 3, 1: 4, 2: 5, 3: 6, 4: 7, 5: 8}[sector]

    def update(self, b: dict, left=(0.0, 0.0), right=(0.0, 0.0)):
        x, y = right                                      # right thumbstick only
        if (x * x + y * y) ** 0.5 > self.DEAD:
            self.slot = self._dir(x, y)
        res = None
        if b.get("b") and not self.prev.get("b"):
            res = "cancel"
        elif not b.get(self.HOLD):                        # hold button released
            res = self.slot if self.slot else "cancel"
        self.prev = dict(b)
        return res


# --------------------------------------------------------------------------- overlay window
class KeyboardOverlay:
    """Always-on-top, click-through, non-activating keyboard picture (tkinter + a little Win32)."""

    W, H = 760, 300

    def __init__(self, root):
        import tkinter as tk
        self.tk = tk
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.93)
        except Exception:
            pass
        self.canvas = tk.Canvas(self.win, width=self.W, height=self.H, bg="#15171c", highlightthickness=0)
        self.canvas.pack()
        self.win.geometry(f"{self.W}x{self.H}+-3000+-3000")     # map it once off-screen so Tk draws it
        self.win.update_idletasks(); self.win.update()
        self.hwnd = None
        self.visible = False
        if sys.platform == "win32":
            from ctypes import wintypes
            self.u = ctypes.WinDLL("user32")
            self.u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            self.u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            self.u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, wintypes.UINT]
            self.u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            try:
                self.hwnd = int(self.win.wm_frame(), 16)
            except Exception:
                self.hwnd = self.u.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            ex = self.u.GetWindowLongW(self.hwnd, -20)
            # NOACTIVATE | TOPMOST | TOOLWINDOW | TRANSPARENT (click-through) | LAYERED
            self.u.SetWindowLongW(self.hwnd, -20, ex | 0x08000000 | 0x8 | 0x80 | 0x20 | 0x80000)
            self.u.ShowWindow(self.hwnd, 0)
        else:
            self.win.withdraw()

    def show(self, game_rect=None, take_focus=True):
        """take_focus: make the keyboard the active window, so Oblivion pauses and ignores the controller."""
        w, h = self.W, self.H
        if game_rect:
            l, t, r, b = game_rect
            x, y = l + (r - l - w) // 2, max(t, b - h - 40)
        else:
            x, y = 200, 300
        if self.hwnd:
            ex = self.u.GetWindowLongW(self.hwnd, -20)
            if take_focus:
                ex &= ~(0x08000000 | 0x20)          # allow activation, not click-through
            else:
                ex |= 0x08000000 | 0x20
            self.u.SetWindowLongW(self.hwnd, -20, ex)
            self.u.SetWindowPos(self.hwnd, -1, x, y, w, h, 0x0040 | (0 if take_focus else 0x0010))
            if take_focus:
                force_foreground(self.hwnd)
                try:
                    self.win.focus_force()
                except Exception:
                    pass
        else:
            self.win.geometry(f"{w}x{h}+{x}+{y}"); self.win.deiconify()
        self.visible = True

    def hide(self):
        if self.hwnd:
            self.u.ShowWindow(self.hwnd, 0)
        else:
            self.win.withdraw()
        self.visible = False

    def draw_picker(self, pk: HotkeyPicker, title: str):
        cv = self.canvas
        cv.delete("all")
        cv.create_text(16, 16, anchor="nw", fill="#f0d090", font=("Segoe UI", 12, "bold"), text=title)
        cv.create_text(16, 276, anchor="nw", fill="#9aa0a8", font=("Segoe UI", 9),
                       text="Keep holding L1 · point the right stick at a slot · release L1 to assign · Circle cancel")
        cx, cy, r = 380, 150, 90
        for (dx, dy), n in PICK_DIRS.items():
            k = 0.7071 if dx and dy else 1.0
            x, y = cx + dx * r * k, cy + dy * r * k
            sel = n == pk.slot
            cv.create_oval(x - 28, y - 28, x + 28, y + 28, fill="#d9a441" if sel else "#3a3f4b", outline="#5c6270")
            cv.create_text(x, y, text=str(n), fill="#101010" if sel else "#e8e8e8", font=("Segoe UI", 16, "bold"))

    def draw(self, kb: KeyboardLogic, title: str):
        cv = self.canvas
        cv.delete("all")
        cv.create_text(16, 16, anchor="nw", fill="#f0d090", font=("Segoe UI", 12, "bold"),
                       text=f"{title}:   {kb.typed[-32:]}_")
        cv.create_text(16, 276, anchor="nw", fill="#9aa0a8", font=("Segoe UI", 9),
                       text="D-pad move · Cross key · Square delete · Triangle space · L1 shift · R1 to Done · Options/R3 finish · Circle cancel")
        y = 48
        for ri, row in enumerate(ROWS):
            n = len(row)
            kw = 70 if ri < 4 else 142
            x = (760 - (n * (kw + 4))) // 2
            for ci, k in enumerate(row):
                sel = (ri, ci) == (kb.r, kb.c)
                fill = "#d9a441" if sel else ("#3a3f4b" if k not in ("SHIFT",) or not kb.shift else "#6b5a2a")
                cv.create_rectangle(x, y, x + kw, y + 40, fill=fill, outline="#5c6270")
                cv.create_text(x + kw / 2, y + 20, text=kb.label(k), fill="#101010" if sel else "#e8e8e8",
                               font=("Segoe UI", 13, "bold"))
                x += kw + 4
            y += 45


# --------------------------------------------------------------------------- display mode
def screen_size() -> tuple[int, int]:
    if sys.platform != "win32":
        return 1920, 1080
    u = ctypes.WinDLL("user32")
    try:
        u.SetProcessDPIAware()
    except Exception:
        pass
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def prepare_borderless_ini(ini: Path) -> str:
    """Set Oblivion.ini to windowed at the desktop resolution (the companion removes the border at run time)."""
    text = ini.read_text("cp1252", "replace")
    w, h = screen_size()
    want = {"bFull Screen": "0", "iSize W": str(w), "iSize H": str(h)}
    cur = {k: (re.search(rf"^{re.escape(k)}\s*=\s*(\S+)", text, re.M) or [None, None])[1] for k in want}
    if cur == want:
        return f"already borderless-ready ({w}x{h})"
    bak = ini.with_name(f"Oblivion.ini.bak-display-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(ini, bak)
    for k, v in want.items():
        text = re.sub(rf"^({re.escape(k)}\s*=\s*)\S+", rf"\g<1>{v}", text, count=1, flags=re.M)
    ini.write_text(text, "cp1252")
    return f"Oblivion.ini set to windowed {w}x{h} (was fullscreen={cur['bFull Screen']} {cur['iSize W']}x{cur['iSize H']}); backup {bak.name}"


def restore_fullscreen_ini(ini: Path) -> str:
    text = ini.read_text("cp1252", "replace")
    text = re.sub(r"^(bFull Screen\s*=\s*)\S+", r"\g<1>1", text, count=1, flags=re.M)
    ini.write_text(text, "cp1252")
    return "Oblivion.ini set back to fullscreen (bFull Screen=1)"


def oblivion_window():
    """(hwnd, pid, rect) of the Oblivion.exe main window, or None."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes
    u = ctypes.WinDLL("user32"); k = ctypes.WinDLL("kernel32")
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not u.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD(); u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000, False, pid.value)
        if h:
            buf = ctypes.create_unicode_buffer(1024); sz = wintypes.DWORD(1024)
            k.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD)]
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz)) and Path(buf.value).name.lower() == "oblivion.exe":
                r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
                found.append((hwnd, pid.value, (r.left, r.top, r.right, r.bottom)))
            k.CloseHandle.argtypes = [ctypes.c_void_p]; k.CloseHandle(h)
        return True

    u.EnumWindows(cb, 0)
    return max(found, key=lambda f: (f[2][2] - f[2][0]) * (f[2][3] - f[2][1])) if found else None


def force_foreground(hwnd) -> bool:
    """SetForegroundWindow that also works from a background process (attach to the foreground thread)."""
    if sys.platform != "win32" or not hwnd:
        return False
    from ctypes import wintypes
    u = ctypes.WinDLL("user32"); k = ctypes.WinDLL("kernel32")
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    for f in ("SetForegroundWindow", "BringWindowToTop", "SetFocus", "SetActiveWindow"):
        getattr(u, f).argtypes = [wintypes.HWND]
    fg = u.GetForegroundWindow()
    me = k.GetCurrentThreadId()
    other = u.GetWindowThreadProcessId(fg, None) if fg else 0
    target = u.GetWindowThreadProcessId(hwnd, None)
    attached = []
    for t in {other, target} - {me, 0}:
        if u.AttachThreadInput(me, t, True):
            attached.append(t)
    try:
        u.ShowWindow(hwnd, 5)                              # SW_SHOW
        u.BringWindowToTop(hwnd)
        ok = bool(u.SetForegroundWindow(hwnd))
        u.SetActiveWindow(hwnd)
        u.SetFocus(hwnd)
    finally:
        for t in attached:
            u.AttachThreadInput(me, t, False)
    return ok


def make_borderless(hwnd) -> bool:
    """Strip caption/frame from a windowed Oblivion and cover the whole screen. Returns True if changed."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes
    u = ctypes.WinDLL("user32")
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, wintypes.UINT]
    GWL_STYLE = -16
    style = u.GetWindowLongW(hwnd, GWL_STYLE)
    frame = 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000   # CAPTION THICKFRAME SYSMENU MIN MAX
    if not style & frame:
        return False
    u.SetWindowLongW(hwnd, GWL_STYLE, ctypes.c_long(style & ~frame).value)
    w, h = screen_size()
    u.SetWindowPos(hwnd, 0, 0, 0, w, h, 0x0020 | 0x0004 | 0x0040)   # FRAMECHANGED | NOZORDER | SHOWWINDOW
    return True
