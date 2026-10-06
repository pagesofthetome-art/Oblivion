"""Extract TES4 record layouts from xEdit's wbDefinitionsTES4.pas (MPL-2.0).

Output per record: its subrecords in order, with kind, required/repeating flags, FormID
targets and, for fixed structs, the field layout (name, type, offset, size). Only structure
facts are exported; xEdit's code is not copied.
"""

from __future__ import annotations

import re
from pathlib import Path

URL = "https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.6/Core/wbDefinitionsTES4.pas"
COMMON_URL = "https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.6/Core/wbDefinitionsCommon.pas"
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
            vars_[v.lower()] = p.expr()          # Pascal names are case-insensitive
            continue
        if k == "id" and v in ("wbRecord", "wbRefRecord") and p.peek(1)[1] == "(":
            records.append(p.expr())
            continue
        p.take()
    return vars_, records


def parse_functions(src: str) -> dict[str, list[dict]]:
    """`function wbX(params): T; begin Result := <expr>; end;` -> {name: [overloads]}.

    Only the implementation part, and only functions whose body assigns Result directly.
    Each overload: {"params": [(name, type, default node|None)], "body": node}.
    """
    impl = src[src.index("implementation"):]
    toks = tokenize(impl)
    out: dict[str, list[dict]] = {}
    i = 0
    while i < len(toks):
        if toks[i] == ("id", "function") and i + 1 < len(toks) and toks[i + 1][0] == "id":
            name = toks[i + 1][1]
            j = i + 2
            params = []
            if j < len(toks) and toks[j][1] == "(":
                depth, k = 1, j + 1
                while k < len(toks) and depth:
                    depth += {"(": 1, ")": -1}.get(toks[k][1], 0)
                    k += 1
                params = _parse_params(toks[j + 1:k - 1])
                j = k
            # find "begin" ... "Result :=" before the matching "end"
            k = j
            while k < len(toks) and toks[k] != ("id", "begin") and toks[k] != ("id", "function"):
                k += 1
            if k < len(toks) and toks[k] == ("id", "begin") and k + 3 < len(toks) and \
                    toks[k + 1] == ("id", "Result") and toks[k + 2][1] == ":=":
                pp = Parser(toks[k + 3:])
                out.setdefault(name.lower(), []).append({"params": params, "body": pp.expr()})
            i = k
            continue
        i += 1
    return out


def _parse_params(toks) -> list:
    groups, cur, depth = [], [], 0
    for t in toks:
        if t[1] in "([":
            depth += 1
        elif t[1] in ")]":
            depth -= 1
        if t[1] == ";" and depth == 0:
            groups.append(cur); cur = []
        else:
            cur.append(t)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        g = [t for t in g if t[1] not in ("const", "var", "out")]
        if ":" not in [t[1] for t in g]:
            continue
        c = [t[1] for t in g].index(":")
        names = [t[1] for t in g[:c] if t[0] == "id"]
        rest = g[c + 1:]
        typ = rest[0][1] if rest else ""
        default = None
        if "=" in [t[1] for t in rest]:
            e = [t[1] for t in rest].index("=")
            default = Parser(rest[e + 1:]).expr()
        for n in names:
            out.append((n, typ, default))
    return out


def _subst(node, env):
    """Replace parameter identifiers with the call's arguments (deep copy)."""
    if isinstance(node, list):
        return [_subst(x, env) for x in node]
    if not isinstance(node, dict):
        return node
    if "id" in node and node["id"].lower() in env:
        r = dict(env[node["id"].lower()])
        r["methods"] = list(r.get("methods", [])) + list(node.get("methods", []))
        return r
    out = {}
    for k, v in node.items():
        if k == "methods":
            out[k] = [(m, _subst(a, env)) for m, a in v]
        else:
            out[k] = _subst(v, env)
    return out


def _name(args):
    for a in args:
        if "str" in a:
            return a["str"]
    return ""


def _sigs(node):
    return [x["id"] for x in node.get("list", []) if "id" in x and SIG.match(x["id"])]


PRIMITIVES = ("wbStruct", "wbInteger", "wbFloat", "wbFormID", "wbString", "wbLString", "wbArray", "wbRArray",
              "wbRStruct", "wbRUnion", "wbUnion", "wbByteArray", "wbUnknown", "wbUnused", "wbEmpty", "wbEnum",
              "wbFlags", "wbRecord", "wbRefRecord")


class Interp:
    def __init__(self, vars_, funcs=None):
        self.vars = vars_
        self.funcs = funcs or {}

    def expand(self, node):
        """A call to a helper function (e.g. wbVec3PosRot(DATA)) -> its Result expression."""
        fn = node.get("fn", "")
        if not fn or fn.startswith(PRIMITIVES) or fn in ("IfThen", "IsTES4") or fn.lower() not in self.funcs:
            return node                     # IfThen is decided by if_then(), not expanded
        args = node.get("args", [])
        first_sig = bool(args) and "id" in args[0] and SIG.match(args[0]["id"])
        cands = [o for o in self.funcs[fn.lower()] if len(args) <= len(o["params"])
                 and all(p[2] is not None for p in o["params"][len(args):])]
        if first_sig:
            cands = [o for o in cands if o["params"] and o["params"][0][1] == "TwbSignature"] or cands
        else:
            cands = [o for o in cands if not o["params"] or o["params"][0][1] != "TwbSignature"] or cands
        if not cands:
            return node
        o = cands[0]
        env = {}
        for i, (pname, _t, default) in enumerate(o["params"]):
            env[pname.lower()] = args[i] if i < len(args) else default
        body = _subst(o["body"], env)
        if isinstance(body, dict):
            body["methods"] = list(body.get("methods", [])) + list(node.get("methods", []))
        return body

    def resolve(self, node, depth=0):
        while depth < 20:
            if "id" in node and node["id"].lower() in self.vars:
                m = node.get("methods", [])
                node = dict(self.vars[node["id"].lower()])
                node["methods"] = list(node.get("methods", [])) + m
            elif "id" in node and node["id"].lower() in self.funcs:
                # a bare helper name is a zero-argument call (wbNextSpeaker, wbLandHeights)
                new = self.expand({"fn": node["id"], "args": [], "methods": node.get("methods", [])})
                if new.get("fn") == node["id"]:
                    break
                node = new
            elif "fn" in node:
                new = self.expand(node)
                if new is node:
                    break
                node = new
            else:
                break
            depth += 1
        return node

    def names(self, args) -> dict | None:
        """Enum / flag / char4 info of an integer field: {"enum": [...]} | {"flags": [...]} | {"char4": True}."""
        for x in args:
            x = self.resolve(x)
            fn = x.get("fn", "")
            if fn == "wbEnum" or fn == "wbFlags":
                lists = [y for y in x.get("args", []) if "list" in y]
                if not lists:
                    continue
                items = lists[0]["list"]
                if not items and len(lists) > 1:          # wbEnum([], [index, 'name', ...]) sparse form
                    pairs = lists[1]["list"]
                    sparse = {}
                    for i in range(0, len(pairs) - 1, 2):
                        if "num" in pairs[i] and "str" in pairs[i + 1]:
                            sparse[str(int(pairs[i]["num"]))] = pairs[i + 1]["str"]
                    return {"enum_sparse": sparse} if sparse else None
                vals = [y.get("str", "") for y in items]
                return {"enum" if fn == "wbEnum" else "flags": vals}
            if x.get("id") == "wbChar4":
                return {"char4": True}
        return None

    def pick_game(self, node):
        """xEdit's per-game selector IsTES4(<Oblivion value>, <other games>) -> the Oblivion value."""
        if node.get("fn") == "IsTES4" and node.get("args"):
            return self.resolve(node["args"][0]) if "fn" in node["args"][0] or "id" in node["args"][0] \
                else node["args"][0]
        return node

    def if_then(self, node):
        """Delphi IfThen(cond, a, b): Assigned(<bound arg>) -> a; wbSimpleRecords -> b; else a."""
        a = node.get("args", [])
        if len(a) < 2:
            return node
        cond = self.resolve(a[0]) if "id" in a[0] else a[0]
        if cond.get("fn") == "Assigned":
            arg = (cond.get("args") or [{}])[0]
            take_then = not (arg.get("id", "").lower() == "nil")
        elif a[0].get("id", "").lower() == "wbsimplerecords":
            take_then = False
        else:
            take_then = True
        pick = a[1] if take_then else (a[2] if len(a) > 2 else {"id": "nil"})
        return self.resolve(pick) if isinstance(pick, dict) else pick

    def fields(self, items, prefix=""):
        """Flatten struct members to (name, type, size|None, formid[, extra])."""
        out = []
        for it in items:
            it = self.resolve(it)
            it = self.pick_game(it)
            if it.get("fn") == "IfThen":
                it = self.if_then(it)
            if it.get("id", "").lower() == "nil":
                continue
            fn = it.get("fn", "")
            a = it.get("args", [])
            nm = prefix + (_name(a) or fn)
            if fn.startswith("wbInteger"):
                it_type = next((x["id"] for x in a if "id" in x and x["id"] in INT_SIZE), None)
                out.append((nm, it_type or "int", INT_SIZE.get(it_type), False, self.names(a)))
            elif fn.startswith("wbFloat"):
                out.append((nm, "float", 4, False))
            elif fn.startswith("wbFormID"):
                out.append((nm, "formid", 4, True))
            elif fn in ("wbUnused", "wbByteArray", "wbUnknown"):
                # no size given = the rest of the subrecord (size 0, valid only as the last field)
                n = next((int(x["num"]) for x in a if "num" in x), 0)
                out.append((nm if fn != "wbUnused" else prefix + "unused", "bytes", n, False))
            elif fn.startswith("wbString"):
                n = next((int(x["num"]) for x in a if "num" in x), 0)
                out.append((nm, "string", n or None, False))
            elif fn.startswith("wbStruct"):
                ra = [self.resolve(x) if "id" in x else x for x in a]
                lsts = [x for x in ra if "list" in x and any("fn" in y or "id" in y for y in x["list"])]
                out += self.fields(lsts[-1]["list"] if lsts else [], nm + ".")
            elif fn.startswith("wbUnion"):
                lst = next((x for x in a if "list" in x), {"list": []})
                alts = [self.fields([x]) for x in lst["list"]]
                # alternatives that resolve all share one size in TES4; unresolved ones don't veto it.
                # An empty wbUnused() alternative counts as size 0 (XLOC filler: 0 or 4 bytes).
                sizes = {sum(f[2] for f in alt) for alt in alts
                         if alt and all(f[2] is not None for f in alt)}
                formid = any(f[3] for alt in alts for f in alt)
                if len(sizes) == 1:
                    out.append((nm, "union", sizes.pop() or None, formid))
                elif sizes:
                    out.append((nm, "union", None, formid, {"alt_sizes": sorted(sizes)}))
                else:
                    out.append((nm, "union", None, formid))
            elif fn.startswith("wbArray"):
                el = self.fields([x for x in a if "fn" in x or ("id" in x and x["id"].lower() in self.vars)])
                count = next((int(x["num"]) for x in a if "num" in x), None)
                el_size = sum(f[2] for f in el) if el and all(f[2] for f in el) else None
                formid = any(f[3] for f in el)
                if count and el_size:
                    # fixed-count array inside a struct (e.g. LAND VHGT 'Height Data'): opaque bytes
                    out.append((nm, "bytes", count * el_size, formid))
                else:
                    out.append((nm, "array", None, formid))
            elif fn:
                out.append((nm, fn, None, False))
            elif it.get("id", "").lower() == "nil":
                continue
            elif "id" in it:     # defined outside this file: size unknown, so later offsets are too
                out.append((prefix + it["id"], "unresolved:" + it["id"], None, False))
        return out

    def members(self, node, group="", repeating=False):
        node = self.pick_game(self.resolve(node))
        if node.get("id", "").lower() == "nil":
            return []
        if node.get("fn") == "IfThen":
            node = self.if_then(node)
            if node.get("id", "").lower() == "nil":
                return []
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
                    # the member list is the last list argument holding calls; wbStructSK puts a
                    # list of sort-key indexes ([4, 5]) before it
                    ra = [self.resolve(x) if "id" in x else x for x in a]
                    lsts = [x for x in ra if "list" in x and any("fn" in y or "id" in y for y in x["list"])]
                    flds = self.fields(lsts[-1]["list"] if lsts else [])
                elif kind in ("array", "union"):
                    flds = self.fields([x for x in a[1:] if "fn" in x or "id" in x])
                elif kind in ("int", "float", "formid"):
                    flds = self.fields([{"fn": fn, "args": a[1:], "methods": []}])
                    if kind == "formid":
                        flds = [(_name(a) or sig, "formid", 4, True)]
                fid = kind == "formid" or any(f[3] for f in flds)
                opt = next((int(m[1][0]["num"]) for m in node.get("methods", [])
                            if m[0] == "SetOptionalFrom" and m[1] and "num" in m[1][0]), None)
                return [{"sig": sig, "name": _name(a), "kind": kind, "required": required, "optional_from": opt,
                         "repeating": repeating or fn.startswith("wbArray") and False, "group": group,
                         "formid": fid, "formid_targets": targets, "fields": flds}]
        if fn == "wbTexturedModel":
            # procedural in wbDefinitionsCommon.pas; its Oblivion branch is:
            # [0] wbString 'Model Filename', [1] wbFloat 'Bound Radius', [2] wbModelInfo (texture hashes)
            sigs = [x for a_ in a for x in _sigs(self.resolve(a_))]
            kinds = [("string", "Model Filename", []), ("float", "Bound Radius", [("Bound Radius", "float", 4, False)]),
                     ("bytes", "Model Info", [])]
            return [{"sig": sg, "name": nm, "kind": k, "required": False, "repeating": repeating, "group": group,
                     "formid": False, "formid_targets": [], "fields": fl}
                    for sg, (k, nm, fl) in zip(sigs, kinds)]
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


def extract(pas_file: Path, common_file: Path | None = None) -> list[dict]:
    src = Path(pas_file).read_text("utf-8", "replace")
    vars_, recs = parse_defs(src)
    funcs = parse_functions(src)
    if common_file and Path(common_file).is_file():
        for k, v in parse_functions(Path(common_file).read_text("utf-8", "replace")).items():
            funcs.setdefault(k, v)
    ip = Interp(vars_, funcs)
    out = []
    for r in recs:
        a = r["args"]
        sig = a[0].get("id", "")
        lst = [x for x in a if "list" in x]
        members = ip.members(lst[-1]) if lst else []
        subs = []
        for i, m in enumerate(members):
            off, layout = 0, []
            for f in m["fields"]:
                name, typ, size, fid = f[:4]
                entry = {"name": name, "type": typ, "offset": off, "size": size, "formid": fid}
                if len(f) > 4 and f[4]:
                    entry.update(f[4])
                layout.append(entry)
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
