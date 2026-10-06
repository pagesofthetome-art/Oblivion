"""S2-S4: the compiler, on invented commands and forms (no Bethesda data).

The vanilla-corpus proof is `forge script-check` on the PC export; these tests pin the rules it
established so they can't regress.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from forge.script import bytecode as bc, commands as cmds  # noqa: E402
from forge.script.compiler import Compiler, CompileError, Resolver, Var  # noqa: E402
from forge.tests.test_script_decode import COMMANDS, build_script  # noqa: E402

FORMS = {
    "player": {"owner": "Fx.esp", "objid": "000014", "sig": "REFR", "edid": "player"},
    "gold": {"owner": "Fx.esp", "objid": "000801", "sig": "MISC", "edid": "Gold"},
    "fxquest": {"owner": "Fx.esp", "objid": "000802", "sig": "QUST", "edid": "FxQuest"},
    "fxglobal": {"owner": "Fx.esp", "objid": "000803", "sig": "GLOB", "edid": "FxGlobal"},
    "fxdoor": {"owner": "Fx.esp", "objid": "000804", "sig": "REFR", "edid": "FxDoor"},
}


class FxResolver(Resolver):
    def form(self, name):
        return FORMS.get(name.casefold())

    def script_vars(self, form):
        if form["edid"] == "FxQuest":
            return {"stage": Var(3, "stage", "short"), "timer": Var(4, "timer", "float")}
        return None


SOURCE = """scn FxScript
short doOnce  ; a comment
ref target
begin FxOnActivate Player
\tif doOnce == 0
\t\tset doOnce to 1
\t\tPlayer.FxGive Gold 5
\telseif doOnce > FxGetLevel
\t\tFxSay "hi" doOnce
\telse
\t\treturn
\tendif
end
"""


def compile_(src, **kw):
    return Compiler(cmds.CommandTable(COMMANDS), FxResolver(), ["Strength", "Intelligence", "Health"]).compile(src, **kw)


def ref_names(c):
    return [r["form"]["edid"] if r["kind"] == "SCRO" else f"SCRV{r['var']}" for r in c.refs]


class CompilerTest(unittest.TestCase):
    def test_round_trip_with_the_decoder_fixture(self):
        data, _v, _r = build_script()
        c = compile_(SOURCE)
        self.assertEqual(c.scda, data)              # byte for byte what the decoder tests decode
        self.assertEqual(ref_names(c), ["player", "Gold"])
        self.assertEqual([(v.index, v.name, v.kind) for v in c.vars], [(1, "doOnce", "short"), (2, "target", "ref")])
        self.assertEqual(c.schr, {"refs": 2, "size": len(data), "vars": 2, "type": 0})
        self.assertEqual(c.name, "FxScript")

    def test_expressions_are_postfix_with_cs_precedence(self):
        c = compile_("short a\nshort b\nset a to (a + 2) * b - -1\nif a == 1 && b == 2 || a == 3\nendif")
        dec = bc.Decompiler(cmds.CommandTable(COMMANDS), [{"index": 1, "name": "a"}, {"index": 2, "name": "b"}]).decode(c.scda)
        self.assertTrue(dec.ok, dec.issues)
        self.assertEqual(dec.stmts[0].text, "set a to a 2 + b * 1 ~ -")
        # the CS binds || tighter than && (vanilla corpus)
        self.assertEqual(dec.stmts[1].text, "if a 1 == b 2 == a 3 == || &&")

    def test_reference_order_rule(self):
        # calling references first, then ref variables by index, then the rest by first use
        src = ("ref r1\nref r2\nbegin FxGameMode\nFxGive Gold\nset r2 to FxDoor\nr1.FxGetLevel\n"
               "FxGive r2\nFxDoor.FxGetLevel\nend")
        c = compile_(src)
        self.assertEqual(ref_names(c), ["SCRV1", "FxDoor", "SCRV2", "Gold"])

    def test_quest_variables_globals_and_negative_params(self):
        c = compile_("set FxQuest.stage to FxGlobal + FxQuest.timer\nFxModAV Health -5")
        self.assertEqual(c.scda[:7], struct.pack("<HH", 0x15, 21) + b"r\x01\x00")
        self.assertIn(b"s\x03\x00", c.scda)
        self.assertIn(b" G\x02\x00", c.scda)
        self.assertIn(b"r\x01\x00f\x04\x00", c.scda)
        self.assertTrue(c.scda.endswith(struct.pack("<HHH", 0x1004, 13, 2) + struct.pack("<H", 2) + b"z" +
                                        struct.pack("<d", -5.0)))

    def test_message_and_messagebox(self):
        c = compile_('short n\nMessage "%.0f left", n, 5\nMessageBox "Go?", "Yes", "No"')
        dec = bc.Decompiler(cmds.CommandTable(COMMANDS), [{"index": 1, "name": "n"}]).decode(c.scda)
        self.assertTrue(dec.ok, dec.issues)
        self.assertEqual([s.text for s in dec.stmts], ['Message "%.0f left", n, 5', 'MessageBox "Go?", "Yes", "No"'])

    def test_cs_tolerances(self):
        # stray endif, a repeated declaration, a punctuation line, `Ref. Func`, words after a no-param command
        c = compile_("short a\nshort a\n:\nendif\nFxDoor. FxGetLevel\nFxGetLevel junk")
        dec = bc.Decompiler(cmds.CommandTable(COMMANDS), [{"index": 1, "name": "a"}], c.refs and
                            [{"kind": "SCRO", "edid": "FxDoor"}]).decode(c.scda)
        self.assertEqual([s.text for s in dec.stmts], ["EndIf", "FxDoor.FxGetLevel", "FxGetLevel"])
        self.assertEqual(len(c.vars), 1)

    def test_unknowns_are_errors_not_guesses(self):
        for src, msg in [("FxNoSuchCommand", "unknown command"), ("FxGive NoSuchForm", "unknown name"),
                         ("set nothing to 1", "unknown variable"), ("FxModAV Charisma 1", "unknown actor value"),
                         ("begin FxNoBlock\nend", "unknown block type"), ("begin FxGameMode", "missing End")]:
            with self.assertRaises(CompileError, msg=src) as cm:
                compile_(src)
            self.assertIn(msg, str(cm.exception))

    def test_unconfirmed_param_types_refuse(self):
        table = cmds.CommandTable(COMMANDS + [{"name": "FxSetGlobal", "opcode": 0x1009, "table": "script",
                                               "params": [{"name": "g", "type_id": 0x13, "optional": False}]}])
        with self.assertRaises(CompileError) as cm:
            Compiler(table, FxResolver()).compile("FxSetGlobal FxGlobal")
        self.assertIn("not confirmed", str(cm.exception))

    def test_pinned_variables_and_references(self):
        c = compile_("short a\nshort b\nset b to a", fixed_vars={"a": 4, "b": 7})
        self.assertEqual([(v.name, v.index) for v in c.vars], [("a", 4), ("b", 7)])
        self.assertEqual(c.schr["vars"], 7)
        c = compile_("FxGive Gold\nFxGive FxDoor", fixed_refs=[("f", "fx.esp", "000804"), ("f", "fx.esp", "000801")])
        self.assertIn(b"r\x02\x00", c.scda[:12])


if __name__ == "__main__":
    unittest.main()
