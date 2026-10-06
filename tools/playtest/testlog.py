"""Read forge_test.log (the console output captured with `scof`) and judge the run.

A run passes only when: the BEGIN marker carries this manifest's run id, the player reached the
test location (GetInCell / GetInWorldspace >> 1), every check produced a value that meets its expectation, no step hit a
console error, the END marker was written, and there was at least one check.
"""

from __future__ import annotations

import re
from pathlib import Path

VALUE_RE = re.compile(r"^(?P<fn>.*?)\s*>>\s*(?P<v>[-+]?\d+(?:\.\d+)?)\s*$")
MARK_RE = re.compile(r"FORGE\|(?P<rest>.*)$")
ERROR_RE = re.compile(r"(not found|missing parameter|invalid|unknown|expected|could not|syntax error|"
                      r"compiled script not saved|mismatched)", re.I)
OPS = {"==": lambda a, b: abs(a - b) < 1e-4, "!=": lambda a, b: abs(a - b) >= 1e-4, "<": lambda a, b: a < b,
       "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b}


def read_lines(path: Path) -> list[str]:
    raw = Path(path).read_bytes()
    return [l.strip() for l in raw.decode("cp1252", "replace").splitlines() if l.strip()]


def _is_probe(fn: str) -> bool:
    f = fn.lower().replace(" ", "")
    return "getincell" in f or "getinworldspace" in f


def parse(lines: list[str]) -> dict:
    """Split the console log into: begin/end run ids, the cell probe, and per-step outputs."""
    out = {"begin": None, "end": None, "cell": None, "in_cell": None, "steps": {}, "unmarked": [],
           "marked": False}
    cur = None                                         # None = before any marker, "cell" = after CELL
    for l in lines:
        if re.search(r"\bprintc\b", l, re.I):
            continue                                   # the echoed command, not its output
        m = MARK_RE.search(l)
        if m:
            parts = m.group("rest").split("|")
            kind = parts[0]
            out["marked"] = True
            if kind == "BEGIN":
                out["begin"] = parts[1] if len(parts) > 1 else ""
                cur = None
            elif kind == "END":
                out["end"] = parts[1] if len(parts) > 1 else ""
                cur = None
            elif kind == "CELL":
                out["cell"] = parts[1] if len(parts) > 1 else ""
                cur = "cell"
            elif kind == "STEP" and len(parts) > 1 and parts[1].isdigit():
                cur = int(parts[1])
                out["steps"].setdefault(cur, {"values": [], "errors": [], "lines": []})
            continue
        v = VALUE_RE.match(l)
        if cur == "cell":
            if v and _is_probe(v.group("fn")):
                out["in_cell"] = float(v.group("v"))
            continue
        if cur is None:
            out["unmarked"].append(l)
            if v and _is_probe(v.group("fn")) and out["in_cell"] is None:
                out["in_cell"] = float(v.group("v"))
            continue
        s = out["steps"][cur]
        s["lines"].append(l)
        if v:
            s["values"].append(float(v.group("v")))
        elif ERROR_RE.search(l):
            s["errors"].append(l)
    return out


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if v is not None else "-"


def evaluate(manifest: dict, log_path: Path | None, extra: dict | None = None) -> dict:
    """Judge a run. extra may carry runner facts: {'froze': bool, 'boot_seconds': float, ...}."""
    extra = extra or {}
    steps = manifest.get("steps", [])
    checks = [s for s in steps if s["do"] == "check"]
    results, problems = [], []
    if log_path is None or not Path(log_path).is_file():
        parsed = None
        problems.append("no forge_test.log: the scripted steps never ran")
    else:
        parsed = parse(read_lines(log_path))
        if not parsed["marked"]:
            # PrintC unavailable (no xOBSE?): match value lines to checks in order
            vals = [float(m.group("v")) for m in (VALUE_RE.match(l) for l in parsed["unmarked"]) if m]
            if vals:
                parsed["in_cell"] = vals.pop(0)
            for st in checks:
                parsed["steps"][st["n"]] = {"values": [vals.pop(0)] if vals else [], "errors": [], "lines": []}
            parsed["begin"] = manifest["run_id"] if steps else None
            parsed["end"] = manifest["run_id"] if not vals and all(parsed["steps"][c["n"]]["values"] for c in checks) else None
            problems.append("no FORGE markers in the log (is xOBSE loaded?); matched values by order")
        if parsed["begin"] != manifest["run_id"]:
            problems.append(f"log is from another run (BEGIN {parsed['begin']!r}, expected {manifest['run_id']!r})")
        if parsed["in_cell"] != 1.0:
            problems.append(f"player was not in {manifest.get('cell')} (GetInCell >> {_fmt(parsed['in_cell'])})")
        if parsed["end"] != manifest["run_id"]:
            problems.append("END marker missing: the run stopped before the last step")
    saved: dict[str, float] = {}
    for st in steps:
        if st["do"] == "wait":
            continue
        got = (parsed or {}).get("steps", {}).get(st["n"], {"values": [], "errors": [], "lines": []})
        r = {"n": st["n"], "do": st["do"], "console": st.get("console"), "errors": got["errors"]}
        if st["do"] != "check":
            r["status"] = "fail" if got["errors"] else ("ok" if parsed else "not-run")
            if got["errors"]:
                r["why"] = "; ".join(got["errors"])
            results.append(r)
            continue
        value = got["values"][-1] if got["values"] else None
        r["value"] = value
        if got["errors"] or value is None:
            r["status"] = "fail"
            r["why"] = "; ".join(got["errors"]) or "no value logged"
        else:
            if st.get("save"):
                saved[st["save"]] = value
            if "expect" in st:
                op, rhs = re.match(r"^\s*(==|!=|<=|>=|<|>)\s*(.+?)\s*$", st["expect"]).groups()
                target = saved.get(rhs[1:]) if rhs.startswith("$") else float(rhs)
                if target is None:
                    r["status"], r["why"] = "fail", f"{rhs} was never saved"
                else:
                    ok = OPS[op](value, target)
                    r["status"] = "pass" if ok else "fail"
                    r["expect"] = f"{op} {_fmt(target)}" + (f" ({rhs})" if rhs.startswith("$") else "")
                    if not ok:
                        r["why"] = f"got {_fmt(value)}, expected {r['expect']}"
            else:
                r["status"] = "saved"
        results.append(r)
    if extra.get("froze"):
        problems.insert(0, "the game froze and was closed (see freeze_report.txt)")
    failed = [r for r in results if r["status"] in ("fail", "not-run")]
    if extra.get("froze"):
        verdict = "FROZE"
    elif not checks:
        verdict = "NO-CHECKS"
        problems.append("the manifest has no checks; 'it launched' is not a pass")
    elif parsed is None:
        verdict = "NOT-RUN"
    elif failed or problems:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    passed = sum(1 for r in results if r["status"] == "pass")
    return {"verdict": verdict, "run_id": manifest.get("run_id"), "spec": manifest.get("spec"),
            "plugin": manifest.get("plugin"), "cell": manifest.get("cell"), "checks": len(checks),
            "passed": passed, "results": results, "problems": problems, **{k: v for k, v in extra.items()}}


def report_text(res: dict) -> str:
    lines = [f"forge test: {res['verdict']}  ({res['passed']}/{res['checks']} checks passed)  "
             f"{res.get('plugin') or ''} in {res.get('cell') or '?'}"]
    if res.get("boot_seconds") is not None:
        lines.append(f"  boot: {res['boot_seconds']:.1f}s from command to playing in the test cell")
    for r in res["results"]:
        tag = {"pass": "PASS", "fail": "FAIL", "ok": " ok ", "saved": "save", "not-run": "----"}[r["status"]]
        detail = ""
        if r["do"] == "check":
            detail = f"= {_fmt(r.get('value'))}" + (f"  (expect {r['expect']})" if r.get("expect") else "")
        lines.append(f"  {tag}  step {r['n']:>2} {r['do']:<9} {r.get('console') or '':<48} {detail}".rstrip())
        if r.get("why") and r["status"] in ("fail", "not-run"):
            lines.append(f"        why: {r['why']}")
    for p in res["problems"]:
        lines.append(f"  problem: {p}")
    return "\n".join(lines)
