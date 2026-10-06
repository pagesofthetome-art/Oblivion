"""Controller check - verifies the whole controller chain before you play. Writes controller_audit.txt.

  py input_audit.py            (or double-click "Check controller.bat")

It checks, and reports PASS / FAIL for each:
  1. Steam: Steam Input must be OFF for Oblivion (otherwise Steam turns the pad into keyboard/mouse).
  2. XInput: exactly ONE controller visible to games (NorthernUI reads XInput). Two = double input.
  3. Every button / stick / trigger, pressed one after another on screen. For each input it records
     what the controller reports AND whether any keyboard or mouse events appeared at the same time.
     Any keyboard/mouse event = something (Steam Input, Shadow "gamepad as mouse", DS4Windows, Xpadder,
     reWASD, an old copy of the companion...) is converting the controller - that is what put digits
     into name boxes. The hooks only WATCH; nothing is blocked.
  4. Game setup: NorthernUI 'Console' scheme selected, NorthernUI.ini values, conflicting mods.
"""
from __future__ import annotations

import ctypes
import json
import re
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import oblivion_controller as oc          # noqa: E402  (pad reading, game paths)
import steam_check                        # noqa: E402

REPORT = HERE / "controller_audit.txt"
MYGAMES = Path.home() / "Documents" / "My Games" / "Oblivion"

# (pad input, PS5 name, what it does in Oblivion on console)
TESTS = [
    ("a", "Cross", "Activate / select"), ("b", "Circle", "Menus (journal) / back"),
    ("x", "Square", "Ready weapon"), ("y", "Triangle", "Jump"),
    ("leftshoulder", "L1", "Grab"), ("rightshoulder", "R1", "Cast spell"),
    ("lefttrigger", "L2", "Block"), ("righttrigger", "R2", "Attack"),
    ("leftstick", "L3 (press left stick)", "Sneak"), ("rightstick", "R3 (press right stick)", "Toggle view"),
    ("back", "Create", "Wait"), ("start", "Options", "Pause menu"),
    ("dpup", "D-pad up", "Hotkey 1 / menu up"), ("dpright", "D-pad right", "Hotkey 3 / menu right"),
    ("dpdown", "D-pad down", "Hotkey 5 / menu down"), ("dpleft", "D-pad left", "Hotkey 7 / menu left"),
    ("lstick", "Left stick: move it in a full circle", "Move / menu navigation"),
    ("rstick", "Right stick: move it in a full circle", "Look"),
]


# ------------------------------------------------------------------ XInput
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


def xinput_slots() -> list[int]:
    for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            x = ctypes.WinDLL(dll)
            break
        except OSError:
            x = None
    if not x:
        return []
    st = XINPUT_STATE()
    return [i for i in range(4) if x.XInputGetState(i, ctypes.byref(st)) == 0]


# ------------------------------------------------------------------ keyboard / mouse watchers (observe only)
class Watch:
    def __init__(self):
        self.events: list[tuple[float, str]] = []
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32")
        k.GetModuleHandleW.restype = ctypes.c_void_p
        HOOK = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        self.u.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOK, ctypes.c_void_p, wintypes.DWORD]
        self.u.SetWindowsHookExW.restype = ctypes.c_void_p
        self.u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self.u.CallNextHookEx.restype = ctypes.c_ssize_t
        self.u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

        def kb(code, w, l):
            if code >= 0 and w in (0x100, 0x104):                 # key down
                vk = ctypes.cast(l, ctypes.POINTER(wintypes.DWORD))[0]
                self.events.append((time.monotonic(), f"key vk=0x{vk:02X}"))
            return self.u.CallNextHookEx(None, code, w, l)

        def ms(code, w, l):
            if code >= 0 and w != 0x200:                         # ignore plain moves here, count them below
                self.events.append((time.monotonic(), {0x201: "mouse left", 0x204: "mouse right",
                                    0x207: "mouse middle", 0x20A: "mouse wheel"}.get(w, f"mouse 0x{w:X}")))
            elif code >= 0:
                self.events.append((time.monotonic(), "mouse move"))
            return self.u.CallNextHookEx(None, code, w, l)

        self._k, self._m = HOOK(kb), HOOK(ms)
        h = k.GetModuleHandleW(None)
        self.hk = self.u.SetWindowsHookExW(13, self._k, h, 0)
        self.hm = self.u.SetWindowsHookExW(14, self._m, h, 0)

    def since(self, t0: float) -> list[str]:
        return [e for t, e in self.events if t >= t0]

    def close(self):
        for h in (self.hk, self.hm):
            if h:
                self.u.UnhookWindowsHookEx(h)


# ------------------------------------------------------------------ static checks
def game_checks() -> list[tuple[str, bool, str]]:
    out = []
    ctrl = MYGAMES / "NorthernUI.ctrl.txt"
    t = ctrl.read_text("cp1252", "replace") if ctrl.is_file() else ""
    out.append(("NorthernUI uses the Console control scheme", "sUseSchemeName=Console" in t and "[Console]" in t,
                str(ctrl)))
    ini = oc.GAME_DATA / "OBSE" / "Plugins" / "NorthernUI.ini"
    try:
        it = ini.read_text("cp1252", "replace")
    except OSError:
        it = ""
    for key, want in (("bEnabled", "TRUE"), ("bDontUseEvenWhenPatched", "FALSE"), ("bMenuConsumesDPad", "TRUE"),
                      ("bUsePlaystationButtonIcons", "TRUE")):
        m = re.search(rf"^{key}\s*=\s*(\w+)", it, re.M)
        out.append((f"NorthernUI.ini {key}={want}", bool(m and m.group(1).upper() == want),
                    f"found {m.group(1) if m else 'missing'}"))
    plugins = oc.PLUGINS_TXT.read_text("cp1252", "replace").lower() if oc.PLUGINS_TXT.is_file() else ""
    out.append(("NorthernUI Hotkeys (types digits on D-pad) not active", "nuihotkeys.esp" not in plugins, ""))
    out.append(("Use WASD in Menus not installed",
                not (oc.GAME_DATA / "OBSE" / "Plugins" / "obse_wasd_menus.dll").exists(), ""))
    out.append(("xOBSE present in the game folder", (oc.GAME_DIR / "obse_loader.exe").is_file(), str(oc.GAME_DIR)))
    return out


# ------------------------------------------------------------------ interactive test
def main():
    import tkinter as tk
    lines = [f"Controller check {datetime.now():%Y-%m-%d %H:%M:%S}", f"game folder: {oc.GAME_DIR}", ""]
    results: list[tuple[str, bool, str]] = []

    info = steam_check.report()
    ok = not steam_check.needs_fix(info)
    detail = "; ".join(f"Oblivion Steam Input={u['use_steam_input'] or 'global'} layouts={u['layouts'] or 'none'}"
                       f" XboxSupport={u['xbox_support']}" for u in info["users"])
    results.append(("Steam Input is OFF for Oblivion", ok, detail))
    slots = xinput_slots()
    results.append(("Exactly one XInput controller (what NorthernUI reads)", len(slots) == 1,
                    f"connected slots: {slots}"))
    results += game_checks()

    pad = oc.Pad()
    root = tk.Tk(); root.title("Oblivion controller check"); root.geometry("760x420")
    big = tk.Label(root, font=("Segoe UI", 20, "bold"), wraplength=720); big.pack(pady=(30, 8))
    sub = tk.Label(root, font=("Segoe UI", 12), wraplength=720, fg="#555"); sub.pack()
    status = tk.Label(root, font=("Consolas", 10), wraplength=720, justify="left"); status.pack(pady=20)
    watch = Watch()
    state = {"i": 0, "t0": time.monotonic(), "held": False, "stick": set(), "done": False,
             "extra": [], "reported": []}

    def current():
        return TESTS[state["i"]] if state["i"] < len(TESTS) else None

    def show():
        t = current()
        if t:
            big.config(text=f"Press:  {t[1]}")
            sub.config(text=f"In Oblivion this is: {t[2]}      ({state['i'] + 1}/{len(TESTS)}) - "
                            "keep this window in front · Esc = skip")
        state["t0"] = time.monotonic()
        state["held"] = False
        state["stick"] = set()

    def finish():
        state["done"] = True
        watch.close()
        for name, ok, d in results:
            lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  - {d}" if d else ""))
        bad = [r for r in results if not r[1]]
        lines.append("")
        lines.append("RESULT: " + ("ALL PASS - the controller reaches the game cleanly."
                                   if not bad else f"{len(bad)} problem(s) - see FAIL lines."))
        REPORT.write_text("\n".join(lines) + "\n", "utf-8")
        big.config(text="ALL PASS" if not bad else f"{len(bad)} problem(s) found")
        sub.config(text=f"Report saved: {REPORT.name}  (Claude can read it). You can close this window.")
        status.config(text="\n".join(f"{'PASS' if ok else 'FAIL'}  {n}" for n, ok, _ in results)[-1400:])

    def skip(_e=None):
        t = current()
        if t and not state["done"]:
            results.append((f"{t[1]} -> {t[2]}", False, "skipped / not detected"))
            state["i"] += 1
            finish() if current() is None else show()

    root.bind("<Escape>", skip)

    def tick():
        if state["done"]:
            return
        if not pad.attached():
            pad.connect()
            status.config(text="Waiting for the controller..." if not pad.attached()
                          else f"Controller: {pad.name} [{pad.kind}]")
            root.after(200, tick); return
        s = pad.read(0.5)
        t = current()
        key = t[0]
        if key in ("lstick", "rstick"):
            x, y = (s.lx, s.ly) if key == "lstick" else (s.rx, s.ry)
            if (x * x + y * y) ** 0.5 > 0.7:
                state["stick"].add(int(((__import__("math").degrees(__import__("math").atan2(y, x)) + 360) % 360) // 90))
            hit = len(state["stick"]) == 4
        else:
            hit = s.buttons.get(key, False)
        other = [b for b, v in s.buttons.items() if v and b != key and b not in ("guide",)]
        if hit and not state["held"]:
            state["held"] = True
            state["press_at"] = time.monotonic()
        if state["held"] and (key in ("lstick", "rstick") or not hit):
            # released (or stick done): look at keyboard/mouse events during the press
            ev = watch.since(state["t0"])
            moves = sum(1 for e in ev if e == "mouse move")
            keys = [e for e in ev if e != "mouse move"]
            clean = not keys and moves < 3
            d = "clean" if clean else f"EXTRA INPUT while pressing it: {keys[:6]} mouse moves={moves}"
            if other:
                d += f"; other buttons also reported: {other}"
                clean = False
            results.append((f"{t[1]} -> {t[2]}", clean, d))
            status.config(text=f"{t[1]}: {'OK' if clean else d}")
            state["i"] += 1
            if current() is None:
                finish(); return
            show()
        root.after(10, tick)

    show()
    root.after(50, tick)
    root.mainloop()
    if not state["done"]:
        finish()
    print(REPORT.read_text("utf-8"))


if __name__ == "__main__":
    main()
