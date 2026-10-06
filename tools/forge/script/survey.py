"""`forge script-decode`: run the SCDA decompiler over a plugin or a script corpus bundle.

    forge script-decode <plugin.esm|corpus.jsonl.gz> [--commands F] [--show EDID|FormID ...]
                        [--source] [--fail N] [--sig SCPT|QUST|INFO] [--json]

Without --show it prints the survey: how many scripts decode with no leftover bytes (the S1 gate is
100%), failures grouped by kind with examples, what the jump fields count, SCHR consistency, and
the block-type codes matched against the `begin` names in the source text. Read-only.
"""

from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from forge.script import bytecode as bc, commands as cmds


def iter_rows(path: Path, sig: str | None = None):
    name = str(path).casefold()
    if name.endswith(".jsonl") or name.endswith(".jsonl.gz"):
        opener = gzip.open if name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if '"row": "script"' not in line[:40]:
                    continue
                row = json.loads(line)
                if not sig or row["sig"] == sig:
                    yield row
        return
    from forge.script.extract import iter_scripts, resolve_refs
    forms: dict = {}
    rows = [row for row, _ in iter_scripts(path, forms) if not sig or row["sig"] == sig]
    for row in rows:
        resolve_refs(row, forms)
        yield row


def label(row: dict) -> str:
    return f"{row['plugin']}:{row['formid']} {row['sig']} {row['edid'] or '-'}" + (f" [{row['ctx']}]" if row["ctx"] else "")


def decode_row(row: dict, table: cmds.CommandTable) -> bc.Decoded:
    return bc.Decompiler(table, row["vars"], row["refs"]).decode(bytes.fromhex(row["scda"]))


def survey(rows, table: cmds.CommandTable, fail_listings: int = 0) -> dict:
    total, ok, empty = Counter(), Counter(), 0
    fails: dict[str, list] = defaultdict(list)
    fail_count: Counter = Counter()
    jumps: Counter = Counter()
    header: Counter = Counter()
    blocks: dict[int, Counter] = defaultdict(Counter)
    block_mismatch = 0
    first_stmt: Counter = Counter()
    unknown_ops: Counter = Counter()
    listings = []
    for row in rows:
        total[row["sig"]] += 1
        if not row["scda"]:
            empty += 1
            continue
        dec = decode_row(row, table)
        jumps.update(dec.jumps)
        header.update(bc.check_header(row, dec))
        if dec.stmts:
            first_stmt[dec.stmts[0].name] += 1
        for i in dec.issues:
            if i.kind == "unknown opcode":
                unknown_ops[i.detail] += 1
        if dec.ok:
            ok[row["sig"]] += 1
            begins = [s.block for s in dec.stmts if s.op == 0x10]
            names = bc.source_blocks(row["sctx"])
            if len(begins) == len(names):
                for code, n in zip(begins, names):
                    blocks[code][n.casefold()] += 1
            else:
                block_mismatch += 1
        else:
            kind = dec.issues[0].kind
            fail_count[kind] += 1
            if len(fails[kind]) < 3:
                i = dec.issues[0]
                fails[kind].append(f"{label(row)} @{i.off:04X} {i.detail}")
            if len(listings) < fail_listings:
                listings.append(f"== {label(row)}\n{bc.listing(dec)}")
    n_total, n_ok = sum(total.values()) - empty, sum(ok.values())
    block_names = {}
    for code, names in sorted(blocks.items()):
        known = table.blocks.get(code)
        block_names[code] = {"table": known.name if known else None, "source": dict(names.most_common(3))}
    return {
        "scripts": dict(total), "with_bytecode": n_total, "empty": empty,
        "decoded_ok": n_ok, "decoded_ok_by_sig": dict(ok),
        "pass_rate": round(100.0 * n_ok / n_total, 2) if n_total else 0.0,
        "failures": {k: {"count": v, "examples": fails[k]} for k, v in fail_count.most_common()},
        "unknown_opcodes": dict(unknown_ops.most_common(20)),
        "jumps": dict(sorted(jumps.items())), "schr": dict(header), "first_statement": dict(first_stmt),
        "block_types": block_names, "block_count_mismatch": block_mismatch,
        "commands_loaded": len(table), "block_types_loaded": len(table.blocks),
        "listings": listings,
    }


def format_survey(s: dict) -> str:
    lines = [f"scripts: {s['scripts']}  (with bytecode {s['with_bytecode']}, empty {s['empty']})",
             f"commands loaded: {s['commands_loaded']}, block types loaded: {s['block_types_loaded']}",
             f"decoded with no leftover bytes: {s['decoded_ok']}/{s['with_bytecode']} = {s['pass_rate']}%  "
             f"{s['decoded_ok_by_sig']}",
             "RESULT: " + ("PASS (S1 gate: 100%)" if s["with_bytecode"] and s["decoded_ok"] == s["with_bytecode"]
                           else "FAIL (S1 gate is 100%)")]
    if s["failures"]:
        lines.append("failures by kind:")
        for k, v in s["failures"].items():
            lines.append(f"  {v['count']:>6}  {k}")
            lines += [f"          e.g. {e}" for e in v["examples"]]
    if s["unknown_opcodes"]:
        lines.append("unknown opcodes: " + ", ".join(f"{k} x{v}" for k, v in s["unknown_opcodes"].items()))
    lines.append("jump fields (which candidate meaning matched):")
    lines += [f"  {v:>6}  {k}" for k, v in s["jumps"].items()]
    lines.append("SCHR checks: " + (", ".join(f"{k} x{v}" for k, v in s["schr"].items()) or "all consistent"))
    lines.append("first statement: " + ", ".join(f"{k} x{v}" for k, v in s["first_statement"].items()))
    lines.append(f"block types (code: exe table name | names in source text), "
                 f"{s['block_count_mismatch']} scripts with begin-count mismatch:")
    for code, b in s["block_types"].items():
        lines.append(f"  {code:>3}: {b['table'] or '?'} | " + ", ".join(f"{n} x{c}" for n, c in b["source"].items()))
    lines += s["listings"]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    args = list(argv)
    as_json = "--json" in args
    with_source = "--source" in args
    args = [a for a in args if a not in ("--json", "--source")]

    def opt(name, default=None, many=False):
        vals = []
        while name in args:
            i = args.index(name)
            vals.append(args[i + 1] if i + 1 < len(args) else default)
            del args[i:i + 2]
        return vals if many else (vals[-1] if vals else default)

    commands_path = opt("--commands")
    shows = [x.casefold() for x in opt("--show", many=True)]
    fail_n = int(opt("--fail", "0"))
    sig = opt("--sig")
    if len(args) != 1:
        print("usage: forge script-decode <plugin|corpus> [--commands F] [--show EDID|FormID] [--fail N]",
              file=sys.stderr)
        return 1
    src = Path(args[0])
    if not src.is_file():
        print(f"error: no such file {src}", file=sys.stderr)
        return 1
    table = cmds.load(commands_path) if commands_path else cmds.load(
        src if str(src).casefold().endswith(".jsonl.gz") else None)
    if not len(table):
        print("note: no command table loaded (vanilla_commands.jsonl / corpus); opcodes show raw", file=sys.stderr)
    rows = iter_rows(src, sig)
    if shows:
        found = 0
        for row in rows:
            if row["edid"].casefold() in shows or row["formid"].casefold() in shows:
                found += 1
                dec = decode_row(row, table)
                if as_json:
                    print(json.dumps({"script": label(row), "ok": dec.ok,
                                      "statements": [vars(st) for st in dec.stmts],
                                      "issues": [vars(i) for i in dec.issues], "jumps": dict(dec.jumps)}))
                    continue
                print(f"== {label(row)}  ({'ok' if dec.ok else 'FAILED'})")
                if with_source:
                    print("-- source\n" + row["sctx"].replace("\r\n", "\n") + "\n-- decoded")
                print(bc.listing(dec))
        return 0 if found else 2
    s = survey(rows, table, fail_n)
    print(json.dumps(s, indent=1) if as_json else format_survey(s))
    return 0 if s["with_bytecode"] and s["decoded_ok"] == s["with_bytecode"] else 2
