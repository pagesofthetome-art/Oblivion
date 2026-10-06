"""Phase 3a: kind: plugin builds records from the spec.

Byte references come from the PC recon of vanilla records (handoff 19): only the short
struct values needed to prove the layouts, not whole records.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

from forge import cli, records as R  # noqa: E402
from forge.tests import fixtures  # noqa: E402
import tes4_plugin as tp  # noqa: E402

# vanilla, from the PC recon of Oblivion.esm (GOG 1.2.0.416)
FLASH_BOLT_SPIT = "000000002b0000000100000000000000"           # Spell, cost 43, Apprentice, flags 0
FLASH_BOLT_EFIT = "464944471400000000000000000000000200000008000000"   # FIDG 20, target, AV 8
PET_STAY_SPIT = "030000001400000000000000" "6bcdcdcd"   # Lesser Power, cost 20; flags 0x6b + CS garbage
PET_STAY_SCIT = "c06e0400" "03000000" "00000000" "00" "1b5600"


def forge(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class CodecTests(unittest.TestCase):
    def test_vanilla_structs_round_trip_with_garbage_padding(self):
        for sub, hx in (("SPIT", FLASH_BOLT_SPIT), ("EFIT", FLASH_BOLT_EFIT), ("SPIT", PET_STAY_SPIT),
                        ("SCIT", PET_STAY_SCIT)):
            data = bytes.fromhex(hx)
            d = R.decode("SPEL", sub, data)
            self.assertEqual(d["layout"], "struct", sub)
            self.assertNotIn("tail", d)
            self.assertEqual(R.encode("SPEL", d), data, sub)

    def test_decoded_names(self):
        efit = R.decode("SPEL", "EFIT", bytes.fromhex(FLASH_BOLT_EFIT))["fields"]
        self.assertEqual((efit["Magic Effect Name"], efit["Magnitude"], efit["Type"], efit["Actor Value"]),
                         ("FIDG", 20, "Target", "Health"))
        spit = R.decode("SPEL", "SPIT", bytes.fromhex(PET_STAY_SPIT))["fields"]
        self.assertEqual(spit["Type"], "Lesser Power")       # 3; the recon guessed "ability" (4)
        self.assertEqual(spit["unused@13"], "cdcdcd")
        scit = R.decode("SPEL", "SCIT", bytes.fromhex(PET_STAY_SCIT))["fields"]
        self.assertEqual((scit["Script effect"], scit["Magic school"]), ("00046EC0", "Illusion"))

    def test_encode_from_names_matches_vanilla(self):
        efit = R.encode("SPEL", {"sig": "EFIT", "fields": {"Magic Effect Name": "FIDG", "Magnitude": 20,
                                                            "Type": "Target", "Actor Value": "Health"}})
        self.assertEqual(efit.hex(), FLASH_BOLT_EFIT)
        spit = R.encode("SPEL", {"sig": "SPIT", "fields": {"Type": "Spell", "Cost": 43, "Level": "Apprentice",
                                                            "Flags": []}})
        self.assertEqual(spit.hex(), FLASH_BOLT_SPIT)

    def test_arrays_decode_every_element(self):
        # MGEF ESCE is a list of 4-char counter-effect codes (PC handoff 20: RALY = DSPL DEMO)
        for hx, codes in (("4453504c44454d4f", ["DSPL", "DEMO"]),
                          ("414248454452484544474845", ["ABHE", "DRHE", "DGHE"])):
            d = R.decode("MGEF", "ESCE", bytes.fromhex(hx))
            self.assertEqual(d["layout"], "array")
            self.assertEqual([i["Counter Effect Code"] for i in d["items"]], codes)
            self.assertEqual(R.encode("MGEF", d).hex(), hx)
        # a length that isn't a whole number of elements stays raw (and still round-trips)
        d = R.decode("MGEF", "ESCE", b"ABC")
        self.assertEqual(d["layout"], "raw")
        self.assertEqual(R.encode("MGEF", d), b"ABC")

    def test_bad_values_are_clear_errors(self):
        with self.assertRaisesRegex(R.CodecError, "not one of"):
            R.encode("SPEL", {"sig": "SPIT", "fields": {"Level": "Grandmaster"}})
        with self.assertRaisesRegex(R.CodecError, "unknown field"):
            R.encode("SPEL", {"sig": "SPIT", "fields": {"Price": 3}})


class PluginBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forge-plug-"))
        self.fx = fixtures.make(self.tmp / "fx")

    def tearDown(self):
        from forge.kb import query as q
        q.close_all()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def spec(self, records, **extra) -> Path:
        s = {"forge_spec": 1, "name": "test-plugin", "kind": "plugin", "intent": "test spells",
             "output": {"plugin": "AKTest.esp", "dir": "out"}, "ids": "AKTest.ids.json",
             "dependencies": {"masters": ["Oblivion.esm"]}, "records": records, "scripts": [],
             "lint": {"data": str(self.fx["installed"])}}
        s.update(extra)
        p = self.tmp / "spec.json"
        p.write_text(json.dumps(s), encoding="utf-8")
        return p

    FLASH = {"sig": "SPEL", "edid": "AKFlashBoltCopy", "FULL": "Flash Bolt",
             "SPIT": {"Type": "Spell", "Cost": 43, "Level": "Apprentice", "Flags": []},
             "effects": [{"effect": "FIDG", "magnitude": 20, "range": "Target"}]}

    def build(self, spec):
        code, out, err = forge("build", str(spec), "--json")
        self.assertEqual(code, 0, out + err)
        return json.loads(out)

    def test_flash_bolt_copy_matches_vanilla_layout(self):
        res = self.build(self.spec([self.FLASH]))
        plugin = Path(res["plugin"])
        hdr = tp.read_header(plugin)
        self.assertEqual(hdr.masters, ["Oblivion.esm"])
        self.assertEqual(hdr.next_object_id, 0x801)
        (p, r), = list(tp.iter_records(plugin))
        self.assertEqual((r.sig, r.form_id, r.editor_id), ("SPEL", 0x01000800, "AKFlashBoltCopy"))
        subs = r.subrecords()
        self.assertEqual([s.sig for s in subs], ["EDID", "FULL", "SPIT", "EFID", "EFIT"])   # vanilla order
        self.assertEqual(subs[2].data.hex(), FLASH_BOLT_SPIT)
        self.assertEqual(subs[4].data.hex(), FLASH_BOLT_EFIT)

    def test_deterministic_and_ids_append_only(self):
        spec = self.spec([self.FLASH])
        first = Path(self.build(spec)["plugin"]).read_bytes()
        self.assertEqual(Path(self.build(spec)["plugin"]).read_bytes(), first)
        # add a record in front: the existing one keeps 000800
        second = dict(self.FLASH, edid="AKSecond")
        res = self.build(self.spec([second, self.FLASH]))
        ids = {r["edid"]: r["objid"] for r in res["records"]}
        self.assertEqual(ids, {"AKFlashBoltCopy": "000800", "AKSecond": "000801"})
        # a retired ID is never handed out again
        idsf = self.tmp / "AKTest.ids.json"
        m = json.loads(idsf.read_text())
        m["retired"]["AKOld"] = m["ids"].pop("AKSecond")
        idsf.write_text(json.dumps(m))
        code, _, err = forge("build", str(self.spec([dict(self.FLASH, edid="AKOld")])))
        self.assertEqual(code, 1)
        self.assertIn("never reused", err)

    def test_script_effect_reference_by_formid(self):
        rec = {"sig": "SPEL", "edid": "AKPetStay", "FULL": "Stay",
               "SPIT": {"Type": "Lesser Power", "Cost": 20, "Level": "Novice", "Flags": []},
               "effects": [{"effect": "SEFF", "range": "Self",
                            "script": {"script": "Oblivion.esm:046EC0", "school": "Illusion", "name": "Script Effect"}}]}
        res = self.build(self.spec([rec]))
        (p, r), = list(tp.iter_records(Path(res["plugin"])))
        subs = r.subrecords()
        self.assertEqual([s.sig for s in subs], ["EDID", "FULL", "SPIT", "EFID", "EFIT", "SCIT", "FULL"])
        scit = subs[5].data
        self.assertEqual(p.global_key(int.from_bytes(scit[:4], "little")), ("oblivion.esm", 0x046EC0))
        self.assertEqual(scit[4:8].hex(), "03000000")        # Illusion, as in vanilla TestPetStay
        self.assertEqual(tp.zstring(subs[6].data), "Script Effect")

    def test_array_of_formids_from_the_spec(self):
        # NPC_ ENAM (eyes) is an array of FormIDs: references resolve per element
        rec = {"sig": "NPC_", "edid": "AKEyesTest", "ENAM": ["Oblivion.esm:0027C1", "Oblivion.esm:0027C2"]}
        res = self.build(self.spec([rec]))
        (p, r), = list(tp.iter_records(Path(res["plugin"])))
        enam = r.first("ENAM")
        self.assertEqual(len(enam), 8)
        self.assertEqual([p.global_key(int.from_bytes(enam[i:i + 4], "little")) for i in (0, 4)],
                         [("oblivion.esm", 0x27C1), ("oblivion.esm", 0x27C2)])

    def test_errors_are_clear(self):
        code, _, err = forge("build", str(self.spec([{"sig": "SPEL", "edid": "AKX", "SPIT": {"Level": "Godlike"}}])))
        self.assertEqual(code, 1)
        self.assertIn("not one of", err)
        code, _, err = forge("build", str(self.spec([{"sig": "SPEL", "edid": "AKX", "XXXX": "1"}])))
        self.assertEqual(code, 1)
        self.assertIn("no subrecord XXXX", err)
        code, _, err = forge("build", str(self.spec([{"sig": "SPEL", "edid": "AKX", "effects": [
            {"effect": "SEFF", "script": {"script": "MyUndefinedScript"}}]}])))
        self.assertEqual(code, 1)
        self.assertIn("can't resolve", err)

    def test_scripts_wait_for_phase_3b(self):
        code, out, _ = forge("build", str(self.spec([self.FLASH], scripts=[{"name": "X"}])))
        self.assertEqual(code, 1)
        self.assertIn("phase 3b", out)

    def test_layout_check_on_built_plugin(self):
        res = self.build(self.spec([self.FLASH]))
        code, out, _ = forge("layout-check", res["plugin"], "--json")
        r = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(r["pass"])
        self.assertEqual((r["records"], r["identical"]), (1, 5))

    def test_repo_acceptance_spec_builds(self):
        spec = TOOLS.parent / "specs" / "ak-searing-bolt.yaml"
        ids_before = (TOOLS.parent / "specs" / "ak-searing-bolt.ids.json").read_bytes()
        code, out, err = forge("build", str(spec), "--set", f"GOG_DATA={self.fx['installed']}",
                               "--out", str(self.tmp / "sb"), "--json")
        self.assertEqual(code, 0, out + err)
        res = json.loads(out)
        self.assertEqual(res["records"], [{"sig": "SPEL", "edid": "AKSearingBolt", "objid": "000800"}])
        self.assertFalse(res["ids_changed"])
        self.assertEqual((TOOLS.parent / "specs" / "ak-searing-bolt.ids.json").read_bytes(), ids_before)


if __name__ == "__main__":
    unittest.main()
