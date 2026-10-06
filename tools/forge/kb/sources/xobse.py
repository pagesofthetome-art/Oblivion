"""Extract OBSE command signatures from an xOBSE source checkout (github.com/llde/xOBSE).

Facts only: name, alias, parameters, return type, the release that added it, and the
source file. The source's help strings are NOT exported (no licence file in the repo).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_URL = "https://github.com/llde/xOBSE"
DOC_URL = "https://htmlpreview.github.io/?https://github.com/llde/xOBSE/blob/master/obse_command_doc.html#{name}"

RET = {"kRetnType_Default": "number", "kRetnType_Form": "form", "kRetnType_String": "string",
       "kRetnType_Array": "array", "kRetnType_ArrayIndex": "array_index", "kRetnType_Ambiguous": "ambiguous"}



def strip_comments(src: str) -> str:
    # keep string literals intact while removing comments
    out, pos = [], 0
    for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"|//[^\n]*|/\*.*?\*/', src, re.S):
        out.append(src[pos:m.start()])
        tok = m.group(0)
        out.append(tok if tok.startswith('"') else ("\n" * tok.count("\n")))
        pos = m.end()
    out.append(src[pos:])
    return "".join(out)


def split_args(s: str) -> list[str]:
    args, depth, cur, quote = [], 0, [], False
    for i, ch in enumerate(s):
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            quote = not quote
        if quote:
            cur.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur).strip()); cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        args.append("".join(cur).strip())
    return args


def _calls(src: str, macro: str):
    for m in re.finditer(r"\b" + macro + r"\s*\(", src):
        i, depth = m.end(), 1
        while i < len(src) and depth:
            depth += {"(": 1, ")": -1}.get(src[i], 0)
            i += 1
        yield split_args(src[m.end():i - 1])


def param_tables(files: list[Path]) -> dict[str, list[dict]]:
    out = {}
    pat = re.compile(r"ParamInfo\s+(\w+)\s*\[[^\]]*\]\s*=\s*\{(.*?)\}\s*;", re.S)
    ent = re.compile(r'\{\s*"([^"]*)"\s*,\s*(\w+)\s*,\s*(\w+)\s*\}')
    for f in files:
        src = strip_comments(f.read_text("latin-1"))
        for m in pat.finditer(src):
            out[m.group(1)] = [{"name": n, "type": re.sub(r"^k(OBSE)?ParamType_", "", t),
                                "optional": o not in ("0", "false")} for n, t, o in ent.findall(m.group(2))]
    return out


def command_defs(files: list[Path]) -> dict[str, dict]:
    defs = {}
    for f in files:
        src = strip_comments(f.read_text("latin-1"))
        cat = f.stem.replace("Commands_", "") if f.stem.startswith("Commands_") else f.stem
        for macro, has_alt, has_num in (("DEFINE_COMMAND", False, True), ("DEFINE_COMMAND_DEPRECATED", False, True),
                                        ("DEFINE_COMMAND_CONDITIONAL", False, True),
                                        ("DEFINE_COMMAND_CONDITIONAL_ALTNAME", True, True),
                                        ("DEFINE_CMD_COND", False, False), ("DEFINE_CMD_ALT", True, False),
                                        ("DEFINE_COMMAND_PLUGIN", False, True)):
            for a in _calls(src, macro):
                name = a[0]
                alias = a[1] if has_alt else ""
                rest = a[2:] if has_alt else a[1:]
                # rest: description, refRequired, [numParams,] paramInfo
                params = rest[-1].strip()
                ref = rest[-3 if has_num else -2].strip()
                defs[name] = {"name": name, "alias": alias, "ref_required": ref not in ("0", "false"),
                              "params_table": None if params in ("NULL", "0") else params,
                              "conditional": "COND" in macro, "deprecated": "DEPRECATED" in macro,
                              "category": cat, "file": f.name}
        # explicit structs: CommandInfo kCommandInfo_X = { "name", "alias", 0, "help", ref, num, params, ...
        for m in re.finditer(r"CommandInfo\s+kCommandInfo_(\w+)\s*=\s*\{(.*?)\}\s*;", src, re.S):
            a = split_args(m.group(2))
            if len(a) < 7:
                continue
            name = a[0].strip('" ')
            defs[m.group(1)] = {"name": name, "alias": a[1].strip('" '), "ref_required": a[4].strip() not in ("0", "false"),
                                "params_table": None if a[6].strip() in ("NULL", "0") else a[6].strip(),
                                "conditional": False, "deprecated": "Deprecated" in (a[10] if len(a) > 10 else ""),
                                "category": cat, "file": f.name}
    return defs


def registrations(table_cpp: Path) -> list[dict]:
    """Commands in registration order with the release index that added them."""
    src = strip_comments(table_cpp.read_text("latin-1"))
    raw = table_cpp.read_text("latin-1")
    body = src[src.index("void CommandTable::Init(void)"):]
    body = body[:body.index("\nvoid CommandTable::", 10)]
    # version hints from the comments around RecordReleaseVersion() calls in the raw text
    hints = re.findall(r"(?://\s*(v?\d{4}|OBSE\s*v?[\d.\-]+)[^\n]*\n\s*)?g_scriptCommands\.RecordReleaseVersion\(\)", raw)
    out, release = [], -1
    tok = re.compile(r"g_scriptCommands\.RecordReleaseVersion\(\)|"
                     r"g_scriptCommands\.Add\(\s*&kCommandInfo_(\w+)\s*(?:,\s*(\w+))?\s*\)|"
                     r"ADD_CMD_RET\(\s*(\w+)\s*,\s*(\w+)\s*\)|ADD_CMD\s*\(\s*(\w+)\s*\)")
    for m in tok.finditer(body):
        if m.group(0).startswith("g_scriptCommands.RecordReleaseVersion"):
            release += 1
            continue
        if release < 0:
            continue          # vanilla additions for the CS build (before OBSE's first release)
        key = m.group(1) or m.group(3) or m.group(5)
        ret = m.group(2) or m.group(4) or "kRetnType_Default"
        out.append({"key": key, "release": release, "ret": RET.get(ret, ret)})
    return out, hints


def extract(xobse_root: Path) -> list[dict]:
    src_dir = xobse_root / "obse" / "obse"
    files = sorted(src_dir.glob("*.cpp")) + sorted(src_dir.glob("*.h"))
    params = param_tables(files)
    defs = command_defs(files)
    regs, _hints = registrations(src_dir / "CommandTable.cpp")
    seen, out = set(), []
    for r in regs:
        d = defs.get(r["key"])
        if d is None or d["name"] in seen or r["key"].startswith(("Test", "kTest")):
            continue
        seen.add(d["name"])
        ver = r["release"] + 8      # CommandTable::GetRequiredOBSEVersion: release index + 8
        out.append({
            "name": d["name"], "alias": d["alias"], "category": d["category"],
            "ref_required": d["ref_required"], "return_type": r["ret"],
            "params": params.get(d["params_table"], []) if d["params_table"] else [],
            "params_unparsed": bool(d["params_table"]) and d["params_table"] not in params,
            "obse_version": ver, "deprecated": d["deprecated"], "conditional": d["conditional"],
            "file": d["file"],     # source: REPO_URL/blob/master/obse/obse/<file>; doc: DOC_URL
        })
    return out


def param_type_ids(xobse_root: Path) -> dict[str, str]:
    """kParamType_* numeric ids (as stored in the game's ParamInfo.typeID) -> name."""
    src = strip_comments((Path(xobse_root) / "obse" / "obse" / "CommandTable.h").read_text("latin-1"))
    block = src[src.index("enum ParamType"):]
    block = block[:block.index("};")]
    out = {}
    for name, val in re.findall(r"kParamType_(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)", block):
        out.setdefault(str(int(val, 0)), name)
    return out
