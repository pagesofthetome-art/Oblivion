"""Freeze probe for Oblivion.exe (read-only diagnostics, Windows only).

When Oblivion's main thread stops (Windows says "Not Responding", or the thread uses no CPU while the
game window is in front), this records WHERE it is stuck:

  * the main thread's instruction pointer and call stack as module+offset
    (e.g. "NorthernUI.dll+0x1A2B3"), found by scanning its stack for verified return addresses;
  * every window Oblivion.exe owns, visible or not - a Windows message box hidden behind the
    borderless game window blocks the game exactly like a freeze. Such a dialog is brought to the
    front so you can see and answer it, and its text is logged.

Results go to controller_log.txt and freeze_report.txt (next to this file).

How the stack is read: the main thread is suspended for well under a millisecond, its 32-bit
(WOW64) registers and stack are copied, and it is resumed at once (always, in a finally block).
Nothing in the game's memory is ever written.
"""
from __future__ import annotations

import bisect
import ctypes
import sys
import time
from datetime import datetime
from pathlib import Path

REPORT = Path(__file__).resolve().parent / "freeze_report.txt"

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
THREAD_SUSPEND_RESUME = 0x0002
THREAD_GET_CONTEXT = 0x0008
THREAD_QUERY_INFORMATION = 0x0040
WOW64_CONTEXT_FLAGS = 0x00010000 | 0x1 | 0x2          # i386 | CONTROL | INTEGER
CTX_SIZE = 716
OFF_EBP, OFF_EIP, OFF_ESP = 180, 184, 196
LIST_MODULES_32BIT = 0x01


class FreezeProbe:
    CHECK_EVERY = 2.0        # seconds between checks
    IDLE_CPU = 0.02          # main thread below 2 % of one core = blocked / waiting
    SAME_NEEDED = 3          # identical stack this many checks in a row = stuck (about 6 s)
    MAX_REPORTS = 6

    def __init__(self, log=print):
        self.log = log
        self.ok = sys.platform == "win32"
        self.pid = self.tid = None
        self.hp = self.ht = None
        self.mods: list[tuple[int, int, str]] = []
        self._bases: list[int] = []
        self._mods_t = 0.0
        self._last = 0.0
        self._cpu = None
        self._sig = None
        self._same = 0
        self._reported: set = set()
        self.reports = 0
        self._hung_logged = False
        if not self.ok:
            return
        from ctypes import wintypes
        self.w = wintypes
        k = self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        u = self.u = ctypes.WinDLL("user32", use_last_error=True)
        k.OpenProcess.restype = k.OpenThread.restype = ctypes.c_void_p
        k.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
        k.Wow64SuspendThread.argtypes = [ctypes.c_void_p]
        k.Wow64SuspendThread.restype = wintypes.DWORD
        k.ResumeThread.argtypes = [ctypes.c_void_p]
        k.ResumeThread.restype = wintypes.DWORD
        k.Wow64GetThreadContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k.GetThreadTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
        k.K32EnumProcessModulesEx.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
                                              ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        k.K32GetModuleBaseNameW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
        k.K32GetModuleInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
        u.IsHungAppWindow.argtypes = [wintypes.HWND]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p,
                                          wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.UINT]
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        u.GetWindow.restype = wintypes.HWND

    # ------------------------------------------------------------------ attach / helpers
    def _attach(self, hwnd, pid) -> bool:
        if pid == self.pid and self.hp and self.ht:
            return True
        self.close()
        tid = self.u.GetWindowThreadProcessId(hwnd, None)        # the thread that owns the game window
        hp = self.k.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        ht = self.k.OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, False, tid)
        if not hp or not ht:
            for h in (hp, ht):
                if h:
                    self.k.CloseHandle(h)
            return False
        self.pid, self.tid, self.hp, self.ht = pid, tid, hp, ht
        self.mods, self._bases, self._mods_t, self._cpu, self._sig, self._same = [], [], 0.0, None, None, 0
        self._hung_logged = False
        return True

    def close(self):
        for h in (self.hp, self.ht):
            if h:
                self.k.CloseHandle(h)
        self.hp = self.ht = self.pid = self.tid = None

    def _read(self, addr, n) -> bytes:
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        self.k.ReadProcessMemory(self.hp, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
        return buf.raw[:got.value]

    def _read_pages(self, addr, n) -> bytes:
        """Read up to n bytes from addr page by page, stopping at the first unreadable page
        (the top of the thread's stack)."""
        out = b""
        while len(out) < n:
            chunk = min(0x1000 - ((addr + len(out)) & 0xFFF), n - len(out))
            part = self._read(addr + len(out), chunk)
            out += part
            if len(part) < chunk:
                break
        return out

    def _modules(self):
        if self.mods and time.monotonic() - self._mods_t < 30:
            return self.mods
        arr = (ctypes.c_void_p * 1024)()
        need = self.w.DWORD(0)
        if not self.k.K32EnumProcessModulesEx(self.hp, arr, ctypes.sizeof(arr), ctypes.byref(need), LIST_MODULES_32BIT):
            return self.mods
        mods = []
        info = (ctypes.c_ubyte * 24)()
        name = ctypes.create_unicode_buffer(260)
        for i in range(min(1024, need.value // ctypes.sizeof(ctypes.c_void_p))):
            hm = arr[i]
            if not hm:
                continue
            if not self.k.K32GetModuleInformation(self.hp, hm, info, 24):
                continue
            base = int.from_bytes(bytes(info[0:8]), "little")
            size = int.from_bytes(bytes(info[8:12]), "little")
            self.k.K32GetModuleBaseNameW(self.hp, hm, name, 260)
            mods.append((base, size, name.value))
        self.mods, self._mods_t = sorted(mods), time.monotonic()
        self._bases = [m[0] for m in self.mods]
        return self.mods

    def _where(self, addr):
        i = bisect.bisect_right(self._bases, addr) - 1
        if i >= 0:
            base, size, name = self.mods[i]
            if addr < base + size:
                return name, addr - base
        return None

    def _sym(self, addr) -> str:
        w = self._where(addr)
        return f"{w[0]}+0x{w[1]:X}" if w else f"0x{addr:08X}"

    def _is_return_address(self, addr) -> bool:
        """True if the bytes just before addr are a CALL instruction."""
        b = self._read(addr - 7, 7)
        if len(b) != 7:
            return False
        if b[2] == 0xE8:                                   # call rel32
            return True
        for n in (2, 3, 6, 7):                             # call r/m32 (FF /2) of length n
            op, modrm = b[7 - n], b[8 - n] if n > 1 else 0
            if op == 0xFF and (modrm >> 3) & 7 == 2:
                return True
        return False

    def _cpu_seconds(self) -> float | None:
        t = [ctypes.c_ulonglong() for _ in range(4)]
        if not self.k.GetThreadTimes(self.ht, *[ctypes.byref(x) for x in t]):
            return None
        return (t[2].value + t[3].value) / 1e7

    # ------------------------------------------------------------------ sampling
    def sample(self) -> dict | None:
        """Suspend the main thread for an instant, copy registers + stack, resume. Read-only."""
        ctx = ctypes.create_string_buffer(CTX_SIZE)
        ctypes.memmove(ctx, WOW64_CONTEXT_FLAGS.to_bytes(4, "little"), 4)
        if self.k.Wow64SuspendThread(self.ht) == 0xFFFFFFFF:
            return None
        try:
            ok = self.k.Wow64GetThreadContext(self.ht, ctx)
            raw = ctx.raw
            esp = int.from_bytes(raw[OFF_ESP:OFF_ESP + 4], "little")
            stack = self._read_pages(esp, 0x8000) if ok else b""
        finally:
            self.k.ResumeThread(self.ht)
        if not ok:
            return None
        eip = int.from_bytes(raw[OFF_EIP:OFF_EIP + 4], "little")
        ebp = int.from_bytes(raw[OFF_EBP:OFF_EBP + 4], "little")
        self._modules()
        frames = [self._sym(eip)]
        for i in range(0, len(stack) - 3, 4):
            v = int.from_bytes(stack[i:i + 4], "little")
            if self._where(v) and self._is_return_address(v):
                frames.append(self._sym(v))
                if len(frames) >= 40:
                    break
        return {"eip": eip, "esp": esp, "ebp": ebp, "frames": frames}

    # ------------------------------------------------------------------ windows of the game
    def windows(self) -> list[dict]:
        out = []
        u, w = self.u, self.w
        pid = self.pid

        @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        def cb(hwnd, _):
            p = w.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid:
                cls = ctypes.create_unicode_buffer(128); u.GetClassNameW(hwnd, cls, 128)
                title = ctypes.create_unicode_buffer(256); u.GetWindowTextW(hwnd, title, 256)
                r = w.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
                out.append({"hwnd": hwnd, "class": cls.value, "title": title.value,
                            "visible": bool(u.IsWindowVisible(hwnd)),
                            "rect": (r.left, r.top, r.right, r.bottom)})
            return True

        u.EnumWindows(cb, 0)
        for win in out:
            if win["class"] == "#32770":                    # a Windows dialog / message box
                win["text"] = self._dialog_text(win["hwnd"])
        return out

    def _dialog_text(self, hwnd) -> str:
        u, w = self.u, self.w
        texts = []

        @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        def cb(child, _):
            buf = ctypes.create_unicode_buffer(1024)
            res = ctypes.c_size_t(0)
            # WM_GETTEXT with a timeout (SMTO_ABORTIFHUNG) - never blocks on a hung window
            if u.SendMessageTimeoutW(child, 0x000D, 1024, buf, 0x0002, 500, ctypes.byref(res)) and buf.value:
                texts.append(buf.value.replace("\r", " ").replace("\n", " "))
            return True

        u.EnumChildWindows(hwnd, cb, 0)
        return " | ".join(texts)

    def _show_dialog(self, hwnd):
        """Bring a (possibly hidden) Oblivion message box in front of the game window."""
        HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
        flags = 0x0001 | 0x0002 | 0x0040 | 0x4000           # NOSIZE | NOMOVE | SHOWWINDOW | ASYNC (never blocks)
        self.u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        self.u.SetForegroundWindow(hwnd)
        self.u.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)

    # ------------------------------------------------------------------ main entry (call often)
    def tick(self, now: float, game_win, focused: bool, extra: str = ""):
        """game_win = (hwnd, pid, rect) of Oblivion's window or None. Cheap unless the game looks stuck."""
        if not self.ok or not game_win or now - self._last < self.CHECK_EVERY:
            return
        dt = now - self._last if self._last else self.CHECK_EVERY
        self._last = now
        hwnd, pid = game_win[0], game_win[1]
        if not self._attach(hwnd, pid):
            return
        hung = bool(self.u.IsHungAppWindow(hwnd))
        cpu = self._cpu_seconds()
        busy = None
        if cpu is not None and self._cpu is not None:
            busy = (cpu - self._cpu) / max(dt, 0.001)
        self._cpu = cpu
        # Only look closer when the game is in front (Oblivion idles on purpose when it's in the background)
        suspicious = hung or (focused and busy is not None and busy < self.IDLE_CPU)
        if not suspicious:
            self._sig, self._same, self._hung_logged = None, 0, False
            return
        s = self.sample()
        if not s:
            return
        sig = tuple(s["frames"][:8])
        self._same = self._same + 1 if sig == self._sig else 1
        self._sig = sig
        if (hung and not self._hung_logged) or (self._same >= self.SAME_NEEDED and sig not in self._reported):
            self._hung_logged = self._hung_logged or hung
            self._reported.add(sig)
            self.report(s, hung, busy, extra)

    def report(self, s, hung, busy, extra):
        if self.reports >= self.MAX_REPORTS:
            return
        self.reports += 1
        why = "Windows reports NOT RESPONDING" if hung else f"main thread idle ({(busy or 0) * 100:.1f}% CPU)"
        lines = [f"=== FREEZE PROBE {datetime.now():%Y-%m-%d %H:%M:%S}: Oblivion stuck - {why} {extra}".rstrip(),
                 f"main thread {self.tid}: EIP {self._sym(s['eip'])}  ESP 0x{s['esp']:08X}  EBP 0x{s['ebp']:08X}",
                 "call stack (newest first, return addresses found on the stack):"]
        lines += [f"  {f}" for f in s["frames"]]
        try:
            wins = self.windows()
        except Exception as exc:                            # never let diagnostics break the companion
            wins = []
            lines.append(f"(window list failed: {exc})")
        lines.append("windows owned by Oblivion.exe:")
        for win in wins:
            lines.append(f"  [{win['class']}] '{win['title']}' visible={win['visible']} rect={win['rect']}"
                         + (f"  TEXT: {win['text']}" if win.get("text") else ""))
        dialogs = [win for win in wins if win["class"] == "#32770"]
        for d in dialogs:
            try:
                self._show_dialog(d["hwnd"])
                lines.append(f"  -> brought the dialog '{d['title']}' to the front")
            except Exception:
                pass
        lines.append("modules: " + ", ".join(f"{n}@{b:08X}" for b, _, n in self.mods))
        text = "\n".join(lines)
        for l in lines[:-1]:
            self.log(l)
        try:
            with open(REPORT, "a", encoding="utf-8") as fh:
                fh.write(text + "\n\n")
        except OSError:
            pass
