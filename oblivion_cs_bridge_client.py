"""Client for the local Construction Set bridge server."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from gamepaths import game_dir  # noqa: E402  (game folder may sit beside a repo clone)

TOKEN_FILE = game_dir() / ".cs_bridge_token"
BASE = "http://127.0.0.1:43821"


def request(path: str, body: dict | None = None):
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(BASE + path, data=data, method="POST" if data is not None else "GET")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Host", "127.0.0.1:43821")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=150) as response:
            return response.status, response.headers, response.read()
    except HTTPError as exc:
        return exc.code, exc.headers, exc.read()
    except URLError as exc:
        raise RuntimeError(f"Cannot reach local bridge at {BASE}: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    sub.add_parser("windows")
    p_controls = sub.add_parser("controls")
    p_controls.add_argument("hwnd", type=int)
    p_screenshot = sub.add_parser("screenshot")
    p_screenshot.add_argument("--hwnd", type=int)
    p_screenshot.add_argument("--desktop", action="store_true")
    p_screenshot.add_argument("--method", choices=("printwindow", "grab"), default="printwindow",
                              help="printwindow works even when other windows cover the CS")
    p_click = sub.add_parser("click")
    p_click.add_argument("hwnd", type=int)
    p_click.add_argument("target", help="Control index as #N or exact control name")
    p_menu = sub.add_parser("menu")
    p_menu.add_argument("hwnd", type=int)
    p_menu.add_argument("path", help='Explicit menu path, e.g. "File->Open"')
    p_type = sub.add_parser("type")
    p_type.add_argument("hwnd", type=int)
    p_type.add_argument("target", help="Control index as #N or exact control name")
    p_type.add_argument("text")
    p_type.add_argument("--append", action="store_true", help="Append at current caret instead of replacing")
    p_keys = sub.add_parser("keys", help="Send keystrokes, pywinauto syntax: {ENTER} {ESC} ^s %%f")
    p_keys.add_argument("hwnd", type=int)
    p_keys.add_argument("keys")
    p_lv = sub.add_parser("listview", help="Read rows of a SysListView32 control")
    p_lv.add_argument("hwnd", type=int)
    p_lv.add_argument("--start", type=int, default=0)
    p_lv.add_argument("--count", type=int, default=200)
    p_lvs = sub.add_parser("listview-select", help="Select (optionally double-click) a list item")
    p_lvs.add_argument("hwnd", type=int)
    g = p_lvs.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--index", type=int)
    p_lvs.add_argument("--double", action="store_true", help="double-click to open the item's dialog")
    p_tree = sub.add_parser("tree", help="Read a SysTreeView32 control")
    p_tree.add_argument("hwnd", type=int)
    p_tree.add_argument("--depth", type=int, default=2)
    p_ts = sub.add_parser("tree-select", help=r"Select a tree node by path, e.g. \Items\Weapon")
    p_ts.add_argument("hwnd", type=int)
    p_ts.add_argument("path")
    p_wait = sub.add_parser("wait", help="Wait for a CS window whose title contains TEXT")
    p_wait.add_argument("title")
    p_wait.add_argument("--timeout", type=float, default=10)
    p_wait.add_argument("--exact", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "health":
            path, body = "/health", None
        elif args.command == "windows":
            path, body = "/windows", None
        elif args.command == "controls":
            path, body = f"/controls?hwnd={args.hwnd}", None
        elif args.command == "screenshot":
            path = "/screenshot?desktop=1" if args.desktop else f"/screenshot?hwnd={args.hwnd}&method={args.method}"
            status, headers, data = request(path)
            if status >= 400:
                print(data.decode("utf-8", "replace"), file=sys.stderr)
                return 1
            screenshot_path = headers.get("X-Screenshot-Path")
            if not screenshot_path:
                raise RuntimeError("Bridge returned no screenshot path")
            out = Path(screenshot_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            print(out)
            return 0
        elif args.command in {"click", "type"}:
            raw = args.target
            target = {"index": int(raw[1:])} if raw.startswith("#") else {"name": raw}
            body = {"hwnd": args.hwnd, **target}
            if args.command == "click":
                path = "/click"
            else:
                path = "/type"
                body.update({"text": args.text, "replace": not args.append})
        elif args.command == "menu":
            path, body = "/menu", {"hwnd": args.hwnd, "path": args.path}
        elif args.command == "keys":
            path, body = "/keys", {"hwnd": args.hwnd, "keys": args.keys}
        elif args.command == "listview":
            path, body = f"/listview?hwnd={args.hwnd}&start={args.start}&count={args.count}", None
        elif args.command == "listview-select":
            body = {"hwnd": args.hwnd, "double": args.double}
            body.update({"text": args.text} if args.text is not None else {"index": args.index})
            path = "/listview/select"
        elif args.command == "tree":
            path, body = f"/tree?hwnd={args.hwnd}&depth={args.depth}", None
        elif args.command == "tree-select":
            path, body = "/tree/select", {"hwnd": args.hwnd, "path": args.path}
        elif args.command == "wait":
            from urllib.parse import quote
            path = f"/wait?title={quote(args.title)}&timeout={args.timeout}&exact={1 if args.exact else 0}"
            body = None
        status, _, data = request(path, body)
        print(data.decode("utf-8", "replace"))
        return 0 if status < 400 else 1
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
