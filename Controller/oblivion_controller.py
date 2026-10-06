"""Play classic Oblivion (2006) with a PlayStation (DualSense / DualShock 4) or Xbox controller.

TWO MODES (chosen automatically, override with "mode" in the config or --mode):
  northernui  NorthernUI (OBSE plugin, Data\\OBSE\\Plugins\\NorthernUI.dll) drives the game natively through
              XInput. This program then only adds what NorthernUI lacks:
                - hotkeys 1-8 on the D-pad, 8-way (the layout from "Oblivion Xpadder Settings NorthernUI"):
                  up=1 up-right=2 right=3 down-right=4 down=5 down-left=6 left=7 up-left=8
                - hold L1 + push the right stick in one of 8 directions = hotkeys 1-8 (Xpadder set 2)
                - hold R3 + L2/R2 = mouse wheel up/down (Xpadder set 3)
                - TYPING MODE for name boxes (hold D-pad left 0.6 s), see TYPING below
  standalone  No NorthernUI: full keyboard+mouse emulation (layout below). Typing mode: hold Create/Back
              and press Options.

TYPING (works in both modes; the game's own text box shows each letter as you pick it)
  D-pad up/down  previous/next letter     D-pad right  keep letter, move on     D-pad left / Square  delete
  Triangle       space                    L1/R1        jump 5 letters back/forward
  L2             upper/lower case         R2           letters / digits
  Cross          finish (in NorthernUI: Cross also presses OK)   Circle  leave typing mode

Oblivion's PC build only understands keyboard + mouse properly (its built-in joystick support is
an unfinished DirectInput layer). This program reads the controller through SDL's GameController
API, which gives the same button names for DualSense, DualShock 4, Xbox and Shadow's virtual
gamepad, and turns it into the keyboard keys and mouse movement Oblivion expects.

  * Reads YOUR key bindings from Documents\\My Games\\Oblivion\\Oblivion.ini [Controls], so a
    remapped key in the game's Controls menu is followed automatically.
  * Console-style layout (see LAYOUT below) with two layers: GAME (move, look, fight) and
    MENU (left stick = mouse cursor, Cross = click, Circle = back). Touchpad click (or Back
    on Xbox pads) switches layers; opening menus with the mapped buttons switches automatically.
  * Only sends input while Oblivion is the focused window, and releases everything when you
    alt-tab, pause, or disconnect, so keys never get stuck.
  * F6 (works while the game is focused) or holding the PS / Guide button for 1 s pauses/resumes.

Run:   run_oblivion_controller.bat              (installs pygame-ce on first run)
       py oblivion_controller.py --diagnose     (prints what the controller sends; writes
                                                 controller_diagnostic.txt for troubleshooting)
       py oblivion_controller.py --nogui        (no window)
Config: oblivion_controller_config.json (created on first save; edit layers/sensitivity there).
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import math
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Must be set before SDL starts: keep receiving controller input while Oblivion (not this
# program) has focus, and prefer the native PlayStation drivers (touchpad, rumble).
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS5", "1")
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS4", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "oblivion_controller_config.json"
DIAG_PATH = APP_DIR / "controller_diagnostic.txt"
LOG_PATH = APP_DIR / "controller_log.txt"       # rewritten every run; read it when troubleshooting


def log(msg: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%H:%M:%S.%f}"[:-3] + "  " + msg + "\n")
    except OSError:
        pass
INI_PATH = Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "My Games" / "Oblivion" / "Oblivion.ini"
PLUGINS_TXT = Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "Oblivion" / "Plugins.txt"
GOG_GAME_DIR = APP_DIR.parent / "Oblivion"
STEAM_GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Oblivion")


def resolve_game_dir() -> Path:
    """Which Oblivion install to play.
    1. "game_dir" in oblivion_controller_config.json, if set;
    2. the install Vortex deploys mods into (Data\\vortex.deployment.json) and that has xOBSE;
    3. the GOG copy next to this folder (Desktop\\Games\\Oblivion)."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text("utf-8"))
        if cfg.get("game_dir"):
            return Path(cfg["game_dir"])
    except (OSError, ValueError):
        pass
    for d in (STEAM_GAME_DIR, GOG_GAME_DIR):
        if (d / "Data" / "vortex.deployment.json").is_file() and (d / "obse_loader.exe").is_file():
            return d
    return GOG_GAME_DIR


GAME_DIR = resolve_game_dir()
GAME_DATA = GAME_DIR / "Data"
NUI_DLL = GAME_DATA / "OBSE" / "Plugins" / "NorthernUI.dll"


def plugin_active(name: str) -> bool:
    """True if <name> is listed in Plugins.txt (the active plugin list Vortex / the launcher writes)."""
    try:
        lines = PLUGINS_TXT.read_text("cp1252", "replace").splitlines()
    except OSError:
        return False
    name = name.lower()
    return any(l.strip().lstrip("*").lower() == name for l in lines if not l.startswith("#"))

# --------------------------------------------------------------------------- key codes
# DirectInput key codes (= scan code set 1; codes >= 0x80 are "extended" keys).
DIK = {
    "esc": 0x01, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09,
    "9": 0x0A, "0": 0x0B, "minus": 0x0C, "equals": 0x0D, "backspace": 0x0E, "tab": 0x0F,
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16, "i": 0x17, "o": 0x18,
    "p": 0x19, "enter": 0x1C, "ctrl": 0x1D, "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22,
    "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26, "tilde": 0x29, "shift": 0x2A, "z": 0x2C, "x": 0x2D,
    "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32, "rshift": 0x36, "alt": 0x38, "space": 0x39,
    "capslock": 0x3A, "apostrophe": 0x28, "comma": 0x33, "period": 0x34, "f1": 0x3B, "f2": 0x3C, "f3": 0x3D, "f4": 0x3E, "f5": 0x3F, "f6": 0x40, "f7": 0x41,
    "f8": 0x42, "f9": 0x43, "f10": 0x44, "f11": 0x57, "f12": 0x58, "rctrl": 0x9D, "home": 0xC7,
    "up": 0xC8, "pageup": 0xC9, "left": 0xCB, "right": 0xCD, "end": 0xCF, "down": 0xD0, "pagedown": 0xD1,
}

# Oblivion's own defaults (from a fresh Oblivion.ini) - used when the INI cannot be read.
DEFAULT_BINDINGS = {
    "Forward": ("key", 0x11), "Back": ("key", 0x1F), "Slide Left": ("key", 0x1E), "Slide Right": ("key", 0x20),
    "Use": ("mouse", 0), "Activate": ("key", 0x39), "Block": ("mouse", 1), "Cast": ("key", 0x2E),
    "Ready Item": ("key", 0x21), "Crouch/Sneak": ("key", 0x1D), "Run": ("key", 0x2A),
    "Always Run": ("key", 0x3A), "Auto Move": ("key", 0x10), "Jump": ("key", 0x12),
    "Toggle POV": ("key", 0x13), "Menu Mode": ("key", 0x0F), "Rest": ("key", 0x14),
    "Quick Menu": ("key", 0x3B), "Grab": ("key", 0x2C), "QuickSave": ("key", 0x3F), "QuickLoad": ("key", 0x43),
    **{f"Quick{i}": ("key", 0x01 + i) for i in range(1, 9)},
}

# Controller layout. Button names are SDL GameController names (PlayStation in brackets):
#   a [Cross]  b [Circle]  x [Square]  y [Triangle]  leftshoulder [L1]  rightshoulder [R1]
#   lefttrigger [L2]  righttrigger [R2]  leftstick [L3]  rightstick [R3]  back [Create/Share]
#   start [Options]  guide [PS]  touchpad [touchpad click]  dpup/dpdown/dpleft/dpright
# Values: an Oblivion control name (resolved through Oblivion.ini), "key:<name>", "mouse:left|right|middle",
#         "wheel:up|down", "layer:menu|game|toggle", or a list of these (pressed together).
LAYOUT = {
    "game": {
        "a": "Activate", "b": ["Menu Mode", "layer:menu"], "x": "Ready Item", "y": "Jump",
        "righttrigger": "Use", "lefttrigger": "Block", "rightshoulder": "Cast", "leftshoulder": "Grab",
        "leftstick": "Crouch/Sneak", "rightstick": "Toggle POV",
        "start": ["key:esc", "layer:menu"], "back": ["Rest", "layer:menu"], "touchpad": "layer:toggle",
        "back+start": "layer:typing",
        "dpup": "Quick1", "dpright": "Quick2", "dpdown": "Quick3", "dpleft": "Quick4",
        # hold Create/Share/Back and press the D-pad for the other four hotkeys
        "back+dpup": "Quick5", "back+dpright": "Quick6", "back+dpdown": "Quick7", "back+dpleft": "Quick8",
    },
    "menu": {
        "a": "mouse:left", "b": ["key:esc", "layer:game"], "x": "mouse:right", "y": "key:enter",
        "leftshoulder": "wheel:up", "rightshoulder": "wheel:down", "lefttrigger": "key:pageup",
        "righttrigger": "key:pagedown", "dpup": "key:up", "dpdown": "key:down", "dpleft": "key:left",
        "dpright": "key:right", "start": ["key:esc", "layer:game"], "back": ["Menu Mode", "layer:game"],
        "touchpad": "layer:toggle",
    },
}

DEFAULTS = {
    "mode": "auto",                # auto | northernui | standalone
    "on_screen_keyboard": True,    # show a controller keyboard when a game text box is selected
    "borderless": True,            # run Oblivion borderless-windowed so the keyboard can be drawn over it
    "nui_dpad_hotkeys": True,      # NorthernUI mode: 8-way D-pad = hotkeys 1-8
    "nui_l1_stick_hotkeys": False, # extra (not console): hold L1 + right stick direction = hotkeys 1-8
    "nui_r3_trigger_wheel": False, # extra (not console): hold R3 + L2/R2 = mouse wheel
    "config_version": 3,
    "typing_hold_seconds": 0.6,
    "block_mouse": True,           # NorthernUI mode: ignore the mouse completely while Oblivion is active    # NorthernUI mode: hold D-pad left this long to start typing
    "deadzone": 0.20,              # left stick
    "look_deadzone": 0.12,         # right stick
    "look_speed": 1400.0,          # mouse counts per second at full right-stick tilt
    "look_curve": 1.8,             # >1 = finer control near the centre
    "invert_y": False,
    "cursor_speed": 900.0,         # menu-layer cursor speed (left stick)
    "trigger_threshold": 0.35,
    "walk_threshold": 0.55,        # left stick tilt below this walks (holds Run, which walks when Always Run is on)
    "walk_by_holding_run": True,
    "only_when_oblivion_focused": True,
    "rumble_on_layer_change": True,
    "layout": LAYOUT,
}

BUTTONS = ["a", "b", "x", "y", "back", "guide", "start", "leftstick", "rightstick", "leftshoulder",
           "rightshoulder", "dpup", "dpdown", "dpleft", "dpright", "misc1", "paddle1", "paddle2", "paddle3",
           "paddle4", "touchpad"]          # SDL_GameControllerButton order (0..20)
PS_NAMES = {"a": "Cross", "b": "Circle", "x": "Square", "y": "Triangle", "back": "Create/Share", "guide": "PS",
            "start": "Options", "leftstick": "L3", "rightstick": "R3", "leftshoulder": "L1",
            "rightshoulder": "R1", "lefttrigger": "L2", "righttrigger": "R2", "touchpad": "Touchpad"}


# --------------------------------------------------------------------------- Oblivion.ini
def read_bindings(ini: Path = INI_PATH) -> tuple[dict, list[str]]:
    """Parse [Controls]: each value is KKKKMMJJ hex = keyboard DIK code, mouse button, joystick button.
    FF/FFFF means unbound. Returns (bindings, notes)."""
    notes = []
    binds = dict(DEFAULT_BINDINGS)
    try:
        text = ini.read_text("cp1252", "replace")
    except OSError:
        return binds, [f"Could not read {ini}; using Oblivion's default keys."]
    m = re.search(r"^\[Controls\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not m:
        return binds, ["Oblivion.ini has no [Controls] section; using default keys."]
    for line in m.group(1).splitlines():
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k not in DEFAULT_BINDINGS or not re.fullmatch(r"[0-9A-Fa-f]{8}", v):
            continue
        key, mouse = int(v[0:4], 16), int(v[4:6], 16)
        if key in (0x38, 0xB8) and mouse != 0xFF:
            binds[k] = ("mouse", mouse)      # prefer the mouse button over Alt (Alt can trigger Windows shortcuts)
        elif key not in (0xFF, 0xFFFF):
            binds[k] = ("key", key)
        elif mouse != 0xFF:
            binds[k] = ("mouse", mouse)
        else:
            notes.append(f"'{k}' has no keyboard or mouse binding in Oblivion.ini")
    return binds, notes


def native_joystick_enabled(ini: Path = INI_PATH) -> bool | None:
    try:
        m = re.search(r"^bUse Joystick\s*=\s*(\d)", ini.read_text("cp1252", "replace"), re.M)
        return None if not m else m.group(1) == "1"
    except OSError:
        return None


def set_native_joystick(enabled: bool, ini: Path = INI_PATH) -> Path:
    """Back up Oblivion.ini, then set bUse Joystick. Returns the backup path."""
    text = ini.read_text("cp1252", "replace")
    backup = ini.with_name(f"Oblivion.ini.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(ini, backup)
    new, n = re.subn(r"^(bUse Joystick\s*=\s*)\d", rf"\g<1>{1 if enabled else 0}", text, flags=re.M)
    if n == 0:
        new = re.sub(r"^\[Controls\]\s*$", f"[Controls]\nbUse Joystick={1 if enabled else 0}", text, count=1, flags=re.M)
    ini.write_text(new, "cp1252")
    return backup


# --------------------------------------------------------------------------- Windows input
class Output:
    """Abstract input sink (the real one uses SendInput; tests use a recorder)."""
    def key(self, dik: int, down: bool): ...
    def mouse_button(self, button: int, down: bool): ...
    def mouse_move(self, dx: int, dy: int): ...
    def wheel(self, clicks: int): ...


class SendInputOutput(Output):
    KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8
    MOUSE_FLAGS = {0: (0x2, 0x4), 1: (0x8, 0x10), 2: (0x20, 0x40)}

    def __init__(self):
        from ctypes import wintypes
        ULONG_PTR = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        self.INPUT, self.KEYBDINPUT, self.MOUSEINPUT = INPUT, KEYBDINPUT, MOUSEINPUT
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]

    def _send(self, inp):
        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def key(self, dik, down):
        flags = self.KEYEVENTF_SCANCODE | (0 if down else self.KEYEVENTF_KEYUP)
        if dik & 0x80:
            flags |= self.KEYEVENTF_EXTENDEDKEY
        inp = self.INPUT(type=1)
        inp.ki = self.KEYBDINPUT(0, dik & 0x7F, flags, 0, 0)
        self._send(inp)

    def mouse_button(self, button, down):
        if button not in self.MOUSE_FLAGS:
            return
        inp = self.INPUT(type=0)
        inp.mi = self.MOUSEINPUT(0, 0, 0, self.MOUSE_FLAGS[button][0 if down else 1], 0, 0)
        self._send(inp)

    def mouse_move(self, dx, dy):
        inp = self.INPUT(type=0)
        inp.mi = self.MOUSEINPUT(int(dx), int(dy), 0, 0x1, 0, 0)       # MOUSEEVENTF_MOVE (relative)
        self._send(inp)

    def wheel(self, clicks):
        inp = self.INPUT(type=0)
        inp.mi = self.MOUSEINPUT(0, 0, ctypes.c_uint32(120 * clicks).value, 0x800, 0, 0)
        self._send(inp)


def oblivion_is_focused() -> bool:
    if sys.platform != "win32":
        return True
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32"); kernel32 = ctypes.WinDLL("kernel32")
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    kernel32.OpenProcess.restype = ctypes.c_void_p
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return False
    try:
        buf = ctypes.create_unicode_buffer(1024); size = wintypes.DWORD(1024)
        kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR,
                                                        ctypes.POINTER(wintypes.DWORD)]
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower() == "oblivion.exe"
        return False
    finally:
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(h)


def _steam_pids() -> set[int]:
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines():
        parts = line.strip().strip('"').split('","')
        if len(parts) > 1 and parts[0].lower() == "steam.exe" and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def _steam_active_process() -> tuple[int, int]:
    """(pid, logged-in account id) that Steam publishes in HKCU\\Software\\Valve\\Steam\\ActiveProcess."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as k:
            return int(winreg.QueryValueEx(k, "pid")[0]), int(winreg.QueryValueEx(k, "ActiveUser")[0])
    except (OSError, ValueError, ImportError):
        return 0, 0


def ensure_steam_running(timeout: float = 90.0) -> bool:
    """Start Steam in the background (no window) if it isn't running, and wait until it is logged in."""
    if sys.platform != "win32":
        return True
    if _steam_pids():
        log("Steam is already running - Oblivion starts directly")
        return True
    import subprocess
    exe = Path(r"C:\Program Files (x86)\Steam\steam.exe")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            exe = Path(winreg.QueryValueEx(k, "SteamExe")[0])
    except (OSError, ImportError):
        pass
    log(f"Steam is not running - starting it in the background first ({exe.name} -silent)")
    try:
        subprocess.Popen([str(exe), "-silent"])
    except OSError as exc:
        log(f"could not start Steam: {exc}")
        return False
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2)
        pids = _steam_pids()
        pid, user = _steam_active_process()
        if pids and pid in pids and user and time.time() - t0 >= 20:
            time.sleep(5)                                  # let it finish its start-up work
            log(f"Steam is up ({time.time() - t0:.0f} s) - starting Oblivion")
            return True
    log("Steam did not finish starting in time - starting Oblivion anyway")
    return False


def oblivion_start_time() -> float | None:
    """Epoch seconds when the focused Oblivion.exe process started (None if Oblivion isn't focused)."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32"); kernel32 = ctypes.WinDLL("kernel32")
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    kernel32.OpenProcess.restype = ctypes.c_void_p
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024); size = wintypes.DWORD(1024)
        kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR,
                                                        ctypes.POINTER(wintypes.DWORD)]
        if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return None
        if Path(buf.value).name.lower() != "oblivion.exe":
            return None
        ft = [wintypes.FILETIME() for _ in range(4)]
        kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        if not kernel32.GetProcessTimes(h, *[ctypes.byref(f) for f in ft]):
            return None
        created = (ft[0].dwHighDateTime << 32) | ft[0].dwLowDateTime
        return created / 1e7 - 11644473600.0
    finally:
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(h)


def northernui_loaded_since(start: float) -> bool:
    """NorthernUI writes Data\\OBSE\\Plugins\\NorthernUI.log when the game loads it (only via obse_loader)."""
    log = GAME_DATA / "OBSE" / "Plugins" / "NorthernUI.log"
    try:
        return log.stat().st_mtime >= start - 5
    except OSError:
        return False


def key_pressed_globally(vk: int) -> bool:
    if sys.platform != "win32":
        return False
    return bool(ctypes.WinDLL("user32").GetAsyncKeyState(vk) & 0x8000)


# --------------------------------------------------------------------------- controller
class PadState:
    def __init__(self):
        self.buttons: dict[str, bool] = {b: False for b in BUTTONS}
        self.buttons.update(lefttrigger=False, righttrigger=False)
        self.lx = self.ly = self.rx = self.ry = 0.0
        self.lt = self.rt = 0.0


class Pad:
    """SDL GameController wrapper (pygame-ce). Falls back to a raw joystick if SDL doesn't know the device."""

    def __init__(self):
        import pygame
        self.pg = pygame
        pygame.init()
        try:
            from pygame._sdl2 import controller as sdlc
            sdlc.init()
            self.sdlc = sdlc
        except Exception:
            self.sdlc = None
        self.dev = None
        self.raw = None
        self.name = ""
        self.kind = ""

    def connect(self) -> bool:
        pg = self.pg
        pg.event.pump()
        if self.dev is not None or self.raw is not None:
            if self.attached():
                return True
            self.dev = self.raw = None
        n = pg.joystick.get_count()
        for i in range(n):
            if self.sdlc and self.sdlc.is_controller(i):
                self.dev = self.sdlc.Controller(i)
                self.name = getattr(self.dev, "name", None) or self.sdlc.name_forindex(i) or "Controller"
                self.kind = "gamecontroller"
                return True
        if n:
            self.raw = pg.joystick.Joystick(0); self.raw.init()
            self.name = self.raw.get_name(); self.kind = "raw joystick (unmapped - see --diagnose)"
            return True
        return False

    def attached(self) -> bool:
        try:
            if self.dev is not None:
                return bool(self.dev.attached())
            if self.raw is not None:
                return self.pg.joystick.get_count() > 0
        except Exception:
            return False
        return False

    def read(self, trigger_threshold: float) -> PadState:
        self.pg.event.pump()
        s = PadState()
        if self.dev is not None:
            d = self.dev
            for i, b in enumerate(BUTTONS):
                try:
                    s.buttons[b] = bool(d.get_button(i))
                except Exception:
                    s.buttons[b] = False
            ax = lambda i: max(-1.0, min(1.0, d.get_axis(i) / 32767.0))
            s.lx, s.ly, s.rx, s.ry, s.lt, s.rt = ax(0), ax(1), ax(2), ax(3), max(0.0, ax(4)), max(0.0, ax(5))
        elif self.raw is not None:          # DirectInput-style DualShock 4 layout guess
            j = self.raw
            btn = lambda i: bool(j.get_button(i)) if i < j.get_numbuttons() else False
            raw_map = {"x": 0, "a": 1, "b": 2, "y": 3, "leftshoulder": 4, "rightshoulder": 5, "back": 8,
                       "start": 9, "leftstick": 10, "rightstick": 11, "guide": 12, "touchpad": 13}
            for b, i in raw_map.items():
                s.buttons[b] = btn(i)
            axn = j.get_numaxes()
            ax = lambda i: j.get_axis(i) if i < axn else 0.0
            s.lx, s.ly, s.rx, s.ry = ax(0), ax(1), ax(2), ax(3)
            s.lt, s.rt = (ax(4) + 1) / 2 if axn > 4 else float(btn(6)), (ax(5) + 1) / 2 if axn > 5 else float(btn(7))
            if j.get_numhats():
                hx, hy = j.get_hat(0)
                s.buttons.update(dpup=hy > 0, dpdown=hy < 0, dpleft=hx < 0, dpright=hx > 0)
        s.buttons["lefttrigger"] = s.lt > trigger_threshold
        s.buttons["righttrigger"] = s.rt > trigger_threshold
        return s

    def rumble(self, strength=0.4, ms=120):
        try:
            if self.dev is not None:
                self.dev.rumble(strength, strength, ms)
            elif self.raw is not None:
                self.raw.rumble(strength, strength, ms)
        except Exception:
            pass


# --------------------------------------------------------------------------- mapping logic
class Mapper:
    """Pure logic: PadState -> Output calls. No pygame or Windows calls in here (testable)."""

    def __init__(self, config: dict, bindings: dict, out: Output, rumble=lambda: None):
        self.cfg = config
        self.binds = bindings
        self.out = out
        self.rumble = rumble
        self.layer = "game"
        self.held: dict[tuple, int] = {}         # output token -> reference count
        self.active_actions: dict[str, list] = {}  # trigger name -> tokens it holds
        self.prev: dict[str, bool] = {}
        self.prev_snapshot: dict[str, bool] = {}
        self.combo_used: set[str] = set()        # modifier buttons used in a combo (suppress their tap action)
        self.frac = [0.0, 0.0]
        self.walk_held = False
        self.layer_changed_at = 0.0
        self.blocked: set[str] = set()           # buttons ignored until released (after a layer switch)
        self.typer = Typer(out, lambda: self.now(), rumble)
        self.typing_hook = None
        self.pulses: list[tuple[float, str]] = []  # (release time, trigger) for tap actions
        self.now = time.monotonic

    # ---- token helpers -------------------------------------------------
    def resolve(self, action) -> list[tuple]:
        """Action spec -> list of tokens: ('key', dik) ('mouse', n) ('wheel', +-1) ('layer', name)."""
        if isinstance(action, list):
            return [t for a in action for t in self.resolve(a)]
        if not action:
            return []
        a = str(action)
        if a.startswith("key:"):
            name = a[4:].lower()
            if name not in DIK:
                raise ValueError(f"unknown key name {name!r}")
            return [("key", DIK[name])]
        if a.startswith("mouse:"):
            return [("mouse", {"left": 0, "right": 1, "middle": 2}[a[6:].lower()])]
        if a.startswith("wheel:"):
            return [("wheel", 1 if a[6:].lower() == "up" else -1)]
        if a.startswith("layer:"):
            return [("layer", a[6:].lower())]
        if a in self.binds:
            return [self.binds[a]]
        raise ValueError(f"unknown action {a!r} (not an Oblivion control name)")

    def _press(self, tok):
        kind, val = tok
        if kind == "layer":
            self.set_layer(val)
            return
        if kind == "wheel":
            self.out.wheel(val)
            return
        n = self.held.get(tok, 0)
        if n == 0:
            (self.out.key if kind == "key" else self.out.mouse_button)(val, True)
        self.held[tok] = n + 1

    def _release(self, tok):
        kind, val = tok
        if kind in ("layer", "wheel"):
            return
        n = self.held.get(tok, 0)
        if n <= 1:
            if n == 1:
                (self.out.key if kind == "key" else self.out.mouse_button)(val, False)
            self.held.pop(tok, None)
        else:
            self.held[tok] = n - 1

    def release_all(self):
        for trig in list(self.active_actions):
            self._end(trig)
        for tok in list(self.held):
            kind, val = tok
            (self.out.key if kind == "key" else self.out.mouse_button)(val, False)
        self.held.clear()
        self.walk_held = False
        self.prev = {}
        self.combo_used.clear()
        self.pulses = []

    def _begin(self, trig, action):
        toks = self.resolve(action)
        self.active_actions[trig] = toks
        for t in toks:
            self._press(t)

    def _end(self, trig):
        for t in self.active_actions.pop(trig, []):
            self._release(t)

    def set_layer(self, name):
        if name == "typing":
            for t in [t for t in self.active_actions if t.startswith("__")]:
                self._end(t)                     # stop walking before typing
            if self.typing_hook and self.typing_hook(self.prev_snapshot):
                return
            self.typer.start()
            self.typer.prev = dict(self.prev_snapshot)
            return
        new = {"toggle": "menu" if self.layer == "game" else "game"}.get(name, name)
        if new != self.layer:
            # buttons still held from the old layer must not fire their new-layer action
            self.blocked = {k for k, v in self.prev_snapshot.items() if v}
            self.layer = new
            self.layer_changed_at = time.monotonic()
            if self.cfg.get("rumble_on_layer_change", True):
                self.rumble()

    # ---- per-tick update -----------------------------------------------
    PULSE = 0.06   # seconds a tap is held, so the game's DirectInput polling sees it

    def update(self, s: PadState, dt: float):
        t_now = self.now()
        for when, trig in [p for p in self.pulses if p[0] <= t_now]:
            self._end(trig)
        self.pulses = [p for p in self.pulses if p[0] > t_now]
        self.prev_snapshot = dict(s.buttons)
        if self.typer.active:
            res = self.typer.update(s.buttons)
            if res == "finish":
                self.typer._schedule(DIK["enter"])          # standalone: Enter confirms the text box
            self.blocked = {k for k, v in s.buttons.items() if v}
            self.prev = dict(s.buttons)
            return
        self.typer.pump()
        self.blocked = {k for k in self.blocked if s.buttons.get(k, False)}
        layout = self.cfg["layout"][self.layer]
        b = {k: (v and k not in self.blocked) for k, v in s.buttons.items()}
        # 1) combos "mod+btn" first: if the modifier is held, the combo replaces the plain button
        combos = {k: v for k, v in layout.items() if "+" in k}
        consumed = set()
        for combo, action in combos.items():
            mod, btn = combo.split("+", 1)
            trig = f"{self.layer}:{combo}"
            down = b.get(mod, False) and b.get(btn, False)
            if down and trig not in self.active_actions:
                self._begin(trig, action)
                self.combo_used.add(mod)
            elif not down and trig in self.active_actions:
                self._end(trig)
            if b.get(mod, False):
                consumed.add(btn)
        modifiers = {c.split("+", 1)[0] for c in combos}
        # 2) plain buttons
        for name, action in layout.items():
            if "+" in name:
                continue
            trig = f"{self.layer}:{name}"
            down = b.get(name, False) and name not in consumed
            was = self.prev.get(name, False)
            if name in modifiers:
                # modifier buttons fire their own action on release, unless used in a combo
                if down and not was:
                    self.combo_used.discard(name)
                if was and not b.get(name, False):
                    if name not in self.combo_used and trig not in self.active_actions:
                        self._begin(trig, action)
                        self.pulses.append((t_now + self.PULSE, trig))
                    self.combo_used.discard(name)
                continue
            if down and trig not in self.active_actions:
                self._begin(trig, action)
                if self.cfg["layout"][self.layer] is not layout:      # layer switched by this action
                    break
            elif not down and trig in self.active_actions:
                self._end(trig)
        # end actions that belong to the layer we are no longer in
        pulsing = {t for _, t in self.pulses}
        for trig in [t for t in self.active_actions if not t.startswith(self.layer + ":") and not t.startswith("__")]:
            btn = trig.split(":", 1)[1].split("+")[-1]
            if not s.buttons.get(btn, False) and trig not in pulsing:
                self._end(trig)
        self.prev = {k: v for k, v in b.items()}
        if self.layer == "game":
            self._movement(s)
            self._look(s.rx, s.ry, dt, self.cfg["look_speed"], self.cfg["look_deadzone"], self.cfg["look_curve"],
                       self.cfg.get("invert_y", False))
        else:
            self._stop_movement()
            self._look(s.lx, s.ly, dt, self.cfg["cursor_speed"], self.cfg["deadzone"], 1.5, False)
            self._look(s.rx, s.ry, dt, self.cfg["cursor_speed"], self.cfg["look_deadzone"], 1.5, False)

    def _hold(self, trig, action, on):
        if on and trig not in self.active_actions:
            self._begin(trig, action)
        elif not on and trig in self.active_actions:
            self._end(trig)

    def _movement(self, s):
        dz = self.cfg["deadzone"]
        mag = math.hypot(s.lx, s.ly)
        if mag < dz:
            lx = ly = 0.0
        else:
            lx, ly = s.lx / mag, s.ly / mag            # direction only (8-way, 22.5 degree sectors)
        self._hold("__fwd", "Forward", ly < -0.38)
        self._hold("__back", "Back", ly > 0.38)
        self._hold("__left", "Slide Left", lx < -0.38)
        self._hold("__right", "Slide Right", lx > 0.38)
        walk = self.cfg.get("walk_by_holding_run", True) and dz <= mag < self.cfg["walk_threshold"]
        self._hold("__walk", "Run", walk)

    def _stop_movement(self):
        for t in ("__fwd", "__back", "__left", "__right", "__walk"):
            if t in self.active_actions:
                self._end(t)

    def _look(self, x, y, dt, speed, dz, curve, invert):
        mag = math.hypot(x, y)
        if mag < dz:
            return
        scaled = ((mag - dz) / (1 - dz)) ** curve
        vx, vy = x / mag * scaled * speed * dt, y / mag * scaled * speed * dt * (-1 if invert else 1)
        self.frac[0] += vx; self.frac[1] += vy
        ix, iy = int(self.frac[0]), int(self.frac[1])
        if ix or iy:
            self.frac[0] -= ix; self.frac[1] -= iy
            self.out.mouse_move(ix, iy)


# --------------------------------------------------------------------------- typing mode
class Typer:
    """Type text with the controller. The game's text box is the display: the current candidate letter is
    typed for real, and replaced (Backspace + new letter) while you scroll through the alphabet."""

    LETTERS = "abcdefghijklmnopqrstuvwxyz'-"
    DIGITS = "0123456789"
    KEY_FOR = {**{c: DIK[c] for c in "abcdefghijklmnopqrstuvwxyz0123456789"}, " ": DIK["space"],
               "'": DIK["apostrophe"], "-": DIK["minus"]}
    STEP = 0.035                                   # seconds between synthetic key events

    def __init__(self, out: Output, now=time.monotonic, rumble=lambda: None):
        self.out, self.now, self.rumble = out, now, rumble
        self.active = False
        self.queue: list[tuple[float, int, bool]] = []
        self.prev: dict[str, bool] = {}
        self.repeat_at: dict[str, float] = {}

    # -- output scheduling (taps need real duration so DirectInput polling sees them)
    def _schedule(self, dik: int, shift=False):
        t = max([q[0] for q in self.queue] + [self.now()]) + self.STEP
        if shift:
            self.queue.append((t, DIK["shift"], True)); t += self.STEP
        self.queue.append((t, dik, True)); self.queue.append((t + self.STEP, dik, False))
        if shift:
            self.queue.append((t + 2 * self.STEP, DIK["shift"], False))

    def pump(self):
        t = self.now()
        due = [q for q in self.queue if q[0] <= t]
        self.queue = [q for q in self.queue if q[0] > t]
        for _, dik, down in sorted(due, key=lambda q: q[0]):
            self.out.key(dik, down)

    def _type(self, ch):
        log(f"typing: type {ch!r}")
        self._schedule(self.KEY_FOR[ch.lower()], shift=ch.isupper())

    def _bksp(self):
        log("typing: backspace")
        self._schedule(DIK["backspace"])

    # -- state
    def start(self):
        self.active, self.digits, self.upper, self.idx, self.cand = True, False, False, 0, False
        self.last_idx = 0
        self.prev = {}
        log("TYPING MODE ON")
        self.rumble()

    def stop(self):
        self.active = False
        log("TYPING MODE OFF")
        self.rumble()

    def _chars(self):
        return self.DIGITS if self.digits else self.LETTERS

    def _char(self):
        c = self._chars()[self.idx % len(self._chars())]
        return c.upper() if self.upper and c.isalpha() else c

    def _show(self, new_idx):
        if self.cand:
            self._bksp()
        self.idx = new_idx % len(self._chars())
        self._type(self._char())
        self.cand = True

    def update(self, b: dict[str, bool]) -> str | None:
        """Feed button states. Returns 'finish' or 'cancel' when typing ends, else None."""
        self.pump()
        t = self.now()

        def pressed(name, repeat=False):
            down, was = b.get(name, False), self.prev.get(name, False)
            if down and not was:
                self.repeat_at[name] = t + 0.40
                return True
            if repeat and down and t >= self.repeat_at.get(name, 1e18):
                self.repeat_at[name] = t + 0.09
                return True
            return False

        result = None
        if pressed("dpdown", True):
            self._show(self.idx + 1 if self.cand else self.last_idx)
        elif pressed("dpup", True):
            self._show(self.idx - 1 if self.cand else self.last_idx)
        elif pressed("rightshoulder", True):
            self._show(self.idx + 5 if self.cand else self.last_idx + 5)
        elif pressed("leftshoulder", True):
            self._show(self.idx - 5 if self.cand else self.last_idx - 5)
        elif pressed("dpright"):
            if self.cand:
                self.cand = False; self.last_idx = self.idx       # keep it
            else:
                self._type(self._char())                         # same letter again (double letters)
        elif pressed("dpleft", True) or pressed("x", True):
            self._bksp(); self.cand = False
        elif pressed("y"):
            if self.cand:
                self.cand = False
            self._type(" ")
        elif pressed("lefttrigger"):
            self.upper = not self.upper
            if self.cand:
                self._show(self.idx)
        elif pressed("righttrigger"):
            self.digits = not self.digits; self.idx = 0; self.last_idx = 0
            if self.cand:
                self._show(0)
        elif pressed("a") or pressed("start"):
            result = "finish"
        elif pressed("b"):
            result = "cancel"
        self.prev = dict(b)
        if result:
            self.stop()
        return result


# --------------------------------------------------------------------------- NorthernUI companion
DIRS8 = {(0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4, (0, 1): 5, (-1, 1): 6, (-1, 0): 7, (-1, -1): 8}


class Companion:
    """NorthernUI mode: never duplicates what NorthernUI does; only hotkeys, wheel and typing."""

    SETTLE = 0.08          # wait this long after the first D-pad press so diagonals register

    def __init__(self, cfg: dict, binds: dict, out: Output, rumble=lambda: None, now=time.monotonic):
        self.cfg, self.binds, self.out, self.now = cfg, binds, out, now
        self.typer = Typer(out, now, rumble)
        self.dpad_t0 = None
        self.dpad_dir = None
        self.dpad_long = False
        self.stick_dir = None
        self.wheel_next = 0.0
        self.pulses: list[tuple[float, tuple]] = []
        self.typing_hook = None

    @property
    def layer(self):
        return "typing" if self.typer.active else "northernui"

    def _tap_bind(self, name):
        log(f"companion: {name}  (open menus: {getattr(self, 'last_menus', '?')})")
        kind, val = self.binds[name]
        if kind == "key":
            self.out.key(val, True); self.pulses.append((self.now() + 0.06, ("key", val)))
        else:
            self.out.mouse_button(val, True); self.pulses.append((self.now() + 0.06, ("mouse", val)))

    def release_all(self):
        for _, (k, v) in self.pulses:
            (self.out.key if k == "key" else self.out.mouse_button)(v, False)
        self.pulses = []
        for _, dik, down in self.typer.queue:
            if not down:
                self.out.key(dik, False)
        self.typer.queue = []

    def update(self, s: PadState, dt: float):
        t = self.now()
        for when, (k, v) in [p for p in self.pulses if p[0] <= t]:
            (self.out.key if k == "key" else self.out.mouse_button)(v, False)
        self.pulses = [p for p in self.pulses if p[0] > t]
        b = s.buttons
        if self.typer.active:
            self.typer.update(b)
            self.dpad_t0 = None
            return
        self.typer.pump()
        # ---- D-pad: 8-way hotkeys on release; hold left = typing mode
        dx = (1 if b.get("dpright") else 0) - (1 if b.get("dpleft") else 0)
        dy = (1 if b.get("dpdown") else 0) - (1 if b.get("dpup") else 0)
        if not getattr(self, "dpad_ours", True):
            dx = dy = 0                              # NorthernUI Hotkeys (NUIHotkeys.esp) owns the D-pad
            self.dpad_t0 = None
        if (dx or dy):
            if self.dpad_t0 is None:
                self.dpad_t0, self.dpad_dir, self.dpad_long = t, (dx, dy), False
            elif t - self.dpad_t0 < self.SETTLE:
                self.dpad_dir = (dx, dy) if abs(dx) + abs(dy) >= sum(map(abs, self.dpad_dir)) else self.dpad_dir
            if self.cfg.get("dpad_hold_typing", False) and self.dpad_dir == (-1, 0) and not self.dpad_long \
                    and t - self.dpad_t0 >= self.cfg["typing_hold_seconds"]:
                self.dpad_long = True
                if self.typing_hook and self.typing_hook(b):
                    return                           # the on-screen keyboard took over
                self.typer.start()
                self.typer.prev = dict(b)           # the held D-pad-left must not count as "delete"
                return
        elif self.dpad_t0 is not None:
            if not self.dpad_long and self.cfg.get("nui_dpad_hotkeys", True):
                self._tap_bind(f"Quick{DIRS8[self.dpad_dir]}")
            self.dpad_t0 = None
        # ---- hold L1 + right stick direction = hotkeys (fires once per push)
        if self.cfg.get("nui_l1_stick_hotkeys", False) and b.get("leftshoulder"):
            mag = math.hypot(s.rx, s.ry)
            if mag > 0.6:
                ang = math.degrees(math.atan2(s.ry, s.rx))           # 0 = right, 90 = down
                sector = int(((ang + 22.5) % 360) // 45)               # 0=right,1=down-right,...
                d = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)][sector]
                if d != self.stick_dir:
                    self.stick_dir = d
                    self._tap_bind(f"Quick{DIRS8[d]}")
            elif mag < 0.3:
                self.stick_dir = None
        else:
            self.stick_dir = None
        # ---- hold R3 + triggers = mouse wheel (repeat while held)
        if self.cfg.get("nui_r3_trigger_wheel", False) and b.get("rightstick"):
            if t >= self.wheel_next and (b.get("lefttrigger") or b.get("righttrigger")):
                self.out.wheel(1 if b.get("lefttrigger") else -1)
                self.wheel_next = t + 0.12

# --------------------------------------------------------------------------- config
def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text("utf-8"))
            lay = user.pop("layout", {})
            if user.get("config_version", 0) < 3:
                # v3 = console 1:1: L1 is Grab and R3 is the camera, so the PC-only extras are off
                user.update({"nui_l1_stick_hotkeys": False, "nui_r3_trigger_wheel": False,
                             "config_version": 3})
            cfg.update(user)
            for layer, m in lay.items():
                cfg["layout"].setdefault(layer, {}).update(m)
        except (OSError, ValueError) as exc:
            print(f"warning: ignoring broken {CONFIG_PATH.name}: {exc}")
    return cfg


def validate_config(cfg: dict, binds: dict) -> list[str]:
    m = Mapper(cfg, binds, Output())
    errs = []
    for layer, mapping in cfg["layout"].items():
        for btn, action in mapping.items():
            for part in btn.split("+"):
                if part not in BUTTONS + ["lefttrigger", "righttrigger"]:
                    errs.append(f"{layer}.{btn}: unknown button '{part}'")
            try:
                m.resolve(action)
            except (ValueError, KeyError) as exc:
                errs.append(f"{layer}.{btn}: {exc}")
    return errs


# --------------------------------------------------------------------------- runners
def diagnose(seconds=25):
    lines = [f"Oblivion controller diagnostic {datetime.now():%Y-%m-%d %H:%M:%S}", f"python {sys.version.split()[0]}"]
    binds, notes = read_bindings()
    lines += [f"Oblivion.ini: {INI_PATH} (native joystick bUse Joystick={native_joystick_enabled()})"]
    lines += [f"  {k} -> {v}" for k, v in binds.items()] + [f"  note: {n}" for n in notes]
    try:
        pad = Pad()
    except ImportError:
        lines.append("pygame-ce is not installed: run  py -m pip install pygame-ce")
        DIAG_PATH.write_text("\n".join(lines), "utf-8"); print("\n".join(lines)); return
    import pygame
    lines.append(f"pygame-ce {pygame.version.ver}, SDL {'.'.join(map(str, pygame.get_sdl_version()))}, "
                 f"GameController API: {'yes' if pad.sdlc else 'NO'}")
    pygame.event.pump()
    n = pygame.joystick.get_count()
    lines.append(f"devices seen by SDL: {n}")
    for i in range(n):
        j = pygame.joystick.Joystick(i); j.init()
        lines.append(f"  [{i}] {j.get_name()}  guid={j.get_guid()}  axes={j.get_numaxes()} buttons={j.get_numbuttons()} "
                     f"hats={j.get_numhats()}  recognised_as_gamepad={bool(pad.sdlc and pad.sdlc.is_controller(i))}")
    if not n:
        lines.append("NO CONTROLLER VISIBLE. On Shadow: check the Shadow app's gamepad/USB forwarding settings "
                     "and that the controller works in Windows 'Set up USB game controllers' (joy.cpl).")
    print("\n".join(lines))
    if n and pad.connect():
        print(f"\nPress buttons and move sticks for {seconds} s (Ctrl+C to stop)...")
        seen = set(); end = time.time() + seconds
        try:
            while time.time() < end:
                s = pad.read(0.35)
                now = {k for k, v in s.buttons.items() if v}
                for k in now - seen:
                    msg = f"pressed {k} ({PS_NAMES.get(k, k)})"; print(msg); lines.append(msg)
                seen = now
                print(f"\r L({s.lx:+.2f},{s.ly:+.2f}) R({s.rx:+.2f},{s.ry:+.2f}) L2 {s.lt:.2f} R2 {s.rt:.2f}   ",
                      end="", flush=True)
                time.sleep(0.03)
        except KeyboardInterrupt:
            pass
        print()
    DIAG_PATH.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"\nSaved {DIAG_PATH}")


def resolve_mode(cfg: dict) -> str:
    m = cfg.get("mode", "auto")
    if m == "auto":
        return "northernui" if NUI_DLL.is_file() else "standalone"
    return m


# menu ids that are part of normal gameplay (HUD), not "a menu is open"
HUD_MENUS = {1004, 1005, 1006, 1010, 1045}


class MouseBlocker:
    """Console-style: while Oblivion is the active window, swallow ALL mouse input (moves, clicks, wheel)
    with a low-level mouse hook, so a bumped mouse or the Shadow app's touch input can never move an
    invisible cursor or change the highlighted menu item. Off whenever another window is active."""

    def __init__(self):
        self.active = False
        self.hook = None
        self._proc = None
        if sys.platform != "win32":
            return
        from ctypes import wintypes
        u = ctypes.WinDLL("user32", use_last_error=True); k = ctypes.WinDLL("kernel32")
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
        u.SetWindowsHookExW.restype = ctypes.c_void_p
        u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        u.CallNextHookEx.restype = ctypes.c_ssize_t
        u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        k.GetModuleHandleW.restype = ctypes.c_void_p
        self.u = u

        def proc(code, wparam, lparam):
            if code >= 0 and self.active:
                return 1                                  # eat it
            return u.CallNextHookEx(None, code, wparam, lparam)

        self._proc = HOOKPROC(proc)                       # keep a reference
        self.hook = u.SetWindowsHookExW(14, self._proc, k.GetModuleHandleW(None), 0)   # WH_MOUSE_LL
        if not self.hook:
            log(f"mouse blocker unavailable (error {ctypes.get_last_error()})")
        atexit.register(self.close)

    def set(self, on: bool):
        if on != self.active:
            self.active = on
            log(f"mouse {'blocked (console mode)' if on else 'released'}")

    def close(self):
        self.active = False
        if self.hook:
            self.u.UnhookWindowsHookEx(self.hook); self.hook = None


class Runner:
    def __init__(self, gui: bool, mode: str | None = None, launch_game: bool = False):
        self.launch_game = launch_game      # start Oblivion only after the user saves the settings
        self.game_started = False
        self.cfg = load_config()
        if mode:
            self.cfg["mode"] = mode
        self.mode = resolve_mode(self.cfg)
        self.binds, self.notes = read_bindings()
        errs = validate_config(self.cfg, self.binds)
        if errs:
            raise SystemExit("Config errors:\n  " + "\n  ".join(errs))
        self.pad = Pad()
        self.out = SendInputOutput() if sys.platform == "win32" else Output()
        self.companion = Companion(self.cfg, self.binds, self.out, lambda: self.pad.rumble())
        self.standalone = Mapper(self.cfg, self.binds, self.out, lambda: self.pad.rumble())
        self.mapper = self.companion if self.mode == "northernui" else self.standalone
        # Oblivion Rebirth+ ships "NorthernUI Hotkeys": it puts hotkeys on the D-pad itself
        # (hold Triangle + D-pad in the inventory to assign). Don't send hotkeys 1-8 from the D-pad too.
        self.nui_hotkeys = plugin_active("NUIHotkeys.esp")
        self.companion.dpad_ours = not self.nui_hotkeys
        # In auto mode we check at run time that NorthernUI really loaded (it only does when the game is
        # started through obse_loader.exe). If it didn't, fall back to full keyboard/mouse emulation.
        self.auto = self.cfg.get("mode", "auto") == "auto" and self.mode == "northernui"
        self.mode_note = ""
        self._nui_check = 0.0
        # on-screen keyboard
        import oblivion_osk as osk
        self.oskmod = osk
        self.probe = osk.GameUIProbe()
        import oblivion_freeze
        self.freeze = oblivion_freeze.FreezeProbe(log)   # records where Oblivion is stuck if it freezes
        self.kb = None                    # KeyboardLogic while open
        self.kb_menu = 0
        self._life_check = 0.0
        self._menus_logged = None
        # The low-level mouse block is OFF: it also swallowed the mouse input that Steam Input produces from
        # the controller, which made the pad dead. The cursor is hidden by a transparent texture instead.
        self.mouse_block = None
        self._game_seen = 0.0             # last time the Oblivion window was seen (after we started it)
        self.kb_last_text: dict[int, str] = {}   # menu id -> text we typed there last
        self._lb_t0 = None                # L1 press time in inventory/magic (-1 = wheel already opened)
        self.picker = None                # hotkey wheel while open
        self.picker_title = ""
        self.kb_commit = None             # text waiting to be typed into the game after the keyboard closed
        self.kb_game_hwnd = None
        self.overlay = None
        self.ui = {"menu": 0, "tiles": []}
        self._ui_check = 0.0
        self._win = None
        self._win_check = 0.0
        self._bordered_done = set()
        self.prev_buttons: dict = {}
        self._cross_at = -1.0
        self._kb_sig = None
        self.companion.typing_hook = self.standalone.typing_hook = self._typing_request
        self.enabled = True
        self.status = "starting"
        self.guide_down_at = None
        self.f6_was = False
        self.last = time.monotonic()
        self.focused = False
        self.last_scan = 0.0
        self._focus_cache = (0.0, False)
        self._ini_cache = (0.0, None)
        atexit.register(lambda: (self.companion.release_all(), self.standalone.release_all()))
        try:
            if LOG_PATH.is_file() and LOG_PATH.stat().st_size:     # keep the last run's log for troubleshooting
                shutil.copy2(LOG_PATH, LOG_PATH.with_name("controller_log.previous.txt"))
            LOG_PATH.write_text("", "utf-8")
        except OSError:
            pass
        log(f"start: mode={self.mode} (config {self.cfg.get('mode')}), NorthernUI.dll present={NUI_DLL.is_file()}, game={GAME_DIR}, NUIHotkeys={self.nui_hotkeys}, "
            f"python {sys.version.split()[0]}")
        self.gui = None
        if gui:
            self._build_gui()
        if self.cfg.get("on_screen_keyboard", True):
            try:
                import tkinter as tk
                root = self.gui
                if root is None:
                    root = tk.Tk(); root.withdraw(); self._tkroot = root
                self.overlay = osk.KeyboardOverlay(root)
            except Exception as exc:
                log(f"on-screen keyboard unavailable: {exc}")

    def _build_gui(self):
        import tkinter as tk
        from tkinter import ttk, messagebox
        self.tk, self.messagebox = tk, messagebox
        r = tk.Tk(); r.title("Oblivion controller"); r.resizable(False, False)
        r.protocol("WM_DELETE_WINDOW", self.quit)
        f = ttk.Frame(r, padding=14); f.grid()
        ttk.Label(f, text="Oblivion controller", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        self.v_status = tk.StringVar(); ttk.Label(f, textvariable=self.v_status, wraplength=420).grid(row=1, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Button(f, text="Pause / resume (F6)", command=self.toggle).grid(row=2, column=0, sticky="ew")
        self.b_save = ttk.Button(f, text="Save settings & start Oblivion" if self.launch_game else "Save settings",
                                 command=self.save)
        self.b_save.grid(row=2, column=1, sticky="ew", padx=6)
        if self.mode == "standalone":
            self.b_ini = ttk.Button(f, text="Turn off Oblivion's own joystick input", command=self.fix_ini)
            self.b_ini.grid(row=2, column=2, sticky="ew")
        ttk.Label(f, text="Look speed").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.v_look = tk.DoubleVar(value=self.cfg["look_speed"])
        ttk.Scale(f, from_=300, to=4000, variable=self.v_look,
                  command=lambda _=None: self.cfg.__setitem__("look_speed", float(self.v_look.get()))).grid(row=3, column=1, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(f, text="Cursor speed (menus)").grid(row=4, column=0, sticky="w")
        self.v_cur = tk.DoubleVar(value=self.cfg["cursor_speed"])
        ttk.Scale(f, from_=200, to=3000, variable=self.v_cur,
                  command=lambda _=None: self.cfg.__setitem__("cursor_speed", float(self.v_cur.get()))).grid(row=4, column=1, columnspan=2, sticky="ew")
        self.v_inv = tk.BooleanVar(value=self.cfg["invert_y"])
        ttk.Checkbutton(f, text="Invert look up/down", variable=self.v_inv,
                        command=lambda: self.cfg.__setitem__("invert_y", bool(self.v_inv.get()))).grid(row=5, column=0, sticky="w", pady=(6, 0))
        dpad = ("D-pad = NorthernUI Hotkeys (hold Triangle + D-pad in the inventory to assign)"
                if self.nui_hotkeys else
                "D-pad (8-way) = hotkeys 1-8 (up 1, up-right 2, right 3, down-right 4, down 5, down-left 6, "
                "left 7, up-left 8)")
        help_nui = ("CONSOLE LAYOUT (NorthernUI 'Console' scheme): L-stick move · R-stick look · R2 attack · "
                    "L2 block · R1 cast · L1 grab · Cross activate · Circle menus · Square ready weapon · "
                    "Triangle jump · L3 sneak · R3 view · Create wait · Options pause · L2+Triangle dodge.\n"
                    f"Hotkeys: {dpad}. To assign: in inventory / magic, highlight it, press Triangle "
                    "(the game's quick-key menu).\nMenus: D-pad / left stick move, Cross select, Circle back. Name boxes: Cross opens "
                    "the on-screen keyboard (game pauses); Options = done, Circle = cancel.\n"
                    "Keep this window open (it minimizes itself when the game starts).")
        help_ = ("GAME: L-stick move (light tilt = walk) · R-stick look · Cross activate · Triangle jump · "
                 "Square ready weapon · Circle journal/menu · R2 attack · L2 block · R1 cast · L1 grab · "
                 "L3 sneak · R3 view · D-pad hotkeys 1-4 (hold Create + D-pad = 5-8) · Create tap = wait · "
                 "Options = pause menu.\nMENU: L/R-stick cursor · Cross click · Circle back · Square right-click · "
                 "L1/R1 scroll. Touchpad click switches GAME/MENU.")
        ttk.Label(f, text=help_nui if self.mode == "northernui" else help_, wraplength=440, justify="left").grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.gui = r

    def toggle(self):
        self.enabled = not self.enabled
        if not self.enabled:
            self.mapper.release_all()
        self.pad.rumble(0.6, 200)

    def save(self):
        out = {k: v for k, v in self.cfg.items()}
        CONFIG_PATH.write_text(json.dumps(out, indent=2), "utf-8")
        print(f"saved {CONFIG_PATH}")
        log("settings saved")
        if self.launch_game and not self.game_started:
            self.start_game()

    def start_game(self):
        """Launch Oblivion through xOBSE (obse_loader.exe), once, after the settings were saved."""
        import subprocess
        game_dir = GAME_DIR
        loader = game_dir / "obse_loader.exe"
        if not loader.is_file():
            log(f"cannot start the game: {loader} not found")
            if self.gui:
                self.messagebox.showerror("Oblivion", f"xOBSE loader not found:\n{loader}")
            return
        self.game_started = True

        def launch():
            # Steam copy: if Steam is not running, xOBSE / the game hand the start over to a fresh Steam
            # (steam -applaunch -> OblivionLauncher.exe -> Oblivion.exe with the Steam overlay injected).
            # Every main-menu freeze happened on that route, every good session on the direct one
            # (Steam already running), so get Steam up first and then start the game directly.
            if "steamapps" in str(game_dir).lower():
                ensure_steam_running()
            try:
                (game_dir / "obse_loader.log").unlink()
            except OSError:
                pass
            subprocess.Popen([str(loader)], cwd=str(game_dir))
            log("Oblivion started through obse_loader.exe")

        import threading
        threading.Thread(target=launch, daemon=True).start()
        if self.gui:
            try:
                self.gui.iconify()                     # keep running in the taskbar, out of the way
            except Exception:
                pass
        if self.gui:
            self.b_save.configure(text="Save settings")

    def fix_ini(self):
        if native_joystick_enabled() is not True:
            self.messagebox.showinfo("Oblivion.ini", "Oblivion's built-in joystick input is already off."); return
        if self.messagebox.askyesno("Oblivion.ini", "Oblivion also reads the controller itself, which causes double "
                                    "or wrong actions. Turn that off (bUse Joystick=0)? A backup of Oblivion.ini is made. "
                                    "Restart the game afterwards."):
            bak = set_native_joystick(False)
            self.messagebox.showinfo("Oblivion.ini", f"Done. Backup: {bak.name}")

    def quit(self):
        self.mapper.release_all()
        if self.gui:
            self.gui.destroy()
        raise SystemExit(0)

    # ---------------------------------------------------------------- on-screen keyboard
    def _fullscreen(self) -> bool:
        try:
            m = re.search(r"^bFull Screen\s*=\s*(\d)", INI_PATH.read_text("cp1252", "replace"), re.M)
            return bool(m and m.group(1) == "1")
        except OSError:
            return False

    def _typing_request(self, buttons) -> bool:
        """Manual request (hold D-pad left / Create+Options). True = the on-screen keyboard handled it."""
        return self._open_keyboard(buttons, reason="manual")

    def _open_keyboard(self, buttons, reason) -> bool:
        if not self.overlay or self._fullscreen():
            log(f"keyboard request ({reason}) - game is fullscreen, using blind typing mode instead")
            return False
        self.mapper.release_all()
        self.kb = self.oskmod.KeyboardLogic(self.out, log=log)
        self.kb.prev = dict(buttons)               # buttons already held don't count as key presses
        self.kb_menu = self.ui.get("menu", 0)
        last = self.kb_last_text.get(self.kb_menu, "")
        if last:                                   # what we typed into this box last time - edit it
            self.kb.typed, self.kb.shift = last, False
        rect = self._win[2] if self._win else None
        self.kb_game_hwnd = self._win[0] if self._win else None
        self.overlay.show(rect, take_focus=True)       # Oblivion pauses; the pad only drives the keyboard
        self.overlay.draw(self.kb, self._kb_title())
        self.pad.rumble(0.5, 120)
        log(f"ON-SCREEN KEYBOARD OPEN ({reason}) menu={self.kb_menu} tiles={self.ui.get('tiles')}")
        return True

    def _close_keyboard(self, why, commit=False, enter=False):
        """Hide the keyboard and give the focus back to Oblivion. commit=True then types the text there."""
        kb = self.kb
        self.kb = None
        if self.overlay:
            self.overlay.hide()
        if kb:
            log(f"on-screen keyboard closed ({why}); text {kb.typed!r}")
        if getattr(self, "kb_game_hwnd", None):
            self.oskmod.force_foreground(self.kb_game_hwnd)
        if kb and commit:
            clear = len(self.kb_last_text.get(self.kb_menu, "")) + 2   # what we typed there before
            self.kb_last_text[self.kb_menu] = kb.typed
            # typed once Oblivion has the focus again (DirectInput only reads keys in the active window)
            self.kb_commit = {"kb": kb, "enter": enter, "clear": clear, "since": time.monotonic(), "started": False}
        self.pad.rumble(0.3, 80)

    def _pump_commit(self, now, focus_ok):
        c = self.kb_commit
        if not c["started"]:
            if not focus_ok:
                if now - c["since"] > 3.0:
                    log("could not give the focus back to Oblivion - text not typed; click the game and retry")
                    self.kb_commit = None
                elif now - c.get("retry", 0) > 0.5 and getattr(self, "kb_game_hwnd", None):
                    c["retry"] = now
                    self.oskmod.force_foreground(self.kb_game_hwnd)
                return
            if c.get("focused_at") is None:
                c["focused_at"] = now
            if now - c["focused_at"] < 0.3:                # let the game resume first
                return
            if c.get("shift_left"):
                c["kb"]._tap(0xCB, shift=True, hold=0.05)     # Shift + Left arrow (extended key)
            elif "taps" in c:
                for dik in c["taps"]:
                    c["kb"]._tap(dik, hold=0.06)
            else:
                c["kb"].commit(enter=c["enter"], clear=c.get("clear", 0))
            c["started"] = True
        c["kb"].pump()
        if c["kb"].idle():
            log("text typed into the game")
            self.kb_commit = None

    def _open_picker(self, buttons):
        if not self.overlay or self._fullscreen():
            return
        self.picker = self.oskmod.HotkeyPicker()
        self.picker.prev = dict(buttons)
        self.kb_game_hwnd = self._win[0] if self._win else None
        self.overlay.show(self._win[2] if self._win else None, take_focus=True)
        what = "spell" if self.ui.get("menu") == 1022 else "item"
        self.picker_title = f"Hotkey for the highlighted {what}"
        self.overlay.draw_picker(self.picker, self.picker_title)
        self.pad.rumble(0.5, 120)
        log(f"hotkey wheel open (menu {self.ui.get('menu')})")

    def _close_picker(self, slot):
        self.picker = None
        if self.overlay:
            self.overlay.hide()
        if self.kb_game_hwnd:
            self.oskmod.force_foreground(self.kb_game_hwnd)
        if isinstance(slot, int):
            kind, val = self.binds.get(f"Quick{slot}", ("key", 0x01 + slot))
            if kind == "key":
                # vanilla: pressing 1-8 while an item/spell is highlighted assigns it to that hotkey
                self.kb_commit = {"kb": self.oskmod.KeyboardLogic(self.out, log=log), "taps": [val],
                                  "since": time.monotonic(), "started": False}
            log(f"hotkey wheel: assign slot {slot}")
        else:
            log("hotkey wheel cancelled")
        self.pad.rumble(0.3, 80)

    def _kb_title(self):
        return {1036: "Character name", 1041: "Spell name", 1042: "Item name", 1040: "Potion name",
                1051: "Text"}.get(self.kb_menu, "Text")

    def _refresh_win(self, now):
        if now - self._win_check <= 1.0:
            return
        self._win_check = now
        had = self._win is not None
        self._win = self.oskmod.oblivion_window()
        if self._win and not had:
            log(f"Oblivion window found (pid {self._win[1]}, {self._win[2][2] - self._win[2][0]}x"
                f"{self._win[2][3] - self._win[2][1]})")
        if self._win and self.cfg.get("borderless", True) and not self._fullscreen() \
                and self._win[0] not in self._bordered_done:
            if self.oskmod.make_borderless(self._win[0]):
                log("made the Oblivion window borderless")
            self._bordered_done.add(self._win[0])

    def _freeze_tick(self, now, focus_ok):
        """Freeze probe: if Oblivion stops, log where its main thread is stuck (see oblivion_freeze.py)."""
        try:
            self.freeze.tick(now, self._win, focus_ok, extra=f"(menus {self.ui.get('menus')})")
        except Exception as exc:
            if not getattr(self, "_freeze_err", False):
                self._freeze_err = True
                log(f"freeze probe error: {exc}")

    def _update_ui_state(self, now, focus_ok, buttons):
        if not (self._win and focus_ok) or now - self._ui_check < 0.1:
            return
        self._ui_check = now
        if not self.probe.attach(self._win[1]):
            return
        prev_menu = self.ui.get("menu", 0)
        self.ui = self.probe.state()
        if self.ui.get("menus") != self._menus_logged:
            self._menus_logged = self.ui.get("menus")
            log(f"menus now: {self._menus_logged} (top {self.ui.get('menu')})")
        if self.kb is None and self.kb_commit is None and self.picker is None and self.overlay is not None:
            cross = now - self._cross_at < 0.3            # Cross pressed in the last 300 ms
            if self.ui["menu"] in self.oskmod.AUTO_OPEN_MENUS and prev_menu != self.ui["menu"]:
                self._open_keyboard(buttons, "text prompt opened")
            elif cross and self.oskmod.textbox_highlighted(self.ui):
                self._cross_at = -1.0
                self._open_keyboard(buttons, "text box selected")
        elif self.kb is not None and self.kb_menu not in self.ui.get("menus", [self.ui["menu"]]):
            self._close_keyboard("menu closed")

    def tick(self):
        now = time.monotonic(); dt = min(now - self.last, 0.05); self.last = now
        if now - self._life_check > 0.5:
            self._life_check = now
            if quit_requested():
                log("a newer copy of the controller program started - this one closes")
                self.quit()
            if self.game_started:
                if self._win:
                    self._game_seen = now
                elif self._game_seen and now - self._game_seen > 8:
                    log("Oblivion has closed - controller program exits")
                    self.quit()
        f6 = key_pressed_globally(0x75)
        if f6 and not self.f6_was:
            self.toggle()
        self.f6_was = f6
        self._refresh_win(now)
        if now - self._focus_cache[0] > 0.2:
            self._focus_cache = (now, (not self.cfg["only_when_oblivion_focused"]) or oblivion_is_focused())
        focus_ok = self._focus_cache[1]
        self._freeze_tick(now, focus_ok)
        if not self.pad.attached() and now - self.last_scan > 1.0:
            self.last_scan = now
            if self.pad.connect():
                log(f"controller connected: {self.pad.name} [{self.pad.kind}]")
                self.pad.rumble(0.5, 150)
        if not self.pad.attached():
            self.mapper.release_all()
            self.status = "Waiting for a controller (connect it in the Shadow app / Windows)."
            return
        s = self.pad.read(self.cfg["trigger_threshold"])
        if s.buttons.get("guide"):
            self.guide_down_at = self.guide_down_at or now
            if now - self.guide_down_at > 1.0:
                self.toggle(); self.guide_down_at = float("inf")
        else:
            self.guide_down_at = None
        if self.mouse_block is not None:
            # block only in NorthernUI mode (standalone mode drives the game through the mouse itself)
            self.mouse_block.set(focus_ok and self.enabled and self.mode == "northernui"
                                and self.kb is None and self.picker is None)
        if focus_ok != self.focused:
            self.focused = focus_ok
            log(f"Oblivion window {'focused' if focus_ok else 'not focused'}")
            if not focus_ok:
                self.mapper.release_all()
        if self.auto and focus_ok and now - self._nui_check > 2.0:
            self._nui_check = now
            start = oblivion_start_time()
            if start is not None:
                age = time.time() - start
                if northernui_loaded_since(start):
                    want, self.mode_note = self.companion, ""
                elif age > 25:
                    want = self.standalone
                    self.mode_note = (" · NorthernUI did NOT load (start the game with Play Oblivion.bat / "
                                      "obse_loader.exe) - using full keyboard+mouse mode")
                else:
                    want, self.mode_note = self.mapper, " · checking whether NorthernUI loaded..."
                if want is not self.mapper:
                    log(f"mode switch -> {'northernui' if want is self.companion else 'standalone'}{self.mode_note}")
                    self.mapper.release_all()
                    self.mapper = want
                    self.mode = "northernui" if want is self.companion else "standalone"
                    self.pad.rumble(0.7, 250)
        for b_, v_ in s.buttons.items():
            if v_ and not self.prev_buttons.get(b_):
                log(f"pad: {PS_NAMES.get(b_, b_)} pressed (menus {self.ui.get('menus')}, menu mode {self.ui.get('menu_mode')})")
        if s.buttons.get("a") and not self.prev_buttons.get("a"):
            self._cross_at = now
        if self.overlay is not None:
            try:
                self._update_ui_state(now, focus_ok, s.buttons)
            except Exception as exc:
                log(f"ui probe error: {exc}")
        if self.kb_commit is not None:
            self._pump_commit(now, focus_ok)
        elif self.picker is not None:
            if self.enabled:
                res = self.picker.update(s.buttons, (s.lx, s.ly), (s.rx, s.ry))
                if res is not None:
                    self._close_picker(res)
                elif self.overlay:
                    self.overlay.draw_picker(self.picker, self.picker_title)
        elif self.kb is not None:
            # the keyboard window has the focus (Oblivion is paused), so don't require focus_ok here
            if self.enabled:
                res = self.kb.update(s.buttons)
                if res in ("done", "enter"):
                    self._close_keyboard(res, commit=True, enter=res == "enter")
                elif res == "cancel":
                    self._close_keyboard("cancelled")
                elif self.overlay:
                    sig = (self.kb.r, self.kb.c, self.kb.shift, self.kb.typed)
                    if sig != self._kb_sig:
                        self._kb_sig = sig
                        self.overlay.draw(self.kb, self._kb_title())
        elif self.enabled and focus_ok:
            # in a menu = the game's own menu-mode flag, or any non-HUD menu open (Big Four = 1)
            in_menu = bool(self.ui.get("menu_mode")) or any(m not in HUD_MENUS for m in self.ui.get("menus", []))
            self.companion.last_menus = self.ui.get("menus", [])
            if self.mapper is self.companion and in_menu:
                # A menu is open: NorthernUI owns the D-pad and sticks there (console-style navigation).
                # Send nothing - no hotkeys, no wheel - so nothing can leak into the menu.
                self.companion.release_all()
                self.companion.dpad_t0 = None
                # Hotkeys are assigned with the GAME's own console quick-key menu: Triangle in the
                # inventory / magic menu (NorthernUI shows the hint). The companion stays out of it.
            else:
                self.mapper.update(s, dt)
        self.prev_buttons = dict(s.buttons)
        if now - self._ini_cache[0] > 3.0:
            self._ini_cache = (now, native_joystick_enabled())
        ini_warn = (" · Oblivion's own joystick input is ON (button above turns it off)"
                    if self._ini_cache[1] and self.mode == "standalone" else "")
        if self.mode == "northernui" and "xbox" not in self.pad.name.lower() and "xinput" not in self.pad.name.lower():
            ini_warn += " · NorthernUI needs the pad presented as an Xbox controller (Shadow setting)"
        state = "PAUSED" if not self.enabled else ("ACTIVE" if focus_ok else "waiting for Oblivion window")
        kb = " · ON-SCREEN KEYBOARD" if self.kb else ""
        menu = self.ui.get("menu") or 0
        menu_txt = f" · menu {menu}" if menu else ""
        self.status = (f"{self.mode.upper()} mode · {self.pad.name} [{self.pad.kind}] · {state} · "
                       f"layer {self.mapper.layer.upper()}{kb}{menu_txt}{ini_warn}{self.mode_note}")

    def run(self):
        print("Oblivion controller running. F6 or hold PS/Guide 1 s = pause. Ctrl+C or close window to exit.")
        for n in self.notes:
            print("note:", n)
        if self.gui:
            def loop():
                try:
                    self.tick()
                except SystemExit:
                    raise
                except Exception as exc:          # never leave keys held on an error
                    self.mapper.release_all(); self.status = f"error: {exc}"
                self.v_status.set(self.status)
                self.gui.after(8, loop)
            self.gui.after(8, loop)
            self.gui.mainloop()
        else:
            last_print = ""
            try:
                while True:
                    self.tick()
                    if getattr(self, "_tkroot", None) is not None:
                        self._tkroot.update()
                    if self.status != last_print:
                        print(self.status); last_print = self.status
                    time.sleep(0.008)
            except KeyboardInterrupt:
                self.mapper.release_all()


_INSTANCE_MUTEX = None
_QUIT_EVENT = None


def single_instance(takeover: bool = True) -> bool:
    """Make sure only one companion runs. If an older copy is still running (e.g. left open after an
    earlier game session), ask it to quit and take over. False only if it would not close."""
    global _INSTANCE_MUTEX, _QUIT_EVENT
    if sys.platform != "win32":
        return True
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = k.CreateEventW.restype = ctypes.c_void_p
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.SetEvent.argtypes = k.ResetEvent.argtypes = [ctypes.c_void_p]
    _QUIT_EVENT = k.CreateEventW(None, True, False, "Local\\OblivionControllerQuit")
    _INSTANCE_MUTEX = k.CreateMutexW(None, False, "Local\\OblivionControllerCompanion")
    # take ownership; if another copy owns it, tell that copy to quit and wait for it (max 6 s)
    r = k.WaitForSingleObject(_INSTANCE_MUTEX, 0)
    if r in (0, 0x80):                                   # WAIT_OBJECT_0 / WAIT_ABANDONED: we own it
        k.ResetEvent(_QUIT_EVENT)
        return True
    if not takeover:
        return False
    k.SetEvent(_QUIT_EVENT)
    r = k.WaitForSingleObject(_INSTANCE_MUTEX, 6000)
    k.ResetEvent(_QUIT_EVENT)
    return r in (0, 0x80)


def quit_requested() -> bool:
    """True when a newer copy of the companion asked this one to close."""
    if sys.platform != "win32" or not _QUIT_EVENT:
        return False
    k = ctypes.WinDLL("kernel32")
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    return k.WaitForSingleObject(_QUIT_EVENT, 0) == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diagnose", action="store_true", help="show what SDL sees and write controller_diagnostic.txt")
    ap.add_argument("--nogui", action="store_true")
    ap.add_argument("--mode", choices=["auto", "northernui", "standalone"], help="override the config")
    ap.add_argument("--prepare-display", action="store_true",
                    help="set Oblivion.ini to windowed desktop resolution (needed to see the on-screen keyboard)")
    ap.add_argument("--fullscreen", action="store_true", help="set Oblivion.ini back to exclusive fullscreen")
    ap.add_argument("--launch-game", action="store_true",
                    help="show 'Save settings & start Oblivion'; the game starts only after you click it")
    ap.add_argument("--native-joystick", choices=["on", "off"], help="set Oblivion.ini bUse Joystick (backs up first)")
    ap.add_argument("--print-game-dir", action="store_true", help="print the Oblivion install that will be started")
    a = ap.parse_args()
    if a.print_game_dir:
        print(GAME_DIR)
        return
    if a.prepare_display or a.fullscreen:
        import oblivion_osk as osk
        cfg = load_config()
        if a.fullscreen:
            print(osk.restore_fullscreen_ini(INI_PATH))
        elif cfg.get("on_screen_keyboard", True) and cfg.get("borderless", True):
            print(osk.prepare_borderless_ini(INI_PATH))
        else:
            print("on_screen_keyboard/borderless disabled in config - display left unchanged")
        return
    if a.native_joystick:
        print("backup:", set_native_joystick(a.native_joystick == "on"))
        return
    if a.diagnose:
        diagnose()
        return
    if not single_instance():
        msg = ("Another copy of the Oblivion controller program is running and did not close.\n"
               "Close it (taskbar), then start again - two copies would both press keys and type twice.")
        print(msg)
        try:
            ctypes.WinDLL("user32").MessageBoxW(None, msg, "Oblivion controller", 0x40)
        except Exception:
            pass
        sys.exit(1)
    try:
        Runner(gui=not a.nogui, mode=a.mode, launch_game=a.launch_game).run()
    except ImportError as exc:
        print(f"Missing library ({exc}). Run:  py -m pip install pygame-ce")
        sys.exit(1)


if __name__ == "__main__":
    main()
