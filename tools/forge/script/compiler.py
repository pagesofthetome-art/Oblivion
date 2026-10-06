"""OBScript compiler: source text (SCTX) -> SCDA bytecode, reference list, variables, SCHR.

Steps S2-S4 of docs/forge-script-compiler-plan.md. The target format is the one the decompiler
(bytecode.py) proved on the whole vanilla corpus; `forge script-check` compiles every vanilla script
and compares bytes. Anything the corpus never exercised is a CompileError, never a guess.

Rules taken from the corpus (see plan section 3c):
  * statements, jumps, Begin lengths, formatted-text commands: as in bytecode.py
  * expressions are postfix, every token prefixed by one space
  * a command writes a u16 parameter count only when it defines parameters
  * reference list order: references used as a statement's calling reference (`X.Func`) first,
    in order of first such use; then reference variables (SCRV) by variable index; then every
    other reference in order of first use
  * variables get indices in declaration order unless the caller pins them (`fixed_vars`): the CS
    keeps old indices across edits, so vanilla scripts have gaps
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

from forge.script import commands as cmds

KEYWORDS = {"scn", "scriptname", "begin", "end", "short", "long", "float", "ref", "int",
            "set", "if", "elseif", "else", "endif", "return"}
VAR_KINDS = {"short": "s", "long": "s", "float": "f", "ref": "f", "int": "s"}   # vanilla never writes 'l'
# operator precedence (higher binds tighter); all binary operators are left-associative
PRECEDENCE = {"&&": 1, "||": 2,           # the CS binds || tighter than && (corpus)
               "==": 3, "!=": 3, ">": 4, "<": 4, ">=": 4, "<=": 4,
              "+": 5, "-": 5, "*": 6, "/": 6, "~": 7}
TOKEN_RE = re.compile(r'"[^"\r\n]*"?|==|!=|>=|<=|&&|\|\||[-+*/()<>!,]|[A-Za-z0-9_.:]+|\S')

ANIM_GROUPS = ["Idle", "DynamicIdle", "SpecialIdle", "Forward", "Backward", "Left", "Right", "FastForward",
               "FastBackward", "FastLeft", "FastRight", "DodgeForward", "DodgeBack", "DodgeLeft", "DodgeRight",
               "TurnLeft", "TurnRight", "Equip", "Unequip", "AttackBow", "AttackLeft", "AttackRight",
               "AttackPower", "AttackForwardPower", "AttackBackPower", "AttackLeftPower", "AttackRightPower",
               "BlockIdle", "BlockHit", "BlockAttack", "Recoil", "Stagger", "Death", "TorchIdle", "CastSelf",
               "CastTouch", "CastTarget", "CastSelfAlt", "CastTouchAlt", "CastTargetAlt", "JumpStart",
               "JumpLoop", "JumpLand"]          # codes 0x00-0x2A (xOBSE CommandTable.h)
SEXES = ["Male", "Female"]
CRIME_TYPES = ["Steal", "Pickpocket", "Trespass", "Attack", "Murder"]   # HYPOTHESIS, checked by the corpus


class CompileError(Exception):
    def __init__(self, line: int, msg: str):
        super().__init__(f"line {line}: {msg}")
        self.line, self.msg = line, msg


@dataclass
class Var:
    index: int
    name: str
    kind: str          # short / long / float / ref

    @property
    def tag(self) -> bytes:
        return VAR_KINDS[self.kind].encode()

    @property
    def is_int(self) -> bool:
        return self.kind in ("short", "long", "int")


@dataclass
class Compiled:
    scda: bytes
    refs: list[dict]               # {"kind": "SCRO", "form": {...}} | {"kind": "SCRV", "var": index}
    vars: list[Var]
    schr: dict
    name: str = ""


class Resolver:
    """Name lookups the compiler needs. Override for real data (see script_check.CorpusResolver)."""

    def form(self, name: str) -> dict | None:            # EditorID -> {"owner","objid","sig",...}
        return None

    def script_vars(self, form: dict) -> dict[str, Var] | None:   # variables of the form's script
        return None


@dataclass
class _Ref:
    key: tuple
    entry: dict
    first: int = -1
    first_call: int = -1


class Compiler:
    def __init__(self, table: cmds.CommandTable, resolver: Resolver | None = None, av_names: list[str] | None = None):
        self.t = table
        self.res = resolver or Resolver()
        self.av = {n.replace(" ", "").casefold(): i for i, n in enumerate(av_names or [])}

    # ================================================================ entry point
    def compile(self, source: str | bytes, script_type: int = 0, fixed_vars: dict[str, int] | None = None,
                fixed_refs: list[tuple] | None = None) -> Compiled:
        if isinstance(source, bytes):
            source = source.decode("latin-1")
        self.out = bytearray()
        self.fix: list[tuple[int, tuple]] = []        # (offset, ref key) patched once the order is known
        self.refs: dict[tuple, _Ref] = {}
        self.use_n = 0
        self.vars: dict[str, Var] = {}
        self.fixed_vars = {k.casefold(): v for k, v in (fixed_vars or {}).items()}
        self.n_stmts = 0
        self.branches: list[list] = []      # stack of open if-chains: [ [stmt_no, jump_offset] ]
        self.begin: tuple | None = None
        self.name = ""
        for lineno, raw in enumerate(re.split(r"\r\n|\n|\r", source), 1):
            self.line = lineno
            toks = self.tokens(raw)
            if toks:
                self.statement(toks)
        if self.begin is not None:
            raise CompileError(self.line, "missing End")
        order = self.order_refs(fixed_refs)
        index = {k: i + 1 for i, k in enumerate(order)}
        for pos, key in self.fix:
            struct.pack_into("<H", self.out, pos, index[key])
        refs = [self.refs[k].entry if k in self.refs else self._fixed_entry(k) for k in order]
        variables = sorted(self.vars.values(), key=lambda v: v.index)
        schr = {"refs": len(refs), "size": len(self.out),
                "vars": max((v.index for v in variables), default=0), "type": script_type}
        return Compiled(bytes(self.out), refs, variables, schr, self.name)

    def _fixed_entry(self, key: tuple) -> dict:
        return {"kind": "SCRV", "var": key[1]} if key[0] == "v" else {"kind": "SCRO", "form": {"key": key[1]}}

    # ================================================================ lexing
    @staticmethod
    def tokens(line: str) -> list[str]:
        out = []
        for m in TOKEN_RE.finditer(line):
            t = m.group(0)
            if t == ";":
                break
            if out and out[-1].endswith(".") and not NUMBER_RE.fullmatch(out[-1]) and re.match(r"[A-Za-z_]", t):
                out[-1] += t                 # `Player. GetItemCount` (the CS tolerates the space)
                continue
            out.append(t)
        if out and not re.match(r"[A-Za-z_]", out[0]):
            return []                        # a stray punctuation line compiles to nothing
        return out

    # ================================================================ emit helpers
    def u16(self, v: int) -> None:
        self.out += struct.pack("<H", v)

    def stmt_start(self, op: int) -> int:
        pos = len(self.out)
        self.u16(op)
        self.u16(0)
        return pos

    def stmt_end(self, pos: int) -> None:
        struct.pack_into("<H", self.out, pos + 2, len(self.out) - pos - 4)
        self.n_stmts += 1

    def ref_slot(self, key: tuple, entry: dict, role: str) -> None:
        r = self.refs.get(key)
        if r is None:
            r = self.refs[key] = _Ref(key, entry)
        if r.first < 0:
            r.first = self.use_n
        if role == "call" and r.first_call < 0:
            r.first_call = self.use_n
        self.use_n += 1
        self.fix.append((len(self.out), key))
        self.u16(0)

    def order_refs(self, fixed: list[tuple] | None) -> list[tuple]:
        if fixed is not None:
            missing = [k for k in self.refs if k not in fixed]
            if missing:
                raise CompileError(self.line, f"reference not in the pinned list: {missing[0]}")
            return list(fixed)
        refs = list(self.refs.values())
        calls = sorted((r for r in refs if r.first_call >= 0), key=lambda r: r.first_call)
        rest = [r for r in refs if r.first_call < 0]
        scrv = sorted((r for r in rest if r.key[0] == "v"), key=lambda r: r.key[1])
        scro = sorted((r for r in rest if r.key[0] != "v"), key=lambda r: r.first)
        return [r.key for r in calls + scrv + scro]

    # ================================================================ names
    def local(self, name: str) -> Var | None:
        return self.vars.get(name.casefold())

    def form(self, name: str) -> dict | None:
        return self.res.form(name)

    def form_key(self, f: dict) -> tuple:
        return ("f", f["owner"].casefold(), f["objid"].upper())

    def ref_operand(self, name: str, role: str) -> None:
        """A reference by name: a local ref variable (SCRV) or a form (SCRO)."""
        v = self.local(name)
        if v is not None:                    # any local works; the CS doesn't check its type
            self.ref_slot(("v", v.index), {"kind": "SCRV", "var": v.index}, role)
            return
        f = self.form(name)
        if f is None:
            raise CompileError(self.line, f"unknown name {name!r}")
        self.ref_slot(self.form_key(f), {"kind": "SCRO", "form": f}, role)

    def ref_operand_form(self, name: str, role: str) -> None:
        f = self.form(name)
        self.ref_slot(self.form_key(f), {"kind": "SCRO", "form": f}, role)

    def ext_var(self, ref_name: str, var_name: str) -> Var:
        if self.local(ref_name) is not None:
            raise CompileError(self.line, f"{ref_name}.{var_name}: variables of ref variables are unsupported")
        f = self.form(ref_name)
        if f is None:
            raise CompileError(self.line, f"unknown name {ref_name!r}")
        names = self.res.script_vars(f) or {}
        v = names.get(var_name.casefold())
        if v is None:
            raise CompileError(self.line, f"{ref_name} has no script variable {var_name!r}")
        return v

    def variable(self, name: str, role: str = "extvar") -> None:
        """A numeric variable operand: local, Quest.var / Ref.var, or a global."""
        if "." in name:
            base, var = name.split(".", 1)
            v = self.ext_var(base, var)
            self.out += b"r"
            self.ref_operand(base, role)
            self.out += v.tag + struct.pack("<H", v.index)
            return
        v = self.local(name)
        if v is not None:
            self.out += v.tag + struct.pack("<H", v.index)
            return
        f = self.form(name)
        if f is not None and f.get("sig") == "GLOB":
            self.out += b"G"
            self.ref_operand(name, "global")
            return
        raise CompileError(self.line, f"unknown variable {name!r}")

    # ================================================================ statements
    def statement(self, toks: list[str]) -> None:
        kw = toks[0].casefold()
        if kw in ("scn", "scriptname"):
            if len(toks) < 2:
                raise CompileError(self.line, "scn without a name")
            self.name = toks[1]
            self.stmt_end(self.stmt_start(0x1D))
            return
        if kw in ("short", "long", "float", "ref", "int"):
            if len(toks) < 2:
                raise CompileError(self.line, f"{kw} without a name")
            name = toks[1]
            if name.casefold() in self.vars:
                return                       # a repeated declaration is ignored (vanilla has five)
            idx = self.fixed_vars.get(name.casefold(),
                                     max([v.index for v in self.vars.values()] + list(self.fixed_vars.values()) + [0]) + 1
                                     if not self.fixed_vars else None)
            if idx is None:
                raise CompileError(self.line, f"variable {name} not in the pinned variable list")
            self.vars[name.casefold()] = Var(idx, name, "short" if kw == "int" else kw)
            return
        if kw == "begin":
            self.begin_block(toks)
            return
        if kw == "end":
            if self.begin is None:
                raise CompileError(self.line, "End without Begin")
            pos = self.stmt_start(0x11)
            self.stmt_end(pos)
            bpos, after = self.begin
            struct.pack_into("<I", self.out, bpos + 6, len(self.out) - after)
            self.begin = None
            return
        if kw == "set":
            self.set_statement(toks)
            return
        if kw in ("if", "elseif"):
            if kw == "elseif":
                self.close_branch()
            pos = self.stmt_start(0x16 if kw == "if" else 0x18)
            jpos = len(self.out)
            self.u16(0)
            self.expression(toks[1:])
            self.stmt_end(pos)
            if kw == "if":
                self.branches.append([])
            self.open_branch(jpos)
            return
        if kw == "else":
            self.close_branch()
            pos = self.stmt_start(0x17)
            jpos = len(self.out)
            self.u16(0)
            self.stmt_end(pos)
            self.open_branch(jpos)
            return
        if kw == "endif":
            self.close_branch()
            if self.branches:
                self.branches.pop()
            self.stmt_end(self.stmt_start(0x19))
            return
        if kw == "return":
            self.stmt_end(self.stmt_start(0x1E))
            return
        self.command_statement(toks)

    def open_branch(self, jpos: int) -> None:
        if not self.branches:          # stray else/elseif: the CS compiles it anyway
            self.branches.append([])
        self.branches[-1].append((self.n_stmts, jpos))

    def close_branch(self) -> None:
        if self.branches and self.branches[-1]:
            stmt_no, jpos = self.branches[-1].pop()
            struct.pack_into("<H", self.out, jpos, self.n_stmts - stmt_no)

    def begin_block(self, toks: list[str]) -> None:
        if self.begin is not None:
            raise CompileError(self.line, "Begin inside a block")
        if len(toks) < 2:
            raise CompileError(self.line, "Begin without a block type")
        blk = self.t.block_by_name.get(toks[1].casefold())
        if blk is None:
            raise CompileError(self.line, f"unknown block type {toks[1]!r}")
        pos = self.stmt_start(0x10)
        self.u16(blk.opcode)
        self.out += b"\0\0\0\0"
        self.params(blk, toks[2:])
        self.stmt_end(pos)
        self.begin = (pos, len(self.out))

    def set_statement(self, toks: list[str]) -> None:
        low = [t.casefold() for t in toks]
        if "to" not in low or len(toks) < 4:
            raise CompileError(self.line, "set needs: set <var> to <expression>")
        i = low.index("to")
        if i != 2:
            raise CompileError(self.line, "set target must be one name")
        pos = self.stmt_start(0x15)
        self.variable(toks[1], "extvar")
        self.expression(toks[i + 1:])
        self.stmt_end(pos)

    def command_statement(self, toks: list[str]) -> None:
        head = toks[0]
        ref = None
        if "." in head and head.split(".", 1)[1]:
            ref, head = head.split(".", 1)
        cmd = self.t.by_name.get(head.casefold())
        if cmd is None:
            raise CompileError(self.line, f"unknown command {head!r}")
        if ref is not None:
            self.u16(0x1C)
            self.ref_operand(ref, "call")
            self.u16(cmd.opcode)
            self.u16(0)
            start = len(self.out)
            self.params(cmd, toks[1:])
            struct.pack_into("<H", self.out, start - 2, len(self.out) - start)
            self.n_stmts += 1
            return
        pos = self.stmt_start(cmd.opcode)
        self.params(cmd, toks[1:])
        self.stmt_end(pos)

    # ================================================================ parameters
    @staticmethod
    def arg_list(args: list[str]) -> list[str]:
        """Drop commas; glue a leading minus onto the number after it (`-25`)."""
        out, i = [], 0
        args = [a for a in args if a != ","]
        while i < len(args):
            if args[i] == "-" and i + 1 < len(args) and NUMBER_RE.fullmatch(args[i + 1]):
                out.append("-" + args[i + 1])
                i += 2
                continue
            out.append(args[i])
            i += 1
        return out

    def params(self, cmd: cmds.Command, args: list[str]) -> None:
        args = self.arg_list(args)
        if cmd.name.casefold() in ("message", "messagebox", "essentialdeathreload"):
            self.formatted(cmd, args)
            return
        if not cmd.params:
            return                  # the CS ignores words after a command without parameters
        if len(args) > len(cmd.params):
            raise CompileError(self.line, f"{cmd.name}: too many parameters")
        missing = [p for p in cmd.params[len(args):] if not p.optional]
        if missing:
            raise CompileError(self.line, f"{cmd.name}: missing parameter {missing[0].name}")
        self.u16(len(args))
        for p, a in zip(cmd.params, args):
            self.param(p, a)

    def param(self, p: cmds.Param, a: str) -> None:
        t = p.type_id
        if t != cmds.STRING and len(a) > 1 and a.startswith('"') and a.endswith('"'):
            a = a[1:-1]                      # a quoted name is accepted for any parameter
        if t == cmds.STRING:
            text = a[1:-1] if a.startswith('"') and a.endswith('"') and len(a) > 1 else a
            b = text.encode("latin-1")
            self.u16(len(b))
            self.out += b
            return
        if t in (cmds.INTEGER, cmds.QUEST_STAGE, cmds.FLOAT):
            if SIGNED_RE.fullmatch(a):
                if t == cmds.FLOAT:
                    self.out += b"z" + struct.pack("<d", float(a))
                else:
                    self.out += b"n" + struct.pack("<i", int(float(a)))
                return
            self.variable(a, "extvar")
            return
        if t == cmds.ACTOR_VALUE:
            code = self.av.get(a.casefold())
            if code is None:
                raise CompileError(self.line, f"unknown actor value {a!r}")
            self.u16(code)
            return
        if t == cmds.ANIM_GROUP:
            self.u16(self.code(ANIM_GROUPS, a, "animation group"))
            return
        if t == cmds.SEX:
            self.u16(self.code(SEXES, a, "sex"))
            return
        if t == cmds.CRIME_TYPE:
            self.u16(self.code(CRIME_TYPES, a, "crime type") if not a.isdigit() else int(a))
            return
        if t == cmds.AXIS:
            if a.upper() not in ("X", "Y", "Z"):
                raise CompileError(self.line, f"bad axis {a!r}")
            self.out += a.upper().encode()
            return
        if t in cmds.FORM_PARAMS and t not in UNCONFIRMED_PARAMS:
            self.out += b"r"
            v = self.local(a)
            if v is not None and v.kind != "ref" and self.form(a) is not None:
                self.ref_operand_form(a, "param")      # a form beats a same-named number variable
            else:
                self.ref_operand(a, "param")
            return
        raise CompileError(self.line, f"parameter type {t:#04x} ({p.name}) is not confirmed by the corpus")

    def code(self, names: list[str], a: str, what: str) -> int:
        for i, n in enumerate(names):
            if n.casefold() == a.casefold():
                return i
        raise CompileError(self.line, f"unknown {what} {a!r}")

    def formatted(self, cmd: cmds.Command, args: list[str]) -> None:
        if not args or not args[0].startswith('"'):
            raise CompileError(self.line, f"{cmd.name} needs a quoted text")
        self.u16(1)
        text = args[0][1:-1].encode("latin-1")
        self.u16(len(text))
        self.out += text
        rest = args[1:]
        if cmd.name.casefold() == "message":
            fmt = [a for a in rest if not NUMBER_RE.fullmatch(a)]
            secs = [a for a in rest if NUMBER_RE.fullmatch(a)]
            self.u16(len(fmt))
            for a in fmt:
                self.variable(a, "extvar")
            self.u16(int(float(secs[0])) if secs else 0)
            self.u16(0)
            return
        fmt = [a for a in rest if not a.startswith('"')]
        buttons = [a for a in rest if a.startswith('"')]
        self.u16(len(fmt))
        for a in fmt:
            self.variable(a, "extvar")
        self.u16(len(buttons))
        for b in buttons:
            self.u16(1)
            bb = b[1:-1].encode("latin-1")
            self.u16(len(bb))
            self.out += bb

    # ================================================================ expressions
    def expression(self, toks: list[str]) -> None:
        """Infix tokens -> postfix bytes, each token preceded by a space. Writes u16 length first."""
        lpos = len(self.out)
        self.u16(0)
        start = len(self.out)
        items = self.expr_items(toks)
        for kind, val in self.to_postfix(items):
            self.out += b" "
            if kind == "op":
                self.out += val.encode()
            else:
                val()
        struct.pack_into("<H", self.out, lpos, len(self.out) - start)

    def expr_items(self, toks: list[str]) -> list[tuple]:
        """Group tokens into operands (callables that emit bytes), operators and parentheses."""
        items, i = [], 0
        prev_operand = False
        while i < len(toks):
            t = toks[i]
            if t in ("(", ")"):
                items.append(("paren", t))
                prev_operand = t == ")"
                i += 1
                continue
            if t in PRECEDENCE or t == "!":
                if t == "-" and not prev_operand:
                    items.append(("op", "~"))
                else:
                    items.append(("op", t))
                prev_operand = False
                i += 1
                continue
            if t == ",":
                i += 1
                continue
            emit, i = self.operand(toks, i)
            items.append(("val", emit))
            prev_operand = True
        return items

    def operand(self, toks: list[str], i: int):
        t = toks[i]
        if NUMBER_RE.fullmatch(t):
            text = t.encode()
            return (lambda: self.out.__iadd__(text)), i + 1
        ref, name = (t.split(".", 1) if "." in t and not NUMBER_RE.fullmatch(t) else (None, t))
        cmd = self.t.by_name.get(name.casefold())
        if cmd is not None and not (ref is None and self.local(name) is not None):
            n = len(cmd.params) if cmd.name.casefold() not in ("message", "messagebox") else 0
            args = []
            j = i + 1
            while j < len(toks) and len(args) < n and toks[j] not in PRECEDENCE and toks[j] not in ("(", ")", "!"):
                if toks[j] != ",":
                    args.append(toks[j])
                j += 1

            def emit(cmd=cmd, ref=ref, args=args):
                if ref is not None:
                    self.out += b"r"
                    self.ref_operand(ref, "exprref")
                self.out += b"X"
                self.u16(cmd.opcode)
                self.u16(0)
                start = len(self.out)
                self.params(cmd, args)
                struct.pack_into("<H", self.out, start - 2, len(self.out) - start)
            return emit, j
        if ref is not None:
            def emit_ext(t=t):
                self.variable(t, "exprref")
            return emit_ext, i + 1
        if self.local(t) is not None:
            v = self.local(t)
            return (lambda v=v: self.out.__iadd__(v.tag + struct.pack("<H", v.index))), i + 1
        f = self.form(t)
        if f is not None:
            if f.get("sig") == "GLOB":
                def emit_glob(t=t):
                    self.out += b"G"
                    self.ref_operand(t, "global")
                return emit_glob, i + 1

            def emit_ref(t=t):
                self.out += b"Z"
                self.ref_operand(t, "value")
            return emit_ref, i + 1
        raise CompileError(self.line, f"unknown name {t!r} in expression")

    def to_postfix(self, items: list[tuple]) -> list[tuple]:
        out, ops = [], []
        for kind, val in items:
            if kind == "val":
                out.append(("val", val))
            elif kind == "paren" and val == "(":
                ops.append(val)
            elif kind == "paren":
                while ops and ops[-1] != "(":
                    out.append(("op", ops.pop()))
                if not ops:
                    raise CompileError(self.line, "unbalanced )")
                ops.pop()
            else:
                p = PRECEDENCE.get(val, 0)
                while ops and ops[-1] != "(" and (PRECEDENCE[ops[-1]] > p or
                                                  (PRECEDENCE[ops[-1]] == p and val != "~")):
                    out.append(("op", ops.pop()))
                ops.append(val)
        while ops:
            op = ops.pop()
            if op == "(":
                raise CompileError(self.line, "unbalanced (")
            out.append(("op", op))
        return out


NUMBER_RE = re.compile(r"\d+(\.\d*)?|\.\d+")
SIGNED_RE = re.compile(r"-?(\d+(\.\d*)?|\.\d+)")
UNCONFIRMED_PARAMS = {0x13, 0x14, 0x27}       # Global, Furniture, Climate: never used by vanilla scripts
