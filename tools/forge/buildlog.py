"""Build log: everything needed to repeat a build without reading the chat."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from forge import VERSION

ROOT = Path(__file__).resolve().parents[2]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def file_entry(p: Path) -> dict:
    p = Path(p)
    if not p.is_file():
        return {"path": str(p), "missing": True}
    return {"path": str(p), "size": p.stat().st_size, "sha256": sha256_file(p)}


def git_state() -> dict:
    def run(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                  timeout=20).stdout.strip()
        except Exception:
            return ""
    commit = run("rev-parse", "HEAD")
    if not commit:
        return {"commit": None}
    dirty = run("status", "--porcelain", "--", "tools", "specs")
    return {"commit": commit, "dirty_tools_or_specs": bool(dirty)}


def tool_versions(code_files: list[Path]) -> dict:
    return {
        "forge": VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git": git_state(),
        "code_sha256": {str(Path(f).relative_to(ROOT)) if Path(f).is_relative_to(ROOT) else str(f):
                        sha256_file(Path(f)) for f in code_files},
    }


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(out_dir: Path, log: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "build-log.json"
    p.write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")
    hist = out_dir.parent / "history.jsonl"
    summary = {k: log.get(k) for k in ("finished", "spec", "status", "outputs")}
    with open(hist, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, default=str) + "\n")
    return p
