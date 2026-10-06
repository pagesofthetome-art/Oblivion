"""Everything that touches Windows: processes, the game window, keys, the freeze probe.

The runner only talks to a Platform, so the tests drive it with a fake one. WinPlatform reuses the
Controller code that already works on Yuri's PC: SendInputOutput + DIK codes for keys
(oblivion_controller.py), oblivion_window / force_foreground / GameUIProbe (oblivion_osk.py) and
FreezeProbe (oblivion_freeze.py).
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

CONTROLLER = Path(__file__).resolve().parents[2] / "Controller"
# Oblivion menu ids (OBSE kMenuType)
MENU_MESSAGE, MENU_LOADING, MENU_PERSUASION, MENU_MAIN = 1001, 1007, 1034, 1044

CHAR_KEYS = {**{c: c for c in "abcdefghijklmnopqrstuvwxyz0123456789"}, " ": "space", ".": "period",
             "-": "minus", "'": "apostrophe", ",": "comma"}


class Platform:
    """Interface (and a harmless default for non-Windows machines)."""
    name = "none"

    def processes(self) -> list[tuple[int, str, str]]:
        return []

    def alive(self, pid: int) -> bool:
        return False

    def launch(self, exe: Path, cwd: Path):
        raise RuntimeError("launching the game needs Windows")

    def kill(self, pid: int) -> bool:
        return False

    def spawn_detached(self, argv: list[str]) -> int | None:
        return None

    def window(self, pid: int):
        return None

    def focus(self, hwnd) -> bool:
        return False

    def focused(self, pid: int) -> bool:
        return False

    def press(self, *keys: str) -> None:
        pass

    def type_text(self, text: str) -> None:
        pass

    def ui_state(self, pid: int) -> dict:
        return {"menu": 0, "menus": [], "menu_mode": False}

    def freeze_tick(self, win, focused: bool) -> bool:
        """True when the freeze probe has just reported a stuck game."""
        return False

    def hung(self, win) -> bool:
        return False

    def screenshot(self, win, path) -> bool:
        """Save a PNG of the game window (or the screen); False if not possible here."""
        return False

    def grab(self, win):
        """An image of the game window for comparisons (None if not possible)."""
        return None

    def console_visible(self, before, after) -> bool:
        """Did the top part of the screen change like the console opening? (screen fallback)"""
        return False

    def desktop_size(self) -> tuple[int, int] | None:
        return None

    def make_borderless(self, win) -> bool:
        return False

    def beep(self) -> None:
        pass

    def sleep(self, s: float) -> None:
        time.sleep(s)

    def now(self) -> float:
        return time.monotonic()


def default() -> Platform:
    return WinPlatform() if sys.platform == "win32" else Platform()


class WinPlatform(Platform):
    name = "windows"
    STEP = 0.035                     # seconds per key edge: DirectInput polls, taps need real duration

    def __init__(self):
        from ctypes import wintypes
        self.w = wintypes
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.k.OpenProcess.restype = ctypes.c_void_p
        self.k.CloseHandle.argtypes = [ctypes.c_void_p]
        self.k.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self.k.TerminateProcess.argtypes = [ctypes.c_void_p, wintypes.UINT]
        self.k.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR,
                                                      ctypes.POINTER(wintypes.DWORD)]
        if str(CONTROLLER) not in sys.path:
            sys.path.insert(0, str(CONTROLLER))
        import oblivion_controller as oc          # SendInput + DIK codes (no pygame at import time)
        import oblivion_osk as osk
        import oblivion_freeze as ofz
        self.oc, self.osk = oc, osk
        self.out = oc.SendInputOutput()
        self.dik = oc.DIK
        self.ui = osk.GameUIProbe()
        self.probe = ofz.FreezeProbe(log=self._probe_log)
        self.probe_lines: list[str] = []

    def _probe_log(self, line: str) -> None:
        self.probe_lines.append(line)

    # -- processes
    def processes(self):
        w = self.w

        class PE(ctypes.Structure):
            _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD),
                        ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", w.LONG), ("dwFlags", w.DWORD),
                        ("szExeFile", w.WCHAR * 260)]

        self.k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        self.k.Process32FirstW.argtypes = self.k.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PE)]
        snap = self.k.CreateToolhelp32Snapshot(2, 0)
        out = []
        try:
            pe = PE()
            pe.dwSize = ctypes.sizeof(PE)
            ok = self.k.Process32FirstW(snap, ctypes.byref(pe))
            while ok:
                out.append((pe.th32ProcessID, pe.szExeFile, self._path(pe.th32ProcessID)))
                ok = self.k.Process32NextW(snap, ctypes.byref(pe))
        finally:
            self.k.CloseHandle(snap)
        return out

    def _path(self, pid: int) -> str:
        h = self.k.OpenProcess(0x1000, False, pid)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = self.w.DWORD(1024)
            return buf.value if self.k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
        finally:
            self.k.CloseHandle(h)

    def alive(self, pid):
        h = self.k.OpenProcess(0x00100000, False, pid)        # SYNCHRONIZE
        if not h:
            return False
        try:
            return self.k.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT = still running
        finally:
            self.k.CloseHandle(h)

    def launch(self, exe, cwd):
        return subprocess.Popen([str(exe)], cwd=str(cwd))

    def kill(self, pid):
        h = self.k.OpenProcess(0x0001, False, pid)            # PROCESS_TERMINATE
        if not h:
            return False
        try:
            return bool(self.k.TerminateProcess(h, 1))
        finally:
            self.k.CloseHandle(h)

    def spawn_detached(self, argv):
        flags = 0x00000008 | 0x00000200 | 0x08000000          # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
        for extra in (0x01000000, 0):                          # try to break away from forge's job first
            try:
                return subprocess.Popen(argv, creationflags=flags | extra, close_fds=True,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL).pid
            except OSError:
                continue
        return None

    # -- window / input
    def window(self, pid):
        win = self.osk.oblivion_window()
        return win if win and win[1] == pid else None

    def focus(self, hwnd):
        return self.osk.force_foreground(hwnd)

    def focused(self, pid):
        hwnd = self.u.GetForegroundWindow()
        p = self.w.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        return p.value == pid

    def _tap(self, dik: int, shift: bool = False):
        if shift:
            self.out.key(self.dik["shift"], True)
            time.sleep(self.STEP)
        self.out.key(dik, True)
        time.sleep(self.STEP)
        self.out.key(dik, False)
        time.sleep(self.STEP)
        if shift:
            self.out.key(self.dik["shift"], False)
            time.sleep(self.STEP)

    def press(self, *keys):
        for k in keys:
            self._tap(self.dik[k])

    def type_text(self, text):
        for ch in text:
            if ch.isupper():
                self._tap(self.dik[ch.lower()], shift=True)
            elif ch == "_":
                self._tap(self.dik["minus"], shift=True)
            else:
                self._tap(self.dik[CHAR_KEYS[ch]])

    def ui_state(self, pid):
        if not self.ui.attach(pid):
            return {"menu": 0, "menus": [], "menu_mode": False}
        return self.ui.state()

    def freeze_tick(self, win, focused):
        before = self.probe.reports
        self.probe.tick(time.monotonic(), win, focused, extra="(forge playtest)")
        return self.probe.reports > before

    def hung(self, win):
        return bool(win) and bool(self.u.IsHungAppWindow(win[0]))

    def desktop_size(self):
        return self.osk.screen_size()

    def make_borderless(self, win):
        return bool(win) and self.osk.make_borderless(win[0])

    def beep(self):
        try:
            import winsound
            for f in (880, 660, 880):
                winsound.Beep(f, 180)
        except Exception:
            pass

    def grab(self, win):
        try:
            from PIL import ImageGrab
            return ImageGrab.grab(bbox=tuple(win[2]) if win else None, all_screens=True)
        except Exception:
            return None

    def screenshot(self, win, path):
        img = self.grab(win)
        if img is None:
            return False
        img.save(path)
        return True

    def console_visible(self, before, after):
        if before is None or after is None or before.size != after.size:
            return False
        from PIL import ImageChops, ImageStat
        w, h = before.size
        box = (0, 0, w, int(h * 0.45))                  # the console covers the top of the screen
        diff = ImageChops.difference(before.crop(box).convert("L"), after.crop(box).convert("L"))
        return ImageStat.Stat(diff).mean[0] > 12
