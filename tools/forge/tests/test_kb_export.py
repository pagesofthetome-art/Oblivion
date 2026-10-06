"""The PC-side exporters, exercised on synthetic data (no Bethesda files needed)."""

from __future__ import annotations

import json
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

from forge.kb import build as kbuild, export, query as q  # noqa: E402
from forge.tests import fixtures  # noqa: E402

BASE = 0x400000
SECT_VA = 0x1000
SECT_OFF = 0x200


def fake_exe(commands: list[tuple], *more_tables: list[tuple]) -> bytes:
    """A minimal PE32 with one section holding strings, ParamInfo and CommandInfo arrays.

    commands: (name, alias, opcode, help, needs_parent, [(param_name, type_id, optional)])
    """
    tables = [commands, *more_tables]
    commands = [c for t in tables for c in t]
    blob = bytearray(b"\0" * 16)
    strings = {}

    def s(text):
        if text not in strings:
            strings[text] = SECT_VA + BASE + len(blob)
            blob.extend(text.encode() + b"\0")
        return strings[text]

    params_va = []
    for name, alias, op, helptext, needs, params in commands:
        s(name); alias and s(alias); s(helptext)
        for p in params:
            s(p[0])
    while len(blob) % 4:
        blob.append(0)
    for name, alias, op, helptext, needs, params in commands:
        params_va.append(SECT_VA + BASE + len(blob) if params else 0)
        for pn, tid, opt in params:
            blob.extend(struct.pack("<III", strings[pn], tid, opt))
    pvas = iter(params_va)
    for table in tables:
        blob.extend(b"\xAA" * 40)                     # junk around each table
        for (name, alias, op, helptext, needs, params), pva in zip(table, pvas):
            blob.extend(export.CMD.pack(strings[name], strings[alias] if alias else 0, op, strings[helptext],
                                        needs, len(params), pva, 0, 0, 0, 0))
    blob.extend(b"\xAA" * 40)
    raw = bytes(blob) + b"\0" * (-len(blob) % 0x200)
    # headers
    pe_off = 0x40
    hdr = bytearray(SECT_OFF)
    hdr[0:2] = b"MZ"
    struct.pack_into("<I", hdr, 0x3C, pe_off)
    hdr[pe_off:pe_off + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", hdr, pe_off + 4, 0x14C, 1, 0, 0, 0, 0xE0, 0x102)
    opt = pe_off + 24
    struct.pack_into("<H", hdr, opt, 0x10B)
    struct.pack_into("<I", hdr, opt + 28, BASE)
    sec = opt + 0xE0
    hdr[sec:sec + 8] = b".rdata\0\0"
    struct.pack_into("<IIII", hdr, sec + 8, len(raw), SECT_VA, len(raw), SECT_OFF)
    return bytes(hdr) + raw


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forge-kbx-"))

    def tearDown(self):
        q.close_all()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_commands_from_exe(self):
        cmds = [("GetPos", "", 0x1024, "get a position", 1, [("Axis", 8, 0)]),
                ("PlaceAtMe", "", 0x1025, "spawn an object", 1, [("ObjectID", 0x15, 0), ("count", 1, 1)]),
                ("PositionWorld", "", 0x1026, "place in a worldspace", 1,
                 [("x", 2, 0), ("y", 2, 0), ("z", 2, 0), ("zrot", 2, 0), ("WorldSpace", 0x1B, 0)])]
        exe = self.tmp / "Oblivion.exe"
        exe.write_bytes(fake_exe(cmds))
        out = self.tmp / "vanilla_commands.jsonl"
        counts = export.export_commands(exe, out)
        self.assertEqual(counts["script_commands"], 3)
        rows = [json.loads(x) for x in out.read_text().splitlines()]
        self.assertEqual([r["name"] for r in rows], ["GetPos", "PlaceAtMe", "PositionWorld"])
        self.assertEqual(rows[2]["params"][-1], {"name": "WorldSpace", "type_id": 0x1B, "optional": False})
        # the build folds them in: PositionWorld gets typed params and multi-source confidence
        db = self.tmp / "kb.sqlite"
        kbuild.build(db, None, out)
        f = q.func("PositionWorld", db)
        self.assertEqual([p["type"] for p in f["params"]], ["Float", "Float", "Float", "Float", "WorldSpace"])
        self.assertEqual(f["confidence"], "CONFIRMED_MULTI_SOURCE")
        self.assertEqual(f["opcode"], 0x1026)

    def test_block_table_from_exe(self):
        cmds = [("PlaceAtMe", "", 0x1025, "spawn an object", 1, [("ObjectID", 0x15, 0)])]
        blocks = [("GameMode", "", 0, "", 0, []), ("MenuMode", "", 1, "", 0, [("Menu Type", 1, 1)]),
                  ("OnActivate", "", 2, "", 0, [("ObjectReferenceID", 4, 1)])]
        exe = self.tmp / "Oblivion.exe"
        exe.write_bytes(fake_exe(cmds, blocks))
        out = self.tmp / "vanilla_commands.jsonl"
        counts = export.export_commands(exe, out)
        self.assertEqual(counts["block_types"], 3)
        rows = [json.loads(x) for x in out.read_text().splitlines()]
        blk = [r for r in rows if r["table"] == "block"]
        self.assertEqual([(r["name"], r["opcode"]) for r in blk], [("GameMode", 0), ("MenuMode", 1), ("OnActivate", 2)])
        self.assertEqual(blk[2]["params"], [{"name": "ObjectReferenceID", "type_id": 4, "optional": True}])
        # the KB still takes only the script table
        db = self.tmp / "kb.sqlite"
        kbuild.build(db, None, out)
        self.assertIsNone(q.func("OnActivate", db))

    def test_export_commands_rejects_other_files(self):
        exe = self.tmp / "x.exe"
        exe.write_bytes(fake_exe([("Foo", "", 0x1001, "x", 0, [])]))
        with self.assertRaises(ValueError):
            export.export_commands(exe, self.tmp / "out.jsonl")

    def test_export_vanilla_and_lookup(self):
        fx = fixtures.make(self.tmp / "fx")
        out = self.tmp / "vanilla_index.jsonl"
        # DLCShiveringIsles.esp is a record-less stub here, as in the GOG build
        counts = export.export_vanilla(fx["installed"], out, ["Oblivion.esm", "DLCShiveringIsles.esp", "UOP.esp"])
        rows = out.read_text(encoding="utf-8").splitlines()
        self.assertEqual(counts["Oblivion.esm"], sum('"plugin": "Oblivion.esm"' in x for x in rows))
        self.assertGreater(counts["Oblivion.esm"], 0)
        self.assertEqual(counts["DLCShiveringIsles.esp"], 0)
        db = self.tmp / "kb.sqlite"
        kbuild.build(db, out, None)
        r = q.form("TestNPC", db)
        base = [x for x in r if not x["override"]]
        self.assertEqual((base[0]["plugin"], base[0]["formid"], base[0]["sig"]), ("Oblivion.esm", "00000100", "NPC_"))
        self.assertTrue(any(x["override"] and x["plugin"] == "UOP.esp" for x in r))
        self.assertEqual(q.form("00000100", db)[0]["edid"], "TestNPC")
        self.assertEqual([x["edid"] for x in q.forms_of_type("QUST", db)], ["TestQuest"])
        hits = q.search("TestQuest", 3, ["form"], db)
        self.assertEqual(hits[0]["detail"]["sig"], "QUST")


if __name__ == "__main__":
    unittest.main()
