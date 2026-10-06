"""Authenticated loopback bridge to the Oblivion Construction Set UI."""

from __future__ import annotations

import argparse
import hmac
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from oblivion_cs_helper import (
    CS_EXE,
    GAME_DIR,
    SCREENSHOT_DIR,
    by_index,
    by_name,
    control_rows,
    desktop,
    enum_windows,
    get_construction_set_window,
    safe_text,
    screenshot,
)
import oblivion_cs_widgets as widgets


MAX_BODY = 65536
MAX_TEXT = 12000
ROOT = Path(__file__).resolve().parent


def ensure_editor_running() -> None:
    """Start the editor only if tasklist says it is not already running."""
    if not CS_EXE.is_file():
        raise FileNotFoundError(f"Construction Set executable not found: {CS_EXE}")
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq TESConstructionSet.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if "TESConstructionSet.exe" in result.stdout:
            return
    except Exception:
        pass
    subprocess.Popen([str(CS_EXE)], cwd=str(CS_EXE.parent), close_fds=True)


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "OblivionCSBridge/1.1"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        # Keep useful request logs, never include authorization headers.
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def _authorized(self) -> bool:
        host = self.headers.get("Host", "")
        if host not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
            self._json(403, {"error": "Host must be localhost"})
            return False
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.token
        if not hmac.compare_digest(supplied, expected):
            self._json(401, {"error": "Valid bearer token required"})
            return False
        return True

    def _json(self, status: int, obj: object) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid Content-Length")
        if length < 0 or length > MAX_BODY:
            raise ValueError("Request body is too large")
        if length == 0:
            return {}
        data = self.rfile.read(length)
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON request body must be an object")
        return value

    def do_GET(self) -> None:
        if not self._authorized():
            return
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/health":
                self._json(200, {"ok": True, "editor": str(CS_EXE)})
            elif parsed.path == "/windows":
                rows = enum_windows(self.server.backend, include_hidden=True, construction_set_only=True)
                self._json(200, {"windows": rows})
            elif parsed.path == "/controls":
                hwnd = int(query["hwnd"][0])
                w = get_construction_set_window(hwnd, self.server.backend)
                self._json(200, {"hwnd": hwnd, "title": safe_text(w), "controls": control_rows(w, 1000)})
            elif parsed.path == "/screenshot":
                SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                if query.get("desktop", ["0"])[0] == "1":
                    path = screenshot(None, True)
                else:
                    hwnd = int(query["hwnd"][0])
                    w = get_construction_set_window(hwnd, self.server.backend)
                    method = query.get("method", ["printwindow"])[0]
                    path = None
                    if method == "printwindow":
                        try:
                            from datetime import datetime as _dt
                            path = SCREENSHOT_DIR / f"construction-set-{hwnd}-{_dt.now():%Y%m%d-%H%M%S}.png"
                            widgets.capture_printwindow(hwnd).save(path)
                        except Exception:
                            path = None
                    if path is None:
                        path = screenshot(w, False)
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Screenshot-Path", str(path))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/listview":
                hwnd = int(query["hwnd"][0])
                get_construction_set_window(hwnd, self.server.backend)
                start = int(query.get("start", ["0"])[0])
                count = int(query.get("count", ["500"])[0])
                self._json(200, widgets.listview_rows(hwnd, start, count))
            elif parsed.path == "/tree":
                hwnd = int(query["hwnd"][0])
                get_construction_set_window(hwnd, self.server.backend)
                depth = int(query.get("depth", ["2"])[0])
                self._json(200, widgets.tree_items(hwnd, max(0, min(depth, 6))))
            elif parsed.path == "/toolbar":
                hwnd = int(query["hwnd"][0])
                get_construction_set_window(hwnd, self.server.backend)
                self._json(200, widgets.toolbar_buttons(hwnd))
            elif parsed.path == "/menus":
                hwnd = int(query["hwnd"][0])
                get_construction_set_window(hwnd, self.server.backend)
                self._json(200, widgets.menu_tree(hwnd))
            elif parsed.path == "/wait":
                title = query["title"][0]
                timeout = float(query.get("timeout", ["10"])[0])
                exact = query.get("exact", ["0"])[0] == "1"
                row = widgets.wait_for_title(
                    lambda: enum_windows(self.server.backend, include_hidden=False, construction_set_only=True),
                    title, timeout, exact)
                if row is None:
                    self._json(404, {"error": f"No Construction Set window titled {title!r} within {timeout}s"})
                else:
                    self._json(200, {"window": row})
            else:
                self._json(404, {"error": "Unknown endpoint"})
        except Exception as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        try:
            body = self._body()
            hwnd = int(body["hwnd"])
            w = get_construction_set_window(hwnd, self.server.backend)
            if self.path == "/click":
                c = self._target(w, body)
                if not c.is_visible() or not c.is_enabled():
                    raise RuntimeError("Refusing to click a hidden or disabled control")
                c.click_input()
                self._json(200, {"ok": True, "action": "click", "control": safe_text(c)})
            elif self.path == "/menu":
                menu_path = str(body.get("path", "")).strip()
                if not menu_path or "->" not in menu_path or "\n" in menu_path or "\r" in menu_path:
                    raise ValueError("Supply an explicit menu path such as File->Open")
                w.menu_select(menu_path)
                self._json(200, {"ok": True, "action": "menu", "path": menu_path})
            elif self.path == "/type":
                text = str(body.get("text", ""))
                if len(text) > MAX_TEXT:
                    raise ValueError(f"Text exceeds {MAX_TEXT} characters")
                c = self._target(w, body)
                if not c.is_visible() or not c.is_enabled():
                    raise RuntimeError("Refusing to type into a hidden or disabled control")
                try:
                    if body.get("replace", True):
                        c.set_edit_text(text)
                    else:
                        c.click_input()
                        c.type_keys(text, with_spaces=True, set_foreground=True)
                except Exception:
                    c.click_input()
                    if body.get("replace", True):
                        c.type_keys("^a", set_foreground=True)
                    c.type_keys(text, with_spaces=True, set_foreground=True)
                self._json(200, {"ok": True, "action": "type", "control": safe_text(c), "length": len(text)})
            elif self.path == "/keys":
                keys = str(body.get("keys", ""))
                if not keys or len(keys) > 2000:
                    raise ValueError("keys must be 1..2000 characters of pywinauto key syntax")
                widgets.send_keys(w, keys)
                self._json(200, {"ok": True, "action": "keys", "window": safe_text(w), "length": len(keys)})
            elif self.path == "/listview/select":
                idx = body.get("index")
                self._json(200, widgets.listview_select(
                    hwnd, body.get("text"), None if idx is None else int(idx), bool(body.get("double", False))))
            elif self.path == "/toolbar/press":
                idx, cmd = body.get("index"), body.get("command")
                self._json(200, widgets.toolbar_press(hwnd, None if idx is None else int(idx),
                                                      None if cmd is None else int(cmd)))
            elif self.path == "/menu/command":
                self._json(200, widgets.menu_command(hwnd, int(body["command"])))
            elif self.path == "/tree/select":
                self._json(200, widgets.tree_select(hwnd, str(body.get("path", ""))))
            else:
                self._json(404, {"error": "Unknown endpoint"})
        except Exception as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})

    @staticmethod
    def _target(w, body: dict):
        has_index = "index" in body
        has_name = "name" in body
        if has_index == has_name:
            raise ValueError("Supply exactly one of index or name")
        return by_index(w, int(body["index"])) if has_index else by_name(w, str(body["name"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=43821)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--backend", choices=("uia", "win32"), default="win32")
    parser.add_argument("--no-launch-editor", action="store_true")
    args = parser.parse_args()
    if not (1024 <= args.port <= 65535):
        parser.error("--port must be between 1024 and 65535")
    try:
        if sys.stdout is None or sys.stderr is None:
            log = GAME_DIR / "CS-bridge.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            stream = open(log, "a", encoding="utf-8", buffering=1)
            if sys.stdout is None:
                sys.stdout = stream
            if sys.stderr is None:
                sys.stderr = stream
        token = args.token_file.read_text(encoding="utf-8").strip()
        if len(token) < 32:
            raise ValueError("Token file must contain a random token of at least 32 characters")
        if not args.no_launch_editor:
            ensure_editor_running()
        server = ThreadingHTTPServer(("127.0.0.1", args.port), BridgeHandler)
        server.daemon_threads = True
        server.token = token
        server.backend = args.backend
        print(f"Oblivion CS bridge listening at 127.0.0.1:{args.port}", flush=True)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"bridge startup failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
