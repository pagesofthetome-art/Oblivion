"""S0/S1: script extraction, the corpus bundle and the SCDA decompiler, on invented scripts.

The command names, opcodes and bytecode here are made up for the test (no Bethesda data); they only
follow the statement/parameter shapes documented in forge/script/bytecode.py.
"""

from __future__ import annotations

import gzip
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from forge.script import bytecode as bc, commands as cmds, survey  # noqa: E402
from forge.script.extract import iter_scripts, resolve_refs  # noqa: E402
from forge.tests.fixtures import grup, plugin, rec, sub, top, u32, z  # noqa: E402

COMMANDS = [
    {"name": "FxGive", "opcode": 0x1001, "table": "script",
     "params": [{"name": "item", "type_id": 3, "optional": False}, {"name": "count", "type_id": 1, "optional": True}]},
    {"name": "FxSay", "opcode": 0x1002, "table": "script",
     "params": [{"name": "text", "type_id": 0, "optional": False}, {"name": "v", "type_id": 2, "optional": True}]},
    {"name": "FxGetLevel", "opcode": 0x1003, "table": "script", "params": []},
    {"name": "FxModAV", "opcode": 0x1004, "table": "script",
     "params": [{"name": "av", "type_id": 5, "optional": False}, {"name": "amount", "type_id": 2, "optional": False}]},
    {"name": "FxGameMode", "opcode": 0, "table": "block", "params": []},
    {"name": "FxOnActivate", "opcode": 2, "table": "block",
     "params": [{"name": "ref", "type_id": 4, "optional": True}]},
]


def st(op: int, body: bytes = b"") -> bytes:
    return struct.pack("<HH", op, len(body)) + body


def call(op: int, *params: bytes) -> bytes:
    return st(op, (struct.pack("<H", len(params)) + b"".join(params)) if params else b"")


def expr(text: bytes) -> bytes:
    return struct.pack("<H", len(text)) + text


def local(tag: str, i: int) -> bytes:
    return tag.encode() + struct.pack("<H", i)


def build_script() -> tuple[bytes, list[dict], list[dict]]:
    """scn / begin FxOnActivate Player / if doOnce == 0 / set doOnce to 1 / Player.FxGive Gold 5 /
    elseif doOnce > FxGetLevel / FxSay "hi" doOnce / else / return / endif / end"""
    variables = [{"index": 1, "name": "doOnce"}, {"index": 2, "name": "target"}]
    refs = [{"kind": "SCRO", "edid": "Player"}, {"kind": "SCRO", "edid": "Gold"}, {"kind": "SCRV", "var": 2}]
    stmts = [
        ("if", expr(b" s\x01\x00 == 0")),
        ("set", local("s", 1) + expr(b" 1")),
        ("raw", struct.pack("<HH", 0x1C, 1) + call(0x1001, b"r\x02\x00", b"n" + struct.pack("<i", 5))),
        ("elseif", expr(b" s\x01\x00 > X\x03\x10\x00\x00")),
        ("raw", call(0x1002, struct.pack("<H", 2) + b"hi", local("s", 1))),
        ("else", b""),
        ("raw", st(0x1E)),
        ("raw", st(0x19)),
    ]
    # jumps: statements to the next branch at the same level (one candidate the survey measures)
    encoded = []
    for kind, payload in stmts:
        if kind == "if":
            encoded.append(lambda j, p=payload: st(0x16, struct.pack("<H", j) + p))
        elif kind == "elseif":
            encoded.append(lambda j, p=payload: st(0x18, struct.pack("<H", j) + p))
        elif kind == "else":
            encoded.append(lambda j: st(0x17, struct.pack("<H", j)))
        elif kind == "set":
            encoded.append(lambda j, p=payload: st(0x15, p))
        else:
            encoded.append(lambda j, p=payload: p)
    jumps = {0: 3, 3: 2, 5: 2}
    inner = b"".join(f(jumps.get(i, 0)) for i, f in enumerate(encoded))
    end = st(0x11)
    begin_body = struct.pack("<HI", 2, len(inner)) + struct.pack("<H", 1) + b"r\x01\x00"
    data = st(0x1D) + st(0x10, begin_body) + inner + end
    return data, variables, refs


class DecompilerTest(unittest.TestCase):
    def setUp(self):
        self.table = cmds.CommandTable(COMMANDS)

    def test_decodes_every_statement_kind(self):
        data, variables, refs = build_script()
        dec = bc.Decompiler(self.table, variables, refs).decode(data)
        self.assertTrue(dec.ok, dec.issues)
        texts = [s.text for s in dec.stmts]
        self.assertEqual(texts[0], "ScriptName")
        self.assertEqual(texts[1], "Begin FxOnActivate Player")
        self.assertEqual(texts[2], "if doOnce == 0")
        self.assertEqual(texts[3], "set doOnce to 1")
        self.assertEqual(texts[4], "Player.FxGive Gold 5")
        self.assertEqual(texts[5], "elseif doOnce > FxGetLevel")
        self.assertEqual(texts[6], 'FxSay "hi" doOnce')
        self.assertEqual(texts[7:], ["else", "Return", "EndIf", "End"])
        self.assertEqual(dec.jumps["If:stmts"], 1)
        self.assertEqual(dec.jumps["ElseIf:stmts"], 1)
        self.assertEqual(dec.jumps["Else:stmts"], 1)
        self.assertEqual(dec.jumps["Begin:bytes_to_end"], 1)
        listing = bc.listing(dec)
        self.assertIn("    set doOnce to 1", listing)

    def test_truncation_and_leftovers_are_reported_not_guessed(self):
        data, variables, refs = build_script()
        dec = bc.Decompiler(self.table, variables, refs).decode(data[:-2])
        self.assertFalse(dec.ok)
        self.assertEqual(dec.issues[0].kind, "truncated")
        bad = st(0x1D) + call(0x1003) + st(0x1002, b"\x01\x00" + b"\x05\x00hello" + b"!!")
        dec = bc.Decompiler(self.table).decode(bad)
        self.assertEqual(dec.issues[0].kind, "leftover param bytes")
        dec = bc.Decompiler(self.table).decode(st(0x15, local("s", 1) + expr(b" 1 ? 2")))
        self.assertEqual(dec.issues[0].kind, "bad expression byte")

    def test_unknown_opcode_keeps_structure(self):
        dec = bc.Decompiler(cmds.CommandTable()).decode(st(0x1D) + st(0x1234, b"\x00\x00") + st(0x1E))
        self.assertEqual([s.name for s in dec.stmts], ["ScriptName", "op1234", "Return"])
        self.assertEqual(dec.issues[0].kind, "unknown opcode")

    def test_code_params_and_literals(self):
        data = call(0x1004, struct.pack("<H", 8), b"z" + struct.pack("<d", 2.5))
        dec = bc.Decompiler(self.table).decode(data)
        self.assertTrue(dec.ok, dec.issues)
        self.assertEqual(dec.stmts[0].text, "FxModAV av#8 2.5")

    def test_source_blocks_ignore_comments(self):
        self.assertEqual(bc.source_blocks("scn X\r\n;begin Fake\r\nBegin GameMode\r\nend\r\n  begin onActivate player"),
                         ["GameMode", "onActivate"])


def fixture_plugin(data: bytes) -> bytes:
    schr = struct.pack("<4sIIII", b"\0" * 4, 3, len(data), 2, 0)
    scpt = rec("SCPT", 0x01000800, sub("EDID", z("FxScript")), sub("SCHR", schr), sub("SCDA", data),
               sub("SCTX", b"scn FxScript\r\nbegin FxOnActivate player\r\nend"),
               sub("SLSD", u32(1) + b"\0" * 12 + b"\x01" + b"\0" * 7), sub("SCVR", z("doOnce")),
               sub("SLSD", u32(2) + b"\0" * 20), sub("SCVR", z("target")),
               sub("SCRO", u32(0x14)), sub("SCRO", u32(0x01000802)), sub("SCRV", u32(2)))
    gold = rec("MISC", 0x01000802, sub("EDID", z("Gold")))
    small = st(0x1D) + st(0x1E)
    rschr = struct.pack("<4sIIII", b"\0" * 4, 0, len(small), 0, 0)
    qust = rec("QUST", 0x01000803, sub("EDID", z("FxQuest")), sub("INDX", struct.pack("<H", 10)),
               sub("QSDT", b"\0"), sub("CNAM", z("log")), sub("SCHR", rschr), sub("SCDA", small),
               sub("SCTX", b"return"), sub("QSDT", b"\0"), sub("SCHR", rschr), sub("SCDA", small),
               sub("SCTX", b"return"))
    dial = rec("DIAL", 0x01000804, sub("EDID", z("FxTopic")))
    info = rec("INFO", 0x01000805, sub("SCHR", rschr), sub("SCDA", small), sub("SCTX", b"return"))
    return plugin(["Oblivion.esm"], top("SCPT", scpt), top("MISC", gold), top("QUST", qust),
                  top("DIAL", dial, grup(struct.pack("<I", 0x01000804), 7, info)))


class ExtractAndSurveyTest(unittest.TestCase):
    def test_extract_export_and_survey(self):
        data, _v, _r = build_script()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "Data").mkdir()
            (td / "Data" / "Fixture.esp").write_bytes(fixture_plugin(data))
            forms = {}
            rows = [r for r, _ in iter_scripts(td / "Data" / "Fixture.esp", forms)]
            for r in rows:
                resolve_refs(r, forms)
            self.assertEqual([(r["sig"], r["ctx"]) for r in rows],
                             [("SCPT", ""), ("QUST", "stage 10 entry 0"), ("QUST", "stage 10 entry 1"),
                              ("INFO", "topic FxTopic")])
            scpt = rows[0]
            self.assertEqual([v["name"] for v in scpt["vars"]], ["doOnce", "target"])
            self.assertEqual(scpt["vars"][0]["flags"], 1)
            self.assertEqual([r.get("edid", r.get("var")) for r in scpt["refs"]], ["", "Gold", 2])
            self.assertEqual(scpt["refs"][0]["owner"], "Oblivion.esm")
            self.assertEqual(scpt["sctx"].encode("latin-1")[:12], b"scn FxScript")

            from forge.kb.export import export_scripts
            out = td / "corpus.jsonl.gz"
            meta = export_scripts(td / "Data", out, None, ["Fixture.esp"])
            self.assertEqual(meta["scripts"], 4)
            self.assertEqual(meta["plugins"]["Fixture.esp"], {"SCPT": 1, "QUST": 2, "INFO": 1})
            with gzip.open(out, "rt", encoding="utf-8") as fh:
                kinds = [json.loads(line)["row"] for line in fh]
            self.assertEqual(kinds[0], "meta")
            self.assertIn("form", kinds)

            cfile = td / "commands.jsonl"
            cfile.write_text("\n".join(json.dumps(c) for c in COMMANDS), encoding="utf-8")
            table = cmds.load(cfile)
            s = survey.survey(survey.iter_rows(out), table)
            self.assertEqual(s["decoded_ok"], 4, s)
            self.assertEqual(s["pass_rate"], 100.0)
            self.assertEqual(s["schr"], {})
            self.assertEqual(s["block_types"][2]["source"], {"fxonactivate": 1})
            # the plugin path gives the same answer as the corpus path
            s2 = survey.survey(survey.iter_rows(td / "Data" / "Fixture.esp"), table)
            self.assertEqual(s2["decoded_ok"], 4)
            self.assertIn("PASS", survey.format_survey(s))


if __name__ == "__main__":
    unittest.main()
