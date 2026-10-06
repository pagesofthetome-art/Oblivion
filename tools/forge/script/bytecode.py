"""SCDA decompiler: compiled Oblivion script bytecode -> a readable statement listing.

Step S1 of docs/forge-script-compiler-plan.md. Survey of the vanilla corpus (Oblivion.esm + 9 DLC,
10,720 scripts with bytecode, 2026-10-06): **100% decode with no leftover bytes**, every jump field
matches one meaning, and every decoded command name appears in its script's source text.

Format (CONFIRMED by that survey unless marked otherwise):
  statement      u16 opcode, u16 length, <length bytes>
  0x1D ScriptName, 0x11 End, 0x19 EndIf, 0x1E Return: length 0. Result scripts (QUST/INFO) have
                 no ScriptName and no Begin/End.
  0x10 Begin     u16 block type, u32 bytes from after this statement through the matching End,
                 [block parameters]. Block types = the exe's block CommandInfo table, opcode = code.
  0x15 Set       variable, u16 expression length, expression
  0x16 If / 0x18 ElseIf   u16 jump, u16 expression length, expression
  0x17 Else      u16 jump
                 jump = number of statements between this one and the next Else/ElseIf/EndIf of
                 the same level
  0x1C           u16 reference index, then a command statement called on that reference
  command        u16 opcode (>= 0x100), u16 length, [u16 parameter count, parameters]
  parameters     by ParamType: string = u16 length + text; number = 'n' i32 | 'z' f64 |
                 variable; form = 'r' + u16 reference index; actor value / animation group /
                 sex / crime type = u16 code; axis = one char. FormType (0x21) and VariableName
                 (0x16) never occur in vanilla: their layout here is a HYPOTHESIS.
  formatted text Message / MessageBox / EssentialDeathReload: u16 1, u16 length + text,
                 u16 variable count + variables, then Message: u16 seconds, u16 0;
                 the others: u16 button count + buttons (u16 1, u16 length + text)
  variables      's'/'l'/'f' + u16 local index; 'r' + u16 ref index + local of that script;
                 'G' + u16 ref index of a global
  expressions    **postfix** (RPN), tokens separated by spaces: numbers as ASCII text, operators
                 as text (== != > < >= <= && || + - * /, ~ = unary minus), variables as above,
                 'Z' + u16 ref index = a reference used as a value, 'X' + u16 opcode + u16 length +
                 parameters = a function call, 'r' + u16 ref + 'X'... = a call on a reference
  SCHR           variable count is a high-water mark: >= the highest SLSD index (gaps and stale
                 counts after deleted variables); ref count = SCRO + SCRV; size = len(SCDA)
"""

from __future__ import annotations

import re
import struct
from collections import Counter
from dataclasses import dataclass, field

from forge.script import commands as cmds

STATEMENTS = {0x10: "Begin", 0x11: "End", 0x12: "Short", 0x13: "Long", 0x14: "Float", 0x15: "Set",
              0x16: "If", 0x17: "Else", 0x18: "ElseIf", 0x19: "EndIf", 0x1C: "RefCall",
              0x1D: "ScriptName", 0x1E: "Return"}
EMPTY_STATEMENTS = {0x11, 0x19, 0x1D, 0x1E}
OPERATORS = ["==", "!=", ">=", "<=", "&&", "||", ">", "<", "+", "-", "*", "/", "(", ")", "~"]   # ~ = unary minus
FORMATTED = {"message", "messagebox", "essentialdeathreload"}   # format text + variables (custom parse)
PLAYER_REF = ("oblivion.esm", 0x14)          # the player reference has no EditorID
LOCAL_TAGS = b"slf"


class DecodeError(Exception):
    def __init__(self, off: int, kind: str, detail: str = ""):
        super().__init__(f"{kind} at {off:04X}" + (f": {detail}" if detail else ""))
        self.off, self.kind, self.detail = off, kind, detail


@dataclass
class Stmt:
    off: int
    op: int
    name: str
    size: int                      # total bytes including the 4-byte header
    text: str = ""
    jump: int | None = None        # If/ElseIf/Else jump, Begin block length
    block: int | None = None       # Begin block type
    tokens: list = field(default_factory=list)   # expression tokens (kind, value, offset)


@dataclass
class Issue:
    off: int
    kind: str
    detail: str = ""


@dataclass
class Decoded:
    stmts: list[Stmt]
    issues: list[Issue]
    jumps: Counter                 # "If:stmts", "Else:bytes_after", "Begin:bytes_to_end", ...
    commands: list = field(default_factory=list)       # every Command called, in order
    param_types: Counter = field(default_factory=Counter)   # ParamType id -> times decoded

    @property
    def ok(self) -> bool:
        return not self.issues


class Reader:
    def __init__(self, data: bytes, base: int = 0):
        self.b, self.pos, self.base = data, 0, base

    @property
    def off(self) -> int:
        return self.base + self.pos

    def left(self) -> int:
        return len(self.b) - self.pos

    def take(self, n: int, what: str) -> bytes:
        if self.pos + n > len(self.b):
            raise DecodeError(self.off, "truncated", f"{what} needs {n} bytes, {self.left()} left")
        v = self.b[self.pos:self.pos + n]
        self.pos += n
        return v

    def u8(self, what="byte") -> int:
        return self.take(1, what)[0]

    def u16(self, what="u16") -> int:
        return struct.unpack("<H", self.take(2, what))[0]

    def u32(self, what="u32") -> int:
        return struct.unpack("<I", self.take(4, what))[0]

    def peek(self) -> int | None:
        return self.b[self.pos] if self.pos < len(self.b) else None

    def sub(self, n: int, what: str) -> "Reader":
        off = self.off
        return Reader(self.take(n, what), off)


class Decompiler:
    def __init__(self, table: cmds.CommandTable, variables: list[dict] | None = None,
                 refs: list[dict] | None = None, external=None):
        """`external(ref_entry)` -> {index: name} for the script behind a reference (quest or
        placed object), so `Quest.s3` reads as `Quest.varName`. Optional."""
        self.t = table
        self.external = external
        self.vars = {v["index"]: v.get("name") or f"var{v['index']}" for v in variables or [] if v.get("index")}
        self.refs = refs or []
        self.issues: list[Issue] = []

    # ---------------------------------------------------------------- names
    def local(self, idx: int, tag: int, off: int) -> str:
        if idx not in self.vars:
            if self.vars:
                self.issues.append(Issue(off, "unknown local", f"{chr(tag)}{idx}"))
            return f"{chr(tag)}{idx}"
        return self.vars[idx]

    def ref(self, idx: int, off: int) -> str:
        if not 1 <= idx <= len(self.refs):
            if self.refs or idx:
                self.issues.append(Issue(off, "ref index out of range", f"{idx} of {len(self.refs)}"))
            return f"ref{idx}"
        r = self.refs[idx - 1]
        if r["kind"] == "SCRV":
            return self.vars.get(r["var"], f"var{r['var']}")
        if not r.get("edid") and (r.get("owner", "").casefold(), int(r.get("objid") or "0", 16)) == PLAYER_REF:
            return "player"
        return r.get("edid") or f"{r.get('owner', '')}:{r.get('formid', '')}"

    def ext_local(self, ref_idx: int, tag: int, idx: int) -> str:
        names = None
        if self.external and 1 <= ref_idx <= len(self.refs):
            names = self.external(self.refs[ref_idx - 1])
        return (names or {}).get(idx) or f"{chr(tag)}{idx}"

    # ---------------------------------------------------------------- operands
    def variable(self, r: Reader) -> str:
        off, tag = r.off, r.u8("variable tag")
        if tag in LOCAL_TAGS:
            return self.local(r.u16("local index"), tag, off)
        if tag == ord("G"):
            return self.ref(r.u16("global index"), off)
        if tag == ord("r"):
            ri = r.u16("ref index")
            base = self.ref(ri, off)
            off2, tag2 = r.off, r.u8("external variable tag")
            if tag2 in LOCAL_TAGS:
                return f"{base}.{self.ext_local(ri, tag2, r.u16('external local index'))}"
            raise DecodeError(off2, "bad external variable tag", f"{tag2:#04x}")
        raise DecodeError(off, "bad variable tag", f"{tag:#04x}")

    def number(self, r: Reader) -> str:
        off, tag = r.off, r.peek()
        if tag == ord("n"):
            r.u8()
            return str(struct.unpack("<i", r.take(4, "int literal"))[0])
        if tag == ord("z"):
            r.u8()
            return repr(struct.unpack("<d", r.take(8, "double literal"))[0])
        if tag is not None and tag in b"slfGr":
            return self.variable(r)
        raise DecodeError(off, "bad number parameter", f"tag {tag if tag is None else hex(tag)}")

    def param(self, r: Reader, p: cmds.Param) -> str:
        t, off = p.type_id, r.off
        self.param_types[t] += 1
        if t == cmds.STRING:
            n = r.u16("string length")
            return '"' + r.take(n, "string").decode("latin-1") + '"'
        if t in (cmds.INTEGER, cmds.FLOAT, cmds.QUEST_STAGE):
            return self.number(r)
        if t in cmds.CODE16_PARAMS:
            return f"{p.name or t}#{r.u16('code')}"
        if t == cmds.AXIS:
            return chr(r.u8("axis"))
        if t == cmds.FORM_TYPE:                      # HYPOTHESIS: u16 like the other codes
            return f"formtype#{r.u16('form type')}"
        if t == cmds.VARIABLE_NAME:                  # HYPOTHESIS: counted string
            n = r.u16("variable name length")
            return r.take(n, "variable name").decode("latin-1")
        if t in cmds.FORM_PARAMS:
            tag = r.peek()
            if tag == ord("r"):
                r.u8()
                return self.ref(r.u16("form ref index"), off)
            if tag is not None and tag in LOCAL_TAGS:
                return self.variable(r)
            raise DecodeError(off, "bad form parameter", f"tag {tag if tag is None else hex(tag)}")
        raise DecodeError(off, "unknown param type", f"{t:#04x} ({p.name})")

    def params(self, r: Reader, cmd: cmds.Command | None, opcode: int) -> str:
        if not r.left():
            return ""
        if cmd is None:
            raw = r.take(r.left(), "params")
            self.issues.append(Issue(r.off - len(raw), "unknown opcode", f"{opcode:#06x}"))
            return "<" + raw.hex() + ">"
        if cmd.name.casefold() in FORMATTED:
            return self.formatted(r, cmd)
        off, n = r.off, r.u16("param count")
        if n > len(cmd.params):
            raise DecodeError(off, "too many params", f"{cmd.name}: {n} > {len(cmd.params)}")
        out = [self.param(r, cmd.params[i]) for i in range(n)]
        if r.left():
            raise DecodeError(r.off, "leftover param bytes", f"{cmd.name}: {r.left()}")
        return " ".join(out)

    def formatted(self, r: Reader, cmd: cmds.Command) -> str:
        """Commands whose text takes format variables (corpus-confirmed):
        u16 1, u16 length + text, u16 variable count + variables, then
          Message:                 u16 display seconds, u16 0
          MessageBox and others:   u16 button count + buttons (u16 1, u16 length + text)"""
        off, n = r.off, r.u16("param count")
        if n != 1:
            raise DecodeError(off, "formatted text param count", f"{cmd.name}: {n}")
        out = ['"' + r.take(r.u16("text length"), "text").decode("latin-1") + '"']
        out += [self.variable(r) for _ in range(r.u16("format variable count"))]
        if cmd.name.casefold() == "message":
            secs, toff, tail = r.u16("display seconds"), r.off, r.u16("message tail")
            if secs:
                out.append(str(secs))
            if tail:
                raise DecodeError(toff, "message tail", str(tail))
        else:
            for _ in range(r.u16("button count")):
                boff, one = r.off, r.u16("button tag")
                if one != 1:
                    raise DecodeError(boff, "button tag", f"{one}")
                out.append('"' + r.take(r.u16("button length"), "button").decode("latin-1") + '"')
        if r.left():
            raise DecodeError(r.off, "leftover param bytes", f"{cmd.name}: {r.left()}")
        return ", ".join(out)

    def call(self, r: Reader, opcode: int, length: int) -> str:
        cmd = self.t.by_op.get(opcode)
        if cmd:
            self.commands.append(cmd)
        body = r.sub(length, "command params")
        args = self.params(body, cmd, opcode)
        name = cmd.name if cmd else f"op{opcode:04X}"
        return f"{name} {args}".rstrip()

    # ---------------------------------------------------------------- expressions
    def expression(self, r: Reader) -> tuple[str, list]:
        toks, out = [], []
        while r.left():
            off, c = r.off, r.peek()
            if c == 0x20:
                r.u8()
                toks.append(("space", " ", off))
                continue
            ch = chr(c)
            if ch.isdigit() or ch == ".":
                s = bytearray()
                while r.left() and (chr(r.peek()).isdigit() or r.peek() in b".eE" or
                                    (r.peek() in b"+-" and s[-1:] in (b"e", b"E"))):
                    s.append(r.u8())
                v = s.decode()
                toks.append(("num", v, off)); out.append(v)
                continue
            if c in b"slfGr":
                if c == ord("r"):
                    # a reference followed by a function call or a variable of its script
                    r.u8()
                    ri = r.u16("ref index")
                    base = self.ref(ri, off)
                    nxt = r.peek()
                    if nxt == ord("X"):
                        r.u8()
                        opcode, length = r.u16("opcode"), r.u16("call length")
                        v = f"{base}.{self.call(r, opcode, length)}"
                        toks.append(("refcall", v, off)); out.append(v)
                        continue
                    if nxt is not None and nxt in LOCAL_TAGS:
                        tag = r.u8()
                        v = f"{base}.{self.ext_local(ri, tag, r.u16('external local index'))}"
                        toks.append(("extvar", v, off)); out.append(v)
                        continue
                    raise DecodeError(r.off, "bad token after reference", f"{nxt if nxt is None else hex(nxt)}")
                v = self.variable(r)
                toks.append(("var", v, off)); out.append(v)
                continue
            if c == ord("Z"):                     # a reference used as a value
                r.u8()
                v = self.ref(r.u16("ref index"), off)
                toks.append(("refval", v, off)); out.append(v)
                continue
            if c == ord("X"):
                r.u8()
                opcode, length = r.u16("opcode"), r.u16("call length")
                v = self.call(r, opcode, length)
                toks.append(("call", v, off)); out.append(v)
                continue
            for op in OPERATORS:
                if r.b[r.pos:r.pos + len(op)] == op.encode():
                    r.take(len(op), "operator")
                    toks.append(("op", op, off)); out.append(op)
                    break
            else:
                raise DecodeError(off, "bad expression byte", f"{c:#04x} {chr(c)!r}")
        return " ".join(out), toks

    # ---------------------------------------------------------------- statements
    def statement(self, r: Reader) -> Stmt:
        start, op = r.off, r.u16("opcode")
        if op == 0x1C:
            ref = self.ref(r.u16("calling ref"), start + 2)
            opcode, length = r.u16("opcode"), r.u16("length")
            text = f"{ref}.{self.call(r, opcode, length)}"
            return Stmt(start, op, "RefCall", r.off - start, text)
        length = r.u16("length")
        body = r.sub(length, f"{STATEMENTS.get(op, 'command')} body")
        name = STATEMENTS.get(op)
        if op in EMPTY_STATEMENTS:
            if length:
                raise DecodeError(start, "unexpected length", f"{name} has {length}")
            return Stmt(start, op, name, 4 + length, name)
        if op == 0x10:
            code, blen = body.u16("block type"), body.u32("block length")
            blk = self.t.blocks.get(code)
            args = self.params(body, blk, code) if blk else ("<" + body.take(body.left(), "").hex() + ">"
                                                            if body.left() else "")
            label = blk.name if blk else f"block#{code}"
            return Stmt(start, op, name, 4 + length, f"Begin {label} {args}".rstrip(), jump=blen, block=code)
        if op == 0x15:
            var = self.variable(body)
            n = body.u16("expression length")
            text, toks = self.expression(body.sub(n, "expression"))
            if body.left():
                raise DecodeError(body.off, "leftover set bytes", str(body.left()))
            return Stmt(start, op, name, 4 + length, f"set {var} to {text}", tokens=toks)
        if op in (0x16, 0x18):
            jump, n = body.u16("jump"), body.u16("expression length")
            text, toks = self.expression(body.sub(n, "expression"))
            if body.left():
                raise DecodeError(body.off, "leftover if bytes", str(body.left()))
            return Stmt(start, op, name, 4 + length, f"{name.lower()} {text}", jump=jump, tokens=toks)
        if op == 0x17:
            jump = body.u16("jump")
            if body.left():
                raise DecodeError(body.off, "leftover else bytes", str(body.left()))
            return Stmt(start, op, name, 4 + length, "else", jump=jump)
        if op in STATEMENTS:
            raise DecodeError(start, "unexpected statement", name)
        cmd = self.t.by_op.get(op)
        if cmd:
            self.commands.append(cmd)
        args = self.params(body, cmd, op)
        return Stmt(start, op, cmd.name if cmd else f"op{op:04X}", 4 + length,
                    f"{cmd.name if cmd else f'op{op:04X}'} {args}".rstrip())

    def decode(self, data: bytes) -> Decoded:
        self.issues, self.commands, self.param_types = [], [], Counter()
        r, stmts = Reader(data), []
        while r.left():
            try:
                stmts.append(self.statement(r))
            except DecodeError as e:
                self.issues.append(Issue(e.off, e.kind, e.detail))
                break
        return Decoded(stmts, self.issues, measure_jumps(stmts) if not self.issues else Counter(),
                       self.commands, self.param_types)


# -------------------------------------------------------------------- jump semantics
def measure_jumps(stmts: list[Stmt]) -> Counter:
    """For every If/ElseIf/Else and Begin, record which candidate meaning its jump field matches."""
    c: Counter = Counter()
    stack: list[int] = []
    begin = None
    for i, s in enumerate(stmts):
        if s.op == 0x10:
            begin = i
        elif s.op == 0x11 and begin is not None:
            b, e = stmts[begin], s
            after = b.off + b.size
            cands = {"bytes_to_end": e.off - after, "bytes_through_end": e.off + e.size - after,
                     "stmts": i - begin}
            hit = [k for k, v in cands.items() if v == b.jump]
            c["Begin:" + ("|".join(hit) or "other")] += 1
            begin = None
        if s.op in (0x17, 0x18, 0x19) and stack:
            j = stack.pop()
            _jump_target(stmts, j, i, c)
        elif s.op in (0x17, 0x18, 0x19):
            c[f"structure:{s.name.lower()} without if"] += 1      # the CS tolerates sloppy nesting
        if s.op in (0x16, 0x17, 0x18):
            stack.append(i)
    if stack:
        c["structure:unclosed if"] += len(stack)
    return c


def _jump_target(stmts, j, i, c):
    s, t = stmts[j], stmts[i]
    cands = {"stmts": i - j, "stmts_between": i - j - 1, "bytes_after": t.off - (s.off + s.size),
             "bytes_from_start": t.off - s.off}
    hit = [k for k, v in cands.items() if v == s.jump]
    c[f"{s.name}:" + ("|".join(hit) or "other")] += 1


# -------------------------------------------------------------------- helpers for the survey
BEGIN_RE = re.compile(r"^\s*begin\s+([A-Za-z_]\w*)", re.I | re.M)


def source_blocks(sctx: str) -> list[str]:
    """Block names from the source text, in order, ignoring comments."""
    text = "\n".join(line.split(";", 1)[0] for line in sctx.splitlines())
    return [m.group(1) for m in BEGIN_RE.finditer(text)]


def listing(dec: Decoded) -> str:
    out, depth = [], 0
    for s in dec.stmts:
        if s.op in (0x11, 0x19, 0x17, 0x18):
            depth = max(0, depth - 1)
        extra = f"   [jump {s.jump}]" if s.jump is not None else ""
        out.append(f"{s.off:04X}  {'  ' * depth}{s.text}{extra}")
        if s.op in (0x10, 0x16, 0x17, 0x18):
            depth += 1
    for i in dec.issues:
        out.append(f"!! {i.kind} at {i.off:04X}" + (f": {i.detail}" if i.detail else ""))
    return "\n".join(out)


WORD_RE = re.compile(r"[A-Za-z_]\w*")


def source_agreement(sctx: str, dec: Decoded) -> list[str]:
    """Commands the bytecode calls whose name and alias never appear in the source text: a sign
    the decoder read an opcode at the wrong place. Comments are ignored."""
    text = "\n".join(line.split(";", 1)[0] for line in sctx.splitlines())
    words = {w.casefold() for w in WORD_RE.findall(text)}
    return sorted({c.name for c in dec.commands
                   if c.name.casefold() not in words and (not c.alias or c.alias.casefold() not in words)})


def check_header(row: dict, dec: Decoded) -> list[str]:
    """SCHR against what the subrecords hold. Returns mismatch tags (survey statistics)."""
    h, bad = row.get("schr") or {}, []
    if "size" not in h:
        return ["schr short"]
    if h["size"] != len(bytes.fromhex(row["scda"])):
        bad.append("size != len(SCDA)")
    if h["refs"] != len(row["refs"]):
        bad.append("refs != SCRO+SCRV")
    idx = [v["index"] for v in row["vars"] if v.get("index")]
    top = max(idx) if idx else 0
    if h["vars"] != len(idx):
        # the field is a high-water mark: deleted variables leave gaps and stale counts behind
        bad.append("vars == max index (gaps)" if h["vars"] == top else
                   "vars > max index (stale)" if h["vars"] > top else "vars < max index")
    return bad
