#!/usr/bin/env python3
"""xedit_run - drive TES4Edit (xEdit 4.1.5f) headlessly for AI agents.

Commands
  install-scripts                 copy tools\\xedit-scripts\\Agent_*.pas into TES4Edit\\Edit Scripts
  run <Script.pas> [--targets A.esp B.esp]
                                  run an xEdit script with -autoload -autoexit and print its report
  qac <Plugin.esp> --yes          back up, then Quick Auto Clean the plugin (removes ITMs,
                                  undeletes+disables UDRs). MODIFIES the plugin - needs --yes.
  cmdline <Script.pas>            print the exact TES4Edit command line without running it

Notes for agents
  * -autoload loads exactly the plugins active in Plugins.txt; a target that is not active
    is not loaded. Activate it first (Oblivion launcher / Wrye Bash) or pass --plugins-txt.
  * xEdit cannot run while it already has the same Data folder open with unsaved changes;
    ask the user to close any open TES4Edit window first.
  * Reports land in <TES4Edit folder>\\Agent-Reports\\ ; xEdit's message log in
    <TES4Edit folder>\\TES4Edit_log.txt.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # ...\Desktop\Games
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gamepaths import game_dir, workspace_dir  # noqa: E402

XEDIT_DIR = workspace_dir() / "TesIvedit" / "TES4Edit 4.1.5f"
XEDIT_EXE = XEDIT_DIR / "TES4Edit.exe"
SCRIPTS_SRC = Path(__file__).resolve().parent / "xedit-scripts"
SCRIPTS_DST = XEDIT_DIR / "Edit Scripts"
REPORTS = XEDIT_DIR / "Agent-Reports"
GAME_DIR = game_dir()
DATA_DIR = GAME_DIR / "Data"
BACKUPS = GAME_DIR / "CSBackups"
OFFICIAL = {"oblivion.esm", "dlcshiveringisles.esp", "knights.esp", "dlchorsearmor.esp", "dlcmehrunesrazor.esp",
            "dlcvilelair.esp", "dlcfrostcrag.esp", "dlcbattlehorncastle.esp", "dlcspelltomes.esp",
            "dlcthievesden.esp", "dlcorrery.esp"}


def base_args(plugins_txt: Path | None) -> list[str]:
    args = [str(XEDIT_EXE), "-TES4", "-IKnowWhatImDoing", f"-D:{DATA_DIR}\\"]
    if plugins_txt:
        args.append(f"-P:{plugins_txt}")
    return args


def check_exe() -> None:
    if not XEDIT_EXE.is_file():
        sys.exit(f"error: TES4Edit.exe not found at {XEDIT_EXE}")


def install_scripts() -> list[str]:
    SCRIPTS_DST.mkdir(parents=True, exist_ok=True)
    done = []
    for src in sorted(SCRIPTS_SRC.glob("Agent_*.pas")):
        dst = SCRIPTS_DST / src.name
        if not dst.exists() or not filecmp.cmp(src, dst, shallow=False):
            shutil.copy2(src, dst)
            done.append(src.name)
    return done


def run_xedit(args: list[str], timeout: int) -> int:
    print("running:", subprocess.list2cmdline(args), flush=True)
    start = time.time()
    try:
        proc = subprocess.run(args, cwd=str(XEDIT_DIR), timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"error: TES4Edit did not exit within {timeout}s. It may be waiting on a dialog "
              "(missing master, plugin not active, error popup). Ask the user to look at the TES4Edit window.",
              file=sys.stderr)
        return 3
    print(f"TES4Edit exited with code {proc.returncode} after {time.time() - start:.0f}s")
    return proc.returncode


def show_report(name: str, max_lines: int) -> None:
    p = REPORTS / name
    if not p.is_file():
        print(f"(no {name} produced - check {XEDIT_DIR / 'TES4Edit_log.txt'})")
        return
    lines = p.read_text("cp1252", "replace").splitlines()
    print(f"\nreport: {p}  ({max(len(lines) - 1, 0)} rows)")
    for line in lines[:max_lines]:
        print("  " + line)
    if len(lines) > max_lines:
        print(f"  ... {len(lines) - max_lines} more rows in the file")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plugins-txt", type=Path, help="custom plugins.txt (default: the game's)")
    ap.add_argument("--timeout", type=int, default=1800)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install-scripts")
    r = sub.add_parser("run"); r.add_argument("script"); r.add_argument("--targets", nargs="*", default=[])
    r.add_argument("--max-lines", type=int, default=60)
    c = sub.add_parser("cmdline"); c.add_argument("script")
    q = sub.add_parser("qac"); q.add_argument("plugin"); q.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    if a.cmd == "install-scripts":
        changed = install_scripts()
        print("installed/updated:", ", ".join(changed) if changed else "(already up to date)")
        return 0

    check_exe()
    if a.cmd in ("run", "cmdline"):
        script = a.script if a.script.lower().endswith(".pas") else a.script + ".pas"
        args = base_args(a.plugins_txt) + ["-autoload", "-autoexit", f"-script:{script}"]
        if a.cmd == "cmdline":
            print(subprocess.list2cmdline(args))
            return 0
        install_scripts()
        if not (SCRIPTS_DST / script).is_file():
            sys.exit(f"error: script not found: {SCRIPTS_DST / script}")
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "scripts").mkdir(exist_ok=True)
        tf = REPORTS / "audit-targets.txt"
        if a.targets:
            tf.write_text("\n".join(a.targets) + "\n", encoding="cp1252")
        elif tf.exists():
            tf.unlink()
        rc = run_xedit(args, a.timeout)
        report = {"Agent_ConflictReport.pas": "conflicts.tsv", "Agent_PluginAudit.pas": "audit.tsv"}.get(script)
        if report:
            show_report(report, a.max_lines)
        elif script == "Agent_ExportScripts.pas":
            n = len(list((REPORTS / "scripts").glob("*.txt")))
            print(f"\n{n} script files in {REPORTS / 'scripts'}")
        return rc

    if a.cmd == "qac":
        name = Path(a.plugin).name
        if name.casefold() in OFFICIAL and name.casefold() == "oblivion.esm":
            sys.exit("error: never clean Oblivion.esm")
        src = DATA_DIR / name
        if not src.is_file():
            sys.exit(f"error: {src} not found")
        if not a.yes:
            sys.exit("refusing: qac rewrites the plugin. Re-run with --yes after the user has agreed.")
        BACKUPS.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = BACKUPS / f"{src.stem}-preQAC-{stamp}{src.suffix}"
        shutil.copy2(src, bak)
        print(f"backup: {bak}")
        args = base_args(a.plugins_txt) + ["-quickautoclean", "-autoload", "-autoexit", name]
        rc = run_xedit(args, a.timeout)
        print("Re-run: python tools\\modlint.py lint", name, "to confirm the ITM/UDR counts dropped.")
        return rc
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
