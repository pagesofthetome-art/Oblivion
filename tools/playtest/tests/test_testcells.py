"""ForgeTestCells.esp: deterministic, parses back, lints clean, and the layout resolves."""

from __future__ import annotations

import struct
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from playtest.tests import base  # noqa: F401
from playtest import examples, testcells
from playtest.tests import fixtures

import tes4_plugin as tp


class TestCellsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="testcells-"))
        fixtures.fake_esm(cls.dir / "Oblivion.esm")
        cls.esp, cls.lj = testcells.write(cls.dir)
        cls.pl = tp.load(cls.esp)

    def test_deterministic(self):
        a, _ = testcells.build_plugin()
        b, _ = testcells.build_plugin()
        self.assertEqual(a, b)
        self.assertEqual(a, self.esp.read_bytes())

    def test_parses_back(self):
        self.assertEqual(self.pl.errors, [])
        self.assertEqual(self.pl.masters, ["Oblivion.esm"])
        c = Counter(r.sig for r in self.pl.records)
        self.assertEqual(c["CELL"], 3)
        self.assertEqual(c["NPC_"], 4)
        self.assertEqual(c["PACK"], 4)
        self.assertEqual(c["ACHR"], 6)
        self.assertEqual(self.pl.num_records, len(self.pl.records))

    def test_cells_and_children(self):
        cells = {r.form_id: r.editor_id for r in self.pl.records if r.sig == "CELL"}
        self.assertEqual(sorted(cells.values()), ["ForgeTestArena", "ForgeTestOpen", "ForgeTestStreet"])
        by_cell = Counter(cells.get(r.parent) for r in self.pl.records if r.sig in ("REFR", "ACHR"))
        self.assertTrue(all(by_cell[c] > 5 for c in cells.values()), by_cell)
        flags = {r.editor_id: r.first("DATA")[0] for r in self.pl.records if r.sig == "CELL"}
        self.assertEqual(flags, {"ForgeTestArena": 0x01, "ForgeTestStreet": 0x81, "ForgeTestOpen": 0x81})

    def test_doors_link_both_ways(self):
        refs = {r.form_id: r for r in self.pl.records if r.sig == "REFR"}
        doors = {r.editor_id: r for r in refs.values() if r.first("XTEL")}
        self.assertEqual(set(doors), {"ForgeArenaDoorRef", "ForgeStreetDoorRef"})
        a, s = doors["ForgeArenaDoorRef"], doors["ForgeStreetDoorRef"]
        self.assertEqual(struct.unpack_from("<I", a.first("XTEL"))[0], s.form_id)
        self.assertEqual(struct.unpack_from("<I", s.first("XTEL"))[0], a.form_id)
        self.assertTrue(a.flags & 0x400 and s.flags & 0x400, "load doors are persistent")

    def test_merchant_has_schedule_and_services(self):
        recs = {r.editor_id: r for r in self.pl.records if r.editor_id}
        npc = recs["ForgeStreetMerchant"]
        pk = [struct.unpack("<I", x.data)[0] for x in npc.subrecords() if x.sig == "PKID"]
        self.assertEqual(pk, [recs["ForgeMerchantWorkPkg"].form_id, recs["ForgeMerchantEveningPkg"].form_id])
        aidt = npc.first("AIDT")
        self.assertTrue(struct.unpack_from("<I", aidt, 4)[0] & 0x400)
        work = recs["ForgeMerchantWorkPkg"]
        self.assertEqual(struct.unpack("<bbBbi", work.first("PSDT"))[3:], (8, 12))
        self.assertEqual(struct.unpack("<iIi", work.first("PLDT"))[1], recs["ForgeStreetStallRef"].form_id)
        self.assertEqual(len(npc.first("DATA")), 33)
        self.assertEqual(len(recs["ForgeTestClass"].first("DATA")), 52)

    def test_lints_clean_against_masters(self):
        import modlint
        r = modlint.lint_plugin(self.esp, self.dir, True, None)
        self.assertEqual(r["summary"].get("error", 0), 0, r["issues"])
        self.assertEqual(r["summary"].get("warning", 0), 0, r["issues"])

    def test_cell_keys(self):
        self.assertEqual(testcells.cell_key(None), "arena")
        self.assertEqual(testcells.cell_key("ForgeTestStreet"), "street")
        self.assertEqual(testcells.cell_key("weather"), "open")
        with self.assertRaises(ValueError):
            testcells.cell_key("Imperial City")

    def test_example_firebolt_plugin(self):
        p = examples.firebolt(self.dir / "ForgeExampleFirebolt.esp")
        pl = tp.load(p)
        spel = [r for r in pl.records if r.sig == "SPEL"][0]
        self.assertEqual(spel.editor_id, "ForgeExampleFireboltSpell")
        efit = spel.first("EFIT")
        self.assertEqual(struct.unpack("<4sIIIIi", efit), (b"FIDG", 25, 0, 0, 2, -1))
        import modlint
        self.assertEqual(modlint.lint_plugin(p, self.dir, True, None)["summary"].get("error", 0), 0)


class KitTests(unittest.TestCase):
    def test_kit_meshes_build_and_parse(self):
        try:
            import numpy  # noqa: F401
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("assetkit needs numpy + Pillow (tools/requirements-assetkit.txt)")
        from assetkit import nif as N
        d = Path(tempfile.mkdtemp(prefix="kit-"))
        files = testcells.build_kit(d)
        nifs = [f for f in files if f.suffix == ".nif"]
        self.assertEqual(len(nifs), len(testcells.KIT))
        for f in nifs:
            n = N.read(f.read_bytes()) if hasattr(N, "read") else None
            self.assertTrue(f.stat().st_size > 500)
            if n is not None:
                self.assertEqual(N.write(n), f.read_bytes(), f"{f.name} round-trips")
        self.assertTrue((d / "textures" / "forge" / "testcells" / "stone.dds").is_file())


if __name__ == "__main__":
    unittest.main()
