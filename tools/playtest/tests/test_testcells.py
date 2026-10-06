"""ForgeTestCells.esp: test actors only (no geometry), deterministic, lints clean, looks copied."""

from __future__ import annotations

import struct
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from playtest.tests import base  # noqa: F401
from playtest import examples, testcells, vanilla
from playtest.tests import fixtures

import tes4_plugin as tp


class TestActorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="testcells-"))
        cls.esm = fixtures.fake_esm(cls.dir / "Oblivion.esm")
        cls.esp, _ = testcells.write(cls.dir, cls.esm)
        cls.pl = tp.load(cls.esp)
        cls.recs = {r.editor_id: r for r in cls.pl.records if r.editor_id}

    def test_deterministic(self):
        a, _ = testcells.build_plugin(self.esm)
        b, _ = testcells.build_plugin(self.esm)
        self.assertEqual(a, b)
        self.assertEqual(a, self.esp.read_bytes())

    def test_actors_only_no_geometry(self):
        self.assertEqual(self.pl.errors, [])
        c = Counter(r.sig for r in self.pl.records)
        self.assertEqual(c["CELL"], 1)
        self.assertEqual(c["ACHR"], 5)
        self.assertEqual(c["NPC_"], 4)
        for sig in ("STAT", "DOOR", "MISC", "REFR", "LIGH"):
            self.assertEqual(c[sig], 0, f"no new {sig}: the playtest uses real vanilla content")
        self.assertFalse(any(b"forge\\testcells" in r.data for r in self.pl.records), "no custom meshes")

    def test_looks_copied_from_a_vanilla_npc(self):
        npc = self.recs["ForgeStreetMerchant"]
        donor = {s.sig: s.data for s in next(r for _, r in tp.iter_records(self.esm, {"NPC_"})
                                             if r.form_id == fixtures.DONOR).subrecords()}
        for sig in ("HNAM", "ENAM", "FGGS", "FGGA", "FGTS", "HCLR"):
            self.assertEqual(npc.first(sig), donor[sig], sig)
        cnto = [struct.unpack_from("<I", x.data)[0] for x in npc.subrecords() if x.sig == "CNTO"]
        self.assertIn(fixtures.SHIRT, cnto, "dressed in the donor's clothes")

    def test_plain_without_esm(self):
        data, lay = testcells.build_plugin(None)
        self.assertIsNone(lay["appearance"])
        self.assertNotIn(b"FGGS", data)

    def test_merchant_schedule_and_services(self):
        npc = self.recs["ForgeStreetMerchant"]
        pk = [struct.unpack("<I", x.data)[0] for x in npc.subrecords() if x.sig == "PKID"]
        self.assertEqual(pk, [self.recs["ForgeMerchantWorkPkg"].form_id, self.recs["ForgeMerchantEveningPkg"].form_id])
        self.assertTrue(struct.unpack_from("<I", npc.first("AIDT"), 4)[0] & 0x400)
        work = self.recs["ForgeMerchantWorkPkg"]
        self.assertEqual(struct.unpack("<bbBbi", work.first("PSDT"))[3:], (8, 12))
        self.assertEqual(struct.unpack("<iIi", work.first("PLDT"))[0], 2, "near current location")
        self.assertEqual(len(npc.first("DATA")), 33)

    def test_lints_clean_against_masters(self):
        import modlint
        r = modlint.lint_plugin(self.esp, self.dir, True, None)
        self.assertEqual(r["summary"].get("error", 0), 0, r["issues"])
        self.assertEqual(r["summary"].get("warning", 0), 0, r["issues"])

    def test_example_firebolt_plugin(self):
        p = examples.firebolt(self.dir / "ForgeExampleFirebolt.esp")
        spel = [r for _, r in tp.iter_records(p, {"SPEL"})][0]
        self.assertEqual(spel.editor_id, "ForgeExampleFireboltSpell")
        self.assertEqual(struct.unpack("<4sIIIIi", spel.first("EFIT")), (b"FIDG", 25, 0, 0, 2, -1))


class VanillaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="vanilla-"))
        cls.esm = fixtures.fake_esm(cls.dir / "Oblivion.esm")
        cls.idx = vanilla.load_index(cls.esm, cls.dir / "idx.json")

    def test_defaults(self):
        a = vanilla.resolve("arena", self.idx)
        self.assertEqual((a.boot, a.cell_edid), ("coc ICArena", "ICArena"),
                         "pinned to ICArena, not the busier 'Cann, Arena' ruin (run 3)")
        self.assertIsNone(a.setpos, "coc's own spot on the floor, not behind the gate (run 5)")
        s = vanilla.resolve("street", self.idx)
        self.assertEqual((s.boot, s.world_edid), ("cow ICMarketDistrict 10 6", "ICMarketDistrict"))
        self.assertEqual(s.setpos[:2], [41000.0, 25100.0], "outside a shop door")
        o = vanilla.resolve("weather", self.idx)
        self.assertEqual(o.boot, "cow Tamriel 5 -3")

    def test_arena_fallback_never_picks_the_ruin(self):
        idx = dict(self.idx, interiors=[c for c in self.idx["interiors"] if c["edid"] != "ICArena"])
        with self.assertRaises(vanilla.VanillaError):
            vanilla.resolve("arena", idx)                  # ICArenaBloodworks is a side room; never the ruin

    def test_test_actors_are_real_non_essential_beggars(self):
        a = vanilla.test_actors(self.idx)
        self.assertEqual(a["target"]["edid"], "FixtureBeggarAnnaRef", "no NPC script first")
        self.assertEqual(a["caster"]["edid"], "FixtureBeggarBoRef")
        picked = {x["edid"] for x in a.values()}
        self.assertNotIn("FixtureBeggarEssRef", picked, "essential NPCs are never used")
        self.assertNotIn("FixtureGuardCidRef", picked, "beggars only")

    def test_custom_and_errors(self):
        self.assertEqual(vanilla.resolve("ICArenaBloodworks", self.idx).boot, "coc ICArenaBloodworks")
        self.assertEqual(vanilla.resolve("marker:Weye", self.idx).moveto, "0000C001")
        with self.assertRaises(vanilla.VanillaError):
            vanilla.resolve("NoSuchCell", self.idx)
        with self.assertRaises(vanilla.VanillaError):
            vanilla.resolve("marker:Nowhere", self.idx)

    def test_cache_and_search(self):
        again = vanilla.load_index(self.esm, self.dir / "idx.json")
        self.assertEqual(again["interiors"], self.idx["interiors"])
        hits = vanilla.search("weye", self.idx)
        self.assertTrue(hits and "marker:Weye" in hits[0])


if __name__ == "__main__":
    unittest.main()
