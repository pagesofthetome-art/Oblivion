"""Inspect and automate the Oblivion Construction Set with pywinauto.

Examples:
  python oblivion_cs_helper.py windows
  python oblivion_cs_helper.py controls --hwnd 123456
  python oblivion_cs_helper.py screenshot --hwnd 123456
  python oblivion_cs_helper.py click --hwnd 123456 --index 4
  python oblivion_cs_helper.py menu --hwnd 123456 --path "File->Open"
  python oblivion_cs_helper.py type --hwnd 123456 --index 7 --text "Example"

Control indices are the indices printed by the latest `controls` output.
Actions require an explicit window handle and explicit control or menu target.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ImageGrab
from pywinauto import Desktop


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from gamepaths import game_dir  # noqa: E402  (game folder may sit beside a repo clone)

GAME_DIR = game_dir()
SCREENSHOT_DIR = GAME_DIR / "CS-Screenshots"
CS_PROCESS = "TESConstructionSet"
CS_EXE = GAME_DIR / "TESConstructionSet.exe"


def process_image_path(pid: int) -> str:
    """Return a process executable path using only read-only Win32 APIs."""
    if sys.platform != "win32":
        return ""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    open_process.restype = ctypes.c_void_p
    query = kernel32.QueryFullProcessImageNameW
    query.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    query.restype = ctypes.c_int
    close = kernel32.CloseHandle
    close.argtypes = [ctypes.c_void_p]
    close.restype = ctypes.c_int
    handle = open_process(0x1000, 0, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(buf))
        if query(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        close(handle)


def is_construction_set_window(w) -> bool:
    try:
        image = process_image_path(int(w.process_id()))
        return bool(image) and Path(image).resolve().as_posix().casefold() == CS_EXE.resolve().as_posix().casefold()
    except Exception:
        return False


def desktop(backend: str) -> Desktop:
    return Desktop(backend=backend)


def safe_text(obj: Any) -> str:
    try:
        return str(obj.window_text())
    except Exception:
        return ""


def enum_windows(backend: str, include_hidden: bool = False, construction_set_only: bool = False) -> list[dict[str, Any]]:
    result = []
    for w in desktop(backend).windows(visible_only=not include_hidden, enabled_only=False):
        try:
            info = w.element_info
            pid = int(w.process_id())
            image = process_image_path(pid)
            if construction_set_only and (
                not image or Path(image).resolve().as_posix().casefold() != CS_EXE.resolve().as_posix().casefold()
            ):
                continue
            result.append({
                "hwnd": int(w.handle),
                "pid": pid,
                "image": image,
                "title": safe_text(w),
                "class_name": str(info.class_name or ""),
                "visible": bool(w.is_visible()),
                "enabled": bool(w.is_enabled()),
                "process": str(info.name or ""),
            })
        except Exception as exc:
            result.append({"error": str(exc)})
    return result


def get_window(hwnd: int, backend: str):
    w = desktop(backend).window(handle=hwnd)
    if not w.exists(timeout=1):
        raise RuntimeError(f"Window handle {hwnd} does not exist")
    return w


def get_construction_set_window(hwnd: int, backend: str):
    w = get_window(hwnd, backend)
    if not is_construction_set_window(w):
        raise PermissionError(f"HWND {hwnd} is not owned by {CS_EXE}")
    return w


def control_rows(w, max_controls: int) -> list[dict[str, Any]]:
    rows = []
    for i, c in enumerate(w.descendants()):
        if i >= max_controls:
            break
        try:
            info = c.element_info
            rect = c.rectangle()
            rows.append({
                "index": i,
                "name": safe_text(c),
                "control_type": str(getattr(info, "control_type", "") or ""),
                "class_name": str(getattr(info, "class_name", "") or ""),
                "automation_id": str(getattr(info, "automation_id", "") or ""),
                "hwnd": int(c.handle) if getattr(c, "handle", None) else None,
                "rect": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
                "visible": bool(c.is_visible()),
                "enabled": bool(c.is_enabled()),
            })
        except Exception as exc:
            rows.append({"index": i, "error": str(exc)})
    return rows


def by_index(w, index: int):
    controls = w.descendants()
    if index < 0 or index >= len(controls):
        raise IndexError(f"Control index {index} is out of range (0..{len(controls)-1})")
    return controls[index]


def by_name(w, name: str):
    matches = []
    for c in w.descendants():
        if safe_text(c).casefold() == name.casefold():
            matches.append(c)
    if not matches:
        raise LookupError(f"No child control has the exact name {name!r}")
    if len(matches) > 1:
        raise LookupError(f"Name {name!r} matches {len(matches)} controls; use --index")
    return matches[0]


def screenshot(w, desktop_capture: bool) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = SCREENSHOT_DIR / f"construction-set-{stamp}.png"
    if desktop_capture:
        ImageGrab.grab().save(out)
    else:
        image = w.capture_as_image()
        image.save(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("win32", "uia"), default="uia")
    sub = parser.add_subparsers(dest="command", required=True)

    p_windows = sub.add_parser("windows", help="List top-level windows")
    p_windows.add_argument("--include-hidden", action="store_true")
    p_windows.add_argument("--all-processes", action="store_true", help="Include windows not owned by Construction Set")

    p_controls = sub.add_parser("controls", help="List a window's child controls")
    p_controls.add_argument("--hwnd", type=int, required=True)
    p_controls.add_argument("--limit", type=int, default=500)

    p_screenshot = sub.add_parser("screenshot", help="Save a screenshot for review")
    p_screenshot.add_argument("--hwnd", type=int, help="Window handle; required unless --desktop is used")
    p_screenshot.add_argument("--desktop", action="store_true", help="Capture the full desktop")

    p_click = sub.add_parser("click", help="Click one visible control")
    p_click.add_argument("--hwnd", type=int, required=True)
    target = p_click.add_mutually_exclusive_group(required=True)
    target.add_argument("--index", type=int)
    target.add_argument("--name")

    p_menu = sub.add_parser("menu", help="Select an explicit menu path")
    p_menu.add_argument("--hwnd", type=int, required=True)
    p_menu.add_argument("--path", required=True, help='For example "File->Open"')

    p_type = sub.add_parser("type", help="Enter text in a control")
    p_type.add_argument("--hwnd", type=int, required=True)
    type_target = p_type.add_mutually_exclusive_group(required=True)
    type_target.add_argument("--index", type=int)
    type_target.add_argument("--name")
    p_type.add_argument("--text", required=True)
    p_type.add_argument("--replace", action="store_true", help="Select existing text before typing")

    args = parser.parse_args()
    try:
        if args.command == "windows":
            print(json.dumps(enum_windows(args.backend, args.include_hidden, not args.all_processes), indent=2))
            return 0

        if args.command == "screenshot" and args.desktop:
            print(screenshot(None, True))
            return 0
        if args.command == "screenshot" and args.hwnd is None:
            parser.error("screenshot requires --hwnd unless --desktop is used")

        w = get_construction_set_window(args.hwnd, args.backend)
        if args.command == "controls":
            print(json.dumps({"hwnd": args.hwnd, "title": safe_text(w), "controls": control_rows(w, args.limit)}, indent=2))
        elif args.command == "screenshot":
            print(screenshot(w, False))
        elif args.command == "click":
            c = by_index(w, args.index) if args.index is not None else by_name(w, args.name)
            if not c.is_visible() or not c.is_enabled():
                raise RuntimeError("Refusing to click a hidden or disabled control")
            c.click_input()
            print(f"Clicked control: {safe_text(c)}")
        elif args.command == "menu":
            if not re.fullmatch(r"[^\r\n]+(?:->[^\r\n]+)+", args.path.strip()):
                raise ValueError("Menu path must use explicit labels separated by ->, such as File->Open")
            w.menu_select(args.path.strip())
            print(f"Selected menu: {args.path.strip()}")
        elif args.command == "type":
            c = by_index(w, args.index) if args.index is not None else by_name(w, args.name)
            if not c.is_visible() or not c.is_enabled():
                raise RuntimeError("Refusing to type into a hidden or disabled control")
            try:
                c.set_edit_text(args.text)
            except Exception:
                c.click_input()
                if args.replace:
                    c.type_keys("^a", set_foreground=True)
                c.type_keys(args.text, with_spaces=True, set_foreground=True)
            print(f"Entered text in control: {safe_text(c)}")
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
