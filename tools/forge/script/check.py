"""`forge script-check`: compile every script's source and compare with the compiled data it ships with.

    forge script-check <corpus.jsonl.gz|plugin> [--commands F] [--sig S] [--show EDID|FormID]
                       [--fail N] [--json]

Like layout-check for records: the vanilla corpus is the test. For each script it compiles SCTX with
forge's compiler and compares
  * SCDA bytes (the verdict), with the reference list pinned to the original order and variable
    indices pinned to the original SLSD indices (both carry editing history the source can't show);
  * the reference list forge would choose on its own (the ordering rule), reported separately;
  * SCHR fields that follow from the source (ref count, size).
Failures are grouped by kind with the first differing byte and both decoded statements. Read-only.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from forge.script import bytecode as bc, commands as cmds, survey
from forge.script.compiler import Compiler, CompileError, Resolver, Var

ROOT = Path(__file__).resolve().parents[3]
DECL_RE = re.compile(r"^\s*(short|long|float|ref|int)\s+([A-Za-z_]\w*)", re.I | re.M)


def av_names() -> list[str]:
    """Actor value names in code order, from the xEdit enum already in the KB data."""
    d = json.loads((ROOT / "tools" / "forge" / "kb" / "data" / "record_schemas.json").read_text(encoding="utf-8"))
    for rec in d.values() if isinstance(d, dict) else d:
        for sub in rec.get("subrecords", []) if isinstance(rec, dict) else []:
            for f in sub.get("fields", []) or []:
                if f.get("name") == "Actor Value" and f.get("enum"):
                    return f["enum"]
    return []


def declared(sctx: str) -> dict[str, str]:
    text = "\n".join(line.split(";", 1)[0] for line in sctx.splitlines())
    return {m.group(2).casefold(): m.group(1).casefold() for m in DECL_RE.finditer(text)}


class CorpusResolver(Resolver):
    """EditorIDs and script variables from a corpus bundle, scoped to one plugin and its masters."""

    def __init__(self, names: survey.ExternalNames, rows: list[dict], load_order: list[str]):
        self.names = names
        self.order = {p.casefold(): i for i, p in enumerate(load_order)}
        self.by_edid: dict[str, list[dict]] = defaultdict(list)
        for f in names.forms.values():
            self.by_edid[f["edid"].casefold()].append(f)
        self.kinds: dict[str, dict[str, str]] = {}
        for r in rows:
            if r["sig"] == "SCPT":
                self.kinds[names.key(r["owner"], r["objid"])] = declared(r["sctx"])
        self.scope: set[str] = set()

    def set_scope(self, plugin: str) -> None:
        own = self.order.get(plugin.casefold(), 99)
        self.scope = {p for p, i in self.order.items() if i == 0 or i == own}

    def form(self, name: str) -> dict | None:
        if name.casefold() in ("player", "playerref"):
            return {"owner": "Oblivion.esm", "objid": "000014", "sig": "REFR", "edid": "player"}
        # a form is visible when the file that defines it is in scope (overrides keep the owner)
        cands = [f for f in self.by_edid.get(name.casefold(), []) if f["owner"].casefold() in self.scope]
        if not cands:
            return None
        return max(cands, key=lambda f: self.order.get(f["plugin"].casefold(), 0))

    def script_vars(self, form: dict) -> dict[str, Var] | None:
        key = self.names.key(form["owner"], form["objid"])
        f = self.names.forms.get(key)
        if f is None:
            return None
        skey = None
        if f.get("scri"):
            skey = self.names.key(*f["scri"].split(":", 1))
        elif f.get("base"):
            b = self.names.forms.get(self.names.key(*f["base"].split(":", 1)))
            if b and b.get("scri"):
                skey = self.names.key(*b["scri"].split(":", 1))
        if skey is None or skey not in self.names.vars:
            return None
        kinds = self.kinds.get(skey, {})
        return {n.casefold(): Var(i, n, kinds.get(n.casefold(), "float"))
                for i, n in self.names.vars[skey].items()}


def ref_key(r: dict) -> tuple:
    if r["kind"] == "SCRV":
        return ("v", r["var"])
    return ("f", r["owner"].casefold(), r["objid"].upper())


def first_diff(a: bytes, b: bytes) -> int:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def stmt_at(dec: bc.Decoded, off: int) -> str:
    for s in dec.stmts:
        if s.off <= off < s.off + s.size:
            return f"{s.off:04X} {s.text}"
    return "(past the end)"


def check_row(row: dict, comp: Compiler, table: cmds.CommandTable, names) -> dict:
    orig = bytes.fromhex(row["scda"])
    fixed_vars = {v["name"]: v["index"] for v in row["vars"] if v.get("index") and v.get("name")}
    fixed_refs = [ref_key(r) for r in row["refs"]]
    res = {"label": survey.label(row), "sig": row["sig"]}
    try:
        c = comp.compile(row["sctx"], row["schr"].get("type", 0), fixed_vars, fixed_refs)
    except CompileError as e:
        res.update(ok=False, kind="compile error: " + re.sub(r"'[^']*'", "<name>", re.sub(r"\('[^)]*\)", "<ref>", e.msg)), detail=str(e))
        return res
    except Exception as e:      # a compiler bug: report, never crash the survey
        res.update(ok=False, kind=f"crash: {type(e).__name__}", detail=str(e))
        return res
    if c.scda != orig:
        off = first_diff(c.scda, orig)
        dec_o = bc.Decompiler(table, row["vars"], row["refs"], names).decode(orig)
        dec_c = bc.Decompiler(table, row["vars"], row["refs"], names).decode(c.scda)
        so, sc = stmt_at(dec_o, off), stmt_at(dec_c, off)
        op = so.split(" ", 2)[1] if " " in so else so
        res.update(ok=False, kind=f"bytes differ in {op}",
                   detail=f"@{off:04X} vanilla [{so}] forge [{sc}] bytes vanilla {orig[off:off + 8].hex(' ')} "
                          f"forge {c.scda[off:off + 8].hex(' ')}")
        return res
    res["ok"] = True
    # the ordering rule, unpinned
    try:
        free = comp.compile(row["sctx"], row["schr"].get("type", 0), fixed_vars, None)
        own = [ref_key({"kind": r["kind"], "var": r.get("var"),
                        "owner": r.get("form", {}).get("owner", ""), "objid": r.get("form", {}).get("objid", "")})
               for r in free.refs]
        res["ref_order"] = "same" if own == fixed_refs else (
            "stale entries" if all(k in fixed_refs for k in own) and len(own) < len(fixed_refs) else "different")
    except CompileError:
        res["ref_order"] = "n/a"
    return res


def run(path: Path, table: cmds.CommandTable, sig: str | None = None, shows=(), fail_n: int = 0) -> dict:
    rows, names = survey.load_rows(path)
    from forge.kb.export import OFFICIAL
    plugins = list(dict.fromkeys([r["plugin"] for r in rows]))
    order = [p for p in OFFICIAL if p in plugins] + [p for p in plugins if p not in OFFICIAL]
    resolver = CorpusResolver(names, rows, order)
    comp = Compiler(table, resolver, av_names())
    total, ok = Counter(), Counter()
    kinds: Counter = Counter()
    examples: dict[str, list] = defaultdict(list)
    ref_order: Counter = Counter()
    shown = []
    for row in rows:
        if sig and row["sig"] != sig or not row["scda"]:
            continue
        if shows and row["edid"].casefold() not in shows and row["formid"].casefold() not in shows:
            continue
        resolver.set_scope(row["plugin"])
        r = check_row(row, comp, table, names)
        total[row["sig"]] += 1
        if r["ok"]:
            ok[row["sig"]] += 1
            ref_order[r.get("ref_order", "?")] += 1
        else:
            kinds[r["kind"]] += 1
            if len(examples[r["kind"]]) < 3:
                examples[r["kind"]].append(f"{r['label']}: {r['detail']}")
        if shows or (not r["ok"] and len(shown) < fail_n):
            shown.append(r)
    n, k = sum(total.values()), sum(ok.values())
    return {"scripts": n, "identical": k, "identical_by_sig": dict(ok), "total_by_sig": dict(total),
            "pass_rate": round(100.0 * k / n, 2) if n else 0.0,
            "failures": {kk: {"count": v, "examples": examples[kk]} for kk, v in kinds.most_common()},
            "ref_order": dict(ref_order), "shown": shown}


def format_report(s: dict) -> str:
    lines = [f"scripts compiled: {s['scripts']}",
             f"SCDA byte-identical: {s['identical']}/{s['scripts']} = {s['pass_rate']}%  {s['identical_by_sig']} "
             f"of {s['total_by_sig']}",
             "RESULT: " + ("PASS (S6 gate: >= 99%)" if s["pass_rate"] >= 99.0 else "FAIL (S6 gate is >= 99%)"),
             "reference list from forge's own ordering rule (identical scripts): " +
             ", ".join(f"{k} x{v}" for k, v in s["ref_order"].items())]
    if s["failures"]:
        lines.append("failures by kind:")
        for k, v in s["failures"].items():
            lines.append(f"  {v['count']:>6}  {k}")
            lines += [f"          e.g. {e}" for e in v["examples"]]
    for r in s["shown"]:
        lines.append(f"== {r['label']}: {'identical' if r['ok'] else r['kind']}" +
                     (f"\n   {r['detail']}" if r.get("detail") else ""))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    args = list(argv)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]

    def opt(name, default=None, many=False):
        vals = []
        while name in args:
            i = args.index(name)
            vals.append(args[i + 1] if i + 1 < len(args) else default)
            del args[i:i + 2]
        return vals if many else (vals[-1] if vals else default)

    commands_path = opt("--commands")
    shows = {x.casefold() for x in opt("--show", many=True)}
    fail_n = int(opt("--fail", "0"))
    sig = opt("--sig")
    if len(args) != 1 or not Path(args[0]).is_file():
        print("usage: forge script-check <corpus.jsonl.gz|plugin> [--commands F] [--show EDID] [--fail N]",
              file=sys.stderr)
        return 1
    src = Path(args[0])
    table = cmds.load(commands_path) if commands_path else cmds.load(
        src if str(src).casefold().endswith(".jsonl.gz") else None)
    if not len(table):
        print("error: no command table (vanilla_commands.jsonl or a corpus bundle)", file=sys.stderr)
        return 1
    s = run(src, table, sig, shows, fail_n)
    print(json.dumps(s, indent=1) if as_json else format_report(s))
    return 0 if s["scripts"] and s["pass_rate"] >= 99.0 else 2
