"""Install / uninstall NorthernUI from this Controller folder into Oblivion\\Data, tuned for a PS5 pad.

  py install_northernui.py              install (or update) + apply PlayStation settings
  py install_northernui.py --uninstall  remove exactly the files this installer added, restore backups
  py install_northernui.py --check      report what is installed, change nothing

What it does
  * Copies Fonts\\ menus\\ Meshes\\ OBSE\\ Textures\\ from this folder into ..\\Oblivion\\Data\\.
    Any file it would replace is backed up first to ..\\_backup-northernui\\<date>\\ and listed
    in northernui_install_manifest.json (used by --uninstall).
  * Edits Data\\OBSE\\Plugins\\NorthernUI.ini (backup kept as NorthernUI.ini.bak-<date>):
      bUsePlaystationButtonIcons=TRUE   PlayStation button icons/names
      bMenuConsumesDPad=FALSE           leave the D-pad to oblivion_controller.py (hotkeys 1-8 and the
                                        typing mode); menus are still navigated with the left stick
  * Checks prerequisites: xOBSE installed (obse_loader.exe) - NorthernUI is an OBSE plugin.
NorthernUI reads the controller through XInput (Xbox API). On Shadow, set the PS5 controller to be
presented as an Xbox controller, otherwise NorthernUI will not see it.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent / "Oblivion"
DATA = GAME / "Data"
PARTS = ["Fonts", "menus", "Meshes", "OBSE", "Textures"]
MANIFEST = HERE / "northernui_install_manifest.json"
INI_SETTINGS = {"bUsePlaystationButtonIcons": "TRUE", "bMenuConsumesDPad": "FALSE"}


def source_files():
    for part in PARTS:
        root = HERE / part
        if root.is_dir():
            for p in root.rglob("*"):
                if p.is_file():
                    yield p, p.relative_to(HERE)


def tune_ini(ini: Path, stamp: str) -> list[str]:
    text = ini.read_text("cp1252", "replace")
    changed = []
    for key, val in INI_SETTINGS.items():
        pat = rf"^({re.escape(key)}\s*=\s*)([^\s;]+)"
        m = re.search(pat, text, re.M)
        if m and m.group(2).upper() != val:
            text = re.sub(pat, rf"\g<1>{val}", text, count=1, flags=re.M)
            changed.append(f"{key}={val}")
        elif not m:
            changed.append(f"{key} not found in NorthernUI.ini (left unchanged)")
    if any("=" in c for c in changed):
        shutil.copy2(ini, ini.with_name(f"NorthernUI.ini.bak-{stamp}"))
        ini.write_text(text, "cp1252")
    return changed


def install():
    if not DATA.is_dir():
        sys.exit(f"Oblivion Data folder not found: {DATA}")
    if not (GAME / "obse_loader.exe").is_file():
        print("WARNING: xOBSE is not installed (Oblivion\\obse_loader.exe missing). NorthernUI needs it.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = HERE.parent / "_backup-northernui" / stamp
    old = json.loads(MANIFEST.read_text("utf-8")) if MANIFEST.is_file() else {"added": [], "replaced": []}
    added, replaced, same = set(old["added"]), {r["file"]: r for r in old["replaced"]}, 0
    for src, rel in source_files():
        dst = DATA / rel
        key = str(rel).replace("/", "\\")
        if dst.is_file() and dst.name.lower() == "northernui.ini":
            same += 1                                        # keep the user's existing NorthernUI settings
            continue
        if dst.is_file():
            if filecmp.cmp(src, dst, shallow=False):
                same += 1
                continue
            if key not in added and key not in replaced:      # a file that isn't ours: back it up once
                bak = backup_root / rel
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, bak)
                replaced[key] = {"file": key, "backup": str(bak)}
        else:
            added.add(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    ini = DATA / "OBSE" / "Plugins" / "NorthernUI.ini"
    notes = tune_ini(ini, stamp) if ini.is_file() else ["NorthernUI.ini missing after copy?"]
    MANIFEST.write_text(json.dumps({"installed": stamp, "added": sorted(added),
                                    "replaced": sorted(replaced.values(), key=lambda r: r["file"])}, indent=2), "utf-8")
    print(f"NorthernUI installed into {DATA}")
    print(f"  new files: {len(added)}   replaced (backed up): {len(replaced)}   already identical: {same}")
    for n in notes:
        print("  NorthernUI.ini:", n)
    print("Start the game with Oblivion\\obse_loader.exe. Check Data\\OBSE\\Plugins\\NorthernUI.log if the new UI doesn't appear.")


def uninstall():
    if not MANIFEST.is_file():
        sys.exit("No northernui_install_manifest.json - nothing installed by this script.")
    man = json.loads(MANIFEST.read_text("utf-8"))
    removed = 0
    for key in man["added"]:
        p = DATA / Path(*key.split("\\"))
        if p.is_file():
            p.unlink(); removed += 1
    for r in man["replaced"]:
        shutil.copy2(r["backup"], DATA / Path(*r["file"].split("\\")))
    # tidy empty folders NorthernUI created
    for part in PARTS:
        root = DATA / part
        if root.is_dir():
            for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                if not any(d.iterdir()):
                    d.rmdir()
    plugins = DATA / "OBSE" / "Plugins"
    for f in [plugins / "NorthernUI.log", plugins / "NorthernUI.xmlprefs.ini", *plugins.glob("NorthernUI.ini.bak-*")]:
        if f.is_file():
            f.unlink()
    MANIFEST.unlink()
    print(f"Removed {removed} files, restored {len(man['replaced'])} backed-up files.")


def check():
    dll = DATA / "OBSE" / "Plugins" / "NorthernUI.dll"
    print("xOBSE installed:", (GAME / "obse_loader.exe").is_file())
    print("NorthernUI.dll installed:", dll.is_file())
    ini = DATA / "OBSE" / "Plugins" / "NorthernUI.ini"
    if ini.is_file():
        t = ini.read_text("cp1252", "replace")
        for k in list(INI_SETTINGS) + ["bEnabled", "bEnhancedMovement360Movement"]:
            m = re.search(rf"^{k}\s*=\s*([^\s;]+)", t, re.M)
            print(f"  {k} = {m.group(1) if m else '?'}")
    print("Install manifest:", MANIFEST if MANIFEST.is_file() else "none")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--uninstall", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
    uninstall() if a.uninstall else check() if a.check else install()
