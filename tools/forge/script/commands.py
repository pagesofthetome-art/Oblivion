"""Command, block-type and parameter tables for the script compiler and decompiler.

Source: the local export of Oblivion.exe's CommandInfo tables (`forge kb export-commands`, or the
"command" rows inside `forge-script-corpus.jsonl.gz`). Bethesda-derived, so it is read at run time
from the PC's git-ignored files and never committed.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMMANDS = ROOT / "vanilla_commands.jsonl"
DEFAULT_CORPUS = ROOT / "forge-script-corpus.jsonl.gz"

# ParamType ids (xOBSE CommandTable.h); names match kb/data/param_types.json
STRING, INTEGER, FLOAT = 0x00, 0x01, 0x02
ACTOR_VALUE, AXIS, ANIM_GROUP, SEX, VARIABLE_NAME, QUEST_STAGE, CRIME_TYPE, FORM_TYPE = \
    0x05, 0x08, 0x0A, 0x12, 0x16, 0x17, 0x1C, 0x21
FORM_PARAMS = {0x03, 0x04, 0x06, 0x07, 0x09, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x13, 0x14, 0x15,
               0x18, 0x19, 0x1A, 0x1B, 0x1D, 0x1E, 0x1F, 0x20, 0x22, 0x23, 0x24, 0x25, 0x27}
CODE16_PARAMS = {ACTOR_VALUE, ANIM_GROUP, SEX, CRIME_TYPE}


@dataclass
class Param:
    name: str
    type_id: int
    optional: bool


@dataclass
class Command:
    opcode: int
    name: str
    alias: str = ""
    params: list[Param] = field(default_factory=list)
    table: str = "script"
    ref_required: bool = False


class CommandTable:
    def __init__(self, rows: list[dict] | None = None):
        self.by_op: dict[int, Command] = {}
        self.by_name: dict[str, Command] = {}
        self.blocks: dict[int, Command] = {}
        self.block_by_name: dict[str, Command] = {}
        for r in rows or []:
            self.add(r)

    def add(self, r: dict) -> None:
        c = Command(r["opcode"], r["name"], r.get("alias", ""),
                    [Param(p.get("name", ""), p["type_id"], bool(p.get("optional"))) for p in r.get("params", [])],
                    r.get("table", "script"), bool(r.get("ref_required")))
        if c.table == "block":
            self.blocks[c.opcode] = c
            for n in (c.name, c.alias):
                if n:
                    self.block_by_name.setdefault(n.casefold(), c)
            return
        self.by_op[c.opcode] = c
        for n in (c.name, c.alias):
            if n:
                self.by_name.setdefault(n.casefold(), c)

    def __len__(self) -> int:
        return len(self.by_op)


def _rows(path: Path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def load(path: Path | str | None = None) -> CommandTable:
    """From vanilla_commands.jsonl or a script corpus bundle. Missing file -> empty table
    (the decompiler then shows raw opcodes)."""
    if path is None:
        path = DEFAULT_COMMANDS if DEFAULT_COMMANDS.is_file() else DEFAULT_CORPUS
    path = Path(path)
    t = CommandTable()
    if not path.is_file():
        return t
    for r in _rows(path):
        if r.get("row", "command") == "command" and "opcode" in r:
            t.add(r)
        elif r.get("row") == "script":
            break               # corpus bundles list commands first
    return t
