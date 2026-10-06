"""forge dump decodes subrecords with the KB schemas."""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

from forge import dump  # noqa: E402
from forge.tests import fixtures  # noqa: E402


class DumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="forge-dump-"))
        cls.fx = fixtures.make(cls.tmp / "fx")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_by_editor_id_decodes_struct_and_formids(self):
        (r,) = dump.dump(self.fx["installed"] / "UOP.esp", "TestNPC")
        self.assertEqual((r["sig"], r["key"]), ("NPC_", "oblivion.esm:000100"))
        acbs = next(s for s in r["subrecords"] if s["sig"] == "ACBS")
        self.assertIn({"name": "Level (offset)", "offset": 10, "type": "itS16", "value": 10}, acbs["fields"])
        splo = next(s for s in r["subrecords"] if s["sig"] == "SPLO")
        self.assertEqual(splo["fields"][0]["value"], "oblivion.esm:000500")

    def test_by_formid_and_sig(self):
        (r,) = dump.dump(self.fx["installed"] / "Oblivion.esm", "00000200")
        self.assertEqual(r["edid"], "TestQuest")
        rows = dump.dump(self.fx["installed"] / "Oblivion.esm", sig="SPEL", limit=2)
        self.assertEqual([x["sig"] for x in rows], ["SPEL", "SPEL"])

    def test_ctda_shows_operator_and_full_tail(self):
        # vanilla-shaped 24-byte CTDA (PC handoff 24): Type 160 = Less Than Or Equal To, 4 trailing bytes
        import struct as st
        from types import SimpleNamespace
        data = bytes([160, 0xCD, 0xCD, 0xCD]) + st.pack("<f", 5.0) + st.pack("<H", 225) + b"\xcd\xcd" + \
            b"\0" * 8 + b"\xde\xad\xbe\xef"
        fake_plugin = SimpleNamespace(global_key=lambda v: ("oblivion.esm", v & 0xFFFFFF))
        from forge import records as R
        rows = dump.decode(fake_plugin, "INFO", SimpleNamespace(sig="CTDA", data=data), R.sub_schema("INFO", "CTDA"))
        vals = {r["name"]: r["value"] for r in rows}
        self.assertTrue(vals["Type"].startswith("Less Than Or Equal To"))
        self.assertEqual(vals["Function"], 225)
        self.assertEqual([v for k, v in vals.items() if k.startswith("unused")][-1], "deadbeef")

    def test_cli(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = dump.main(["Oblivion.esm", "TestCell", "--data", str(self.fx["installed"])])
        self.assertEqual(code, 0)
        self.assertIn("CELL oblivion.esm:000400", out.getvalue())


if __name__ == "__main__":
    unittest.main()
