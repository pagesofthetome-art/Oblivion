"""Check (and fix) Steam's controller handling for Oblivion.

  py steam_check.py          report only
  py steam_check.py --fix    turn Steam Input OFF for Oblivion (app 22330) - Steam must be closed

Why: with Steam Input on, Steam hides the controller from the game and converts it with a layout.
This PC had Oblivion set to the "Keyboard (WASD) and Mouse" layout (controller_xbox360_wasd.vdf):
D-pad -> number keys, sticks -> WASD/mouse, buttons -> keys. NorthernUI then never sees a gamepad,
and stray keys (digits in name boxes, mouse cursor) appear. With Steam Input OFF the game gets the
Shadow virtual Xbox 360 pad directly through XInput and NorthernUI drives it natively.

What --fix changes (backups next to each file, *.bak-oblivion-<date>):
  * userdata\\<id>\\config\\localconfig.vdf : apps\\22330  "UseSteamControllerConfig" "0"  (= Steam Input: Disabled)
  * steamapps\\common\\Steam Controller Configs\\<id>\\config\\configset_*.vdf : removes the 22330 layout
Exit code: 0 = OK (Steam Input off for Oblivion), 2 = needs fixing but Steam is running, 1 = error.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

APP = "22330"
STEAM_CANDIDATES = [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]


def steam_dir() -> Path | None:
    for d in STEAM_CANDIDATES:
        if (d / "steam.exe").is_file() or (d / "userdata").is_dir():
            return d
    return None


def steam_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"], capture_output=True,
                             text=True, timeout=10).stdout
        return "steam.exe" in out.lower()
    except Exception:
        return False


def find_block(text: str, key: str, must_contain: str | None = None) -> tuple[int, int] | None:
    """(start of '{', index of matching '}') for a "key" { ... } block (first one containing must_contain)."""
    for m in re.finditer(r'"%s"\s*\{' % re.escape(key), text):
        start = text.index("{", m.start())
        depth, i = 0, start
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[start:i]
        if must_contain is None or must_contain in body:
            return start, i
    return None


def app_setting(local: str) -> str | None:
    """Oblivion's per-game Steam Input setting. Steam keeps it in its own "22330" block (not the one with
    LastPlayed), so look through every "22330" block."""
    for m in re.finditer(r'"%s"\s*\{' % APP, local):
        start = local.index("{", m.start())
        depth, i = 0, start
        while i < len(local):
            depth += {"{": 1, "}": -1}.get(local[i], 0)
            if depth == 0:
                break
            i += 1
        v = re.search(r'"UseSteamControllerConfig"\s*"(\d+)"', local[start:i])
        if v:
            return v.group(1)
    return None


def layouts(cfgdir: Path) -> dict[str, str]:
    found = {}
    for f in cfgdir.glob("configset_*.vdf"):
        t = f.read_text("utf-8", "replace")
        blk = find_block(t, APP)
        if blk:
            m = re.search(r'"(template|workshop|autosave|selected)"\s*"([^"]*)"', t[blk[0]:blk[1]])
            found[f.name] = m.group(2) if m else "(custom)"
    return found


def report() -> dict:
    sd = steam_dir()
    info = {"steam": str(sd) if sd else None, "running": steam_running(), "users": []}
    if not sd:
        return info
    for u in (sd / "userdata").glob("*"):
        lc = u / "config" / "localconfig.vdf"
        if not lc.is_file():
            continue
        local = lc.read_text("utf-8", "replace")
        xbox = re.search(r'"SteamController_XBoxSupport"\s*"(\d)"', local)
        ps = re.search(r'"SteamController_PSSupport"\s*"(\d)"', local)
        cfgdir = sd / "steamapps" / "common" / "Steam Controller Configs" / u.name / "config"
        info["users"].append({
            "id": u.name, "localconfig": lc, "cfgdir": cfgdir,
            "use_steam_input": app_setting(local),           # None/1 = follow global, 0 = off, 2 = on
            "xbox_support": xbox.group(1) if xbox else "?",
            "ps_support": ps.group(1) if ps else "?",
            "layouts": layouts(cfgdir) if cfgdir.is_dir() else {},
        })
    return info


def steam_input_active(u) -> bool:
    """Is Steam Input applied to Oblivion? (per-game 0 = off, 2 = on, else the global Xbox setting)"""
    if u["use_steam_input"] == "0":
        return False
    if u["use_steam_input"] == "2":
        return True
    return u["xbox_support"] != "0"


def needs_fix(info) -> bool:
    return any(steam_input_active(u) for u in info["users"])


def backup(p: Path, stamp: str):
    shutil.copy2(p, p.with_name(p.name + f".bak-oblivion-{stamp}"))


def fix(info) -> list[str]:
    done, stamp = [], datetime.now().strftime("%Y%m%d-%H%M%S")
    for u in info["users"]:
        lc: Path = u["localconfig"]
        t = lc.read_text("utf-8", "replace")
        blk = find_block(t, APP, "LastPlayed") or find_block(t, APP, "UseSteamControllerConfig")
        if blk:
            body = t[blk[0]:blk[1]]
            if re.search(r'"UseSteamControllerConfig"\s*"\d+"', body):
                new = re.sub(r'("UseSteamControllerConfig"\s*)"\d+"', r'\1"0"', body, count=1)
            else:
                # indent like the line after the brace
                nl = body.find("\n")
                indent = re.match(r"\s*", body[nl + 1:]).group(0) if nl >= 0 else "\t"
                new = "{\n" + indent + '"UseSteamControllerConfig"\t\t"0"' + body[1:]
            if new != body:
                backup(lc, stamp)
                lc.write_text(t[:blk[0]] + new + t[blk[1]:], "utf-8")
                done.append(f"{lc}: Oblivion Steam Input -> Disabled")
        for name in u["layouts"]:
            f = u["cfgdir"] / name
            t = f.read_text("utf-8", "replace")
            m = re.search(r'\s*"%s"\s*\{' % APP, t)
            blk = find_block(t, APP)
            if m and blk:
                backup(f, stamp)
                f.write_text(t[:m.start()] + t[blk[1] + 1:], "utf-8")
                done.append(f"{f.name}: removed Oblivion layout ({u['layouts'][name]})")
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    a = ap.parse_args()
    info = report()
    if not info["steam"]:
        print("Steam not found - nothing to check.")
        return 0
    for u in info["users"]:
        state = {"0": "DISABLED (good)", "2": "FORCED ON", None: "follows the global setting",
                 "1": "follows the global setting"}.get(u["use_steam_input"], u["use_steam_input"])
        print(f"Steam user {u['id']}: Oblivion Steam Input = {state}; Xbox controller support = "
              f"{u['xbox_support']}; layouts for Oblivion = {u['layouts'] or 'none'}")
    if not needs_fix(info):
        print("OK: Steam leaves the controller alone in Oblivion (NorthernUI gets the real gamepad).")
        return 0
    if not a.fix:
        print("PROBLEM: Steam Input converts the controller for Oblivion. Run with --fix (Steam closed).")
        return 2
    if info["running"]:
        print("PROBLEM: Steam Input is turning your controller into keyboard + mouse for Oblivion\n"
              "(layout: Keyboard (WASD) and Mouse). Switch it off once, in Steam itself:\n"
              "  1. Steam > Library > right-click 'The Elder Scrolls IV: Oblivion' > Properties\n"
              "  2. Controller (left side) > set the drop-down to  'Disable Steam Input'\n"
              "  3. Close the window, then run Play Oblivion again.")
        return 2
    for line in fix(info):
        print("fixed:", line)
    print("OK: Steam Input is now OFF for Oblivion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
