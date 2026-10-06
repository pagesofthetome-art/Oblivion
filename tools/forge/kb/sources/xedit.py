"""Extract TES4 record layouts from xEdit's wbDefinitionsTES4.pas (MPL-2.0).

Output per record: its subrecords in order, with kind, required/repeating flags, FormID
targets and, for fixed structs, the field layout (name, type, offset, size). Only structure
facts are exported; xEdit's code is not copied.
"""

from __future__ import annotations

import re
from pathlib import Path

URL = "https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.6/Core/wbDefinitionsTES4.pas"
LICENSE = "MPL-2.0 (xEdit)"
SIG = re.compile(r"^[A-Z][A-Z0-9_]{3}$")
INT_SIZE = {"itU8": 1, "itS8": 1, "itU16": 2, "itS16": 2, "itU32": 4, "itS32": 4, "itU64": 8, "itS64": 8}

_TOK = re.compile(r"""
    (?P<ws>\s+)|(?P<c1>\{[^}]*\})|(?P<c2>\(\*.*?\*\))|(?P<c3>//[^\n]*)|
    (?P<str>'(?:[^']|'')*')|(?P<num>\$[0-9A-Fa-f]+|\d+(?:\.\d+)?)|
    (?P<id>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>:=|<>|<=|>=|[()\[\],.;:+\-*/=<>^@#])
""", re.S | re.X)


def tokenize(src: str):
    out = []
    for m in _TOK.finditer(src):
        k = m.lastgroup
        if k in ("ws", "c1", "c2", "c3"):
            continue
        out.append((k, m.group(k)))
    return out


class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else ("eof", "")

    def take(self):
        tok = self.peek(); self.i += 1; return tok

    def expr(self):
        node = self.unary()
        while self.peek()[1] in ("+", "-", "*", "/", "or", "and", "=", "<>"):
            self.take(); self.unary()          # operands beyond the first carry no layout facts
        return node

    def unary(self):
        while self.peek()[1] in ("-", "not", "@"):
            self.take()
        return self.postfix(self.primary())

    def primary(self):
        k, v = self.take()
        if k == "str":
            return {"str": v[1:-1].replace("''", "'")}
        if k == "num":
            return {"num": int(v[1:], 16) if v.startswith("$") else float(v)}
        if v == "[":
            return {"list": self.args("]")}
        if v == "(":
            e = self.expr()
            if self.peek()[1] == ",":          # Pascal record literal / tuple: keep elements
                items = [e]
                while self.peek()[1] == ",":
                    self.take(); items.append(self.expr())
                e = {"list": items}
            if self.peek()[1] == ")":
                self.take()
            return e
        if k == "id":
            if self.peek()[1] == "(":
                self.take()
                return {"fn": v, "args": self.args(")"), "methods": []}
            return {"id": v, "methods": []}
        return {"junk": v}

    def postfix(self, node):
        while self.peek()[1] == "." and self.peek(1)[0] == "id":
            self.take(); _, name = self.take()
            args = []
            if self.peek()[1] == "(":
                self.take(); args = self.args(")")
            if isinstance(node, dict) and "methods" in node:
                node["methods"].append((name, args))
        return node

    def args(self, close):
        out = []
        if self.peek()[1] == close:
            self.take(); return out
        while True:
            out.append(self.expr())
            k, v = self.take()
            if v == close or k == "eof":
                return out
            if v != ",":                      # skip anything unexpected up to the next separator
                depth = 0
                while True:
                    k2, v2 = self.peek()
                    if k2 == "eof":
                        return out
                    if v2 in "([":
                        depth += 1
                    elif v2 in ")]":
                        if depth == 0:
                            break
                        depth -= 1
                    elif v2 == "," and depth == 0:
                        break
                    self.take()
                k, v = self.take()
                if v == close:
                    return out


def parse_defs(src: str):
    body = src[src.index("procedure DefineTES4;", src.index("implementation")):]
    p = Parser(tokenize(body))
    vars_, records = {}, []
    while p.peek()[0] != "eof":
        k, v = p.peek()
        if k == "id" and p.peek(1)[1] == ":=":
            p.take(); p.take()
            vars_[v] = p.expr()
            continue
        if k == "id" and v in ("wbRecord", "wbRefRecord") and p.peek(1)[1] == "(":
            records.append(p.expr())
            continue
        p.take()
    return vars_, records


def _name(args):
    for a in args:
        if "str" in a:
            return a["str"]
    return ""


def _sigs(node):
    return [x["id"] for x in node.get("list", []) if "id" in x and SIG.match(x["id"])]


class Interp:
    def __init__(self, vars_):
        self.vars = vars_

    def resolve(self, node, depth=0):
        while "id" in node and node["id"] in self.vars and depth < 20:
            m = node.get("methods", [])
            node = dict(self.vars[node["id"]])
            node["methods"] = list(node.get("methods", [])) + m
            depth += 1
        return node

    def fields(self, items, prefix=""):
        """Flatten struct members to (name, type, size|None, formid)."""
        out = []
        for it in items:
            it = self.resolve(it)
            fn = it.get("fn", "")
            a = it.get("args", [])
            nm = prefix + (_name(a) or fn)
            if fn.startswith("wbInteger"):
                it_type = next((x["id"] for x in a if "id" in x and x["id"] in INT_SIZE), None)
                out.append((nm, it_type or "int", INT_SIZE.get(it_type), False))
            elif fn.startswith("wbFloat"):
                out.append((nm, "float", 4, False))
            elif fn.startswith("wbFormID"):
                out.append((nm, "formid", 4, True))
            elif fn in ("wbUnused", "wbByteArray", "wbUnknown"):
                n = next((int(x["num"]) for x in a if "num" in x), None)
                out.append((nm if fn != "wbUnused" else prefix + "unused", "bytes", n, False))
            elif fn.startswith("wbString"):
                n = next((int(x["num"]) for x in a if "num" in x), 0)
                out.append((nm, "string", n or None, False))
            elif fn.startswith("wbStruct"):
                lst = next((x for x in a if "list" in x), {"list": []})
                out += self.fields(lst["list"], nm + ".")
            elif fn.startswith("wbUnion"):
                lst = next((x for x in a if "list" in x), {"list": []})
                alts = [self.fields([x]) for x in lst["list"]]
                sizes = {sum(f[2] or 0 for f in alt) if all(f[2] for f in alt) else None for alt in alts}
                formid = any(f[3] for alt in alts for f in alt)
                out.append((nm, "union", sizes.pop() if len(sizes) == 1 else None, formid))
            elif fn.startswith("wbArray"):
                out.append((nm, "array", None, any(f[3] for f in self.fields([x for x in a if "fn" in x]))))
            elif fn:
                out.append((nm, fn, None, False))
            elif "id" in it:     # defined outside this file: size unknown, so later offsets are too
                out.append((prefix + it["id"], "unresolved:" + it["id"], None, False))
        return out

    def members(self, node, group="", repeating=False):
        node = self.resolve(node)
        if "list" in node:
            return [m for x in node["list"] for m in self.members(x, group, repeating)]
        fn = node.get("fn", "")
        a = node.get("args", [])
        meths = {m[0] for m in node.get("methods", [])}
        if not fn:
            return []
        first = self.resolve(a[0]) if a else {}
        if fn.startswith(("wbRArray", "wbRStruct", "wbRUnion")):
            g = _name(a) or group
            out = []
            for x in a:
                rx = self.resolve(x)
                if "list" in rx or "fn" in rx:
                    out += self.members(rx, g, repeating or fn.startswith("wbRArray"))
            return out
        if "id" in a[0] if a else False:
            sig = a[0]["id"]
            if SIG.match(sig):
                kind = ("formid" if fn.startswith("wbFormID") else "string" if fn.startswith(("wbString", "wbLString"))
                        else "struct" if fn.startswith("wbStruct") else "int" if fn.startswith("wbInteger")
                        else "float" if fn.startswith("wbFloat") else "array" if fn.startswith("wbArray")
                        else "union" if fn.startswith("wbUnion") else "bytes" if fn.startswith(("wbByteArray", "wbUnknown"))
                        else "empty" if fn.startswith("wbEmpty") else fn)
                required = "SetRequired" in meths or any(x.get("id") == "True" for x in a[2:])
                targets = [s for x in a for s in _sigs(x)] if kind == "formid" else []
                flds = []
                if kind in ("struct",):
                    lst = next((x for x in a if "list" in x), {"list": []})
                    flds = self.fields(lst["list"])
                elif kind in ("array", "union"):
                    flds = self.fields([x for x in a[1:] if "fn" in x or "id" in x])
                elif kind in ("int", "float", "formid"):
                    flds = self.fields([{"fn": fn, "args": a[1:], "methods": []}])
                    if kind == "formid":
                        flds = [(_name(a) or sig, "formid", 4, True)]
                fid = kind == "formid" or any(f[3] for f in flds)
                return [{"sig": sig, "name": _name(a), "kind": kind, "required": required,
                         "repeating": repeating or fn.startswith("wbArray") and False, "group": group,
                         "formid": fid, "formid_targets": targets, "fields": flds}]
        # helper call (e.g. a model/texture helper): list every signature it mentions
        out = []
        for x in a:
            rx = self.resolve(x)
            for s in _sigs(rx):
                out.append({"sig": s, "name": _name(a), "kind": "helper:" + fn, "required": False,
                            "repeating": repeating, "group": group, "formid": False, "formid_targets": [],
                            "fields": []})
            if "fn" in rx and rx is not x:
                out += self.members(rx, group, repeating)
        return out


def extract(pas_file: Path) -> list[dict]:
    src = Path(pas_file).read_text("utf-8", "replace")
    vars_, recs = parse_defs(src)
    ip = Interp(vars_)
    out = []
    for r in recs:
        a = r["args"]
        sig = a[0].get("id", "")
        lst = [x for x in a if "list" in x]
        members = ip.members(lst[-1]) if lst else []
        subs = []
        for i, m in enumerate(members):
            off, layout = 0, []
            for name, typ, size, fid in m["fields"]:
                layout.append({"name": name, "type": typ, "offset": off, "size": size, "formid": fid})
                off = None if off is None or size is None else off + size
            m = dict(m, order=i, fields=layout)
            subs.append(m)
        out.append({"sig": sig, "name": _name(a), "subrecords": subs, "source": URL, "license": LICENSE})
    return out


def condition_functions(pas_file: Path) -> list[dict]:
    src = Path(pas_file).read_text("utf-8", "replace")
    out = []
    for m in re.finditer(r"\(Index:\s*(\d+);\s*Name:\s*'([^']+)'(?:;\s*ParamType1:\s*(\w+))?(?:;\s*ParamType2:\s*(\w+))?", src):
        params = [p[2:] for p in (m.group(3), m.group(4)) if p]
        out.append({"index": int(m.group(1)), "name": m.group(2), "param_types": params, "source": URL})
    return out
