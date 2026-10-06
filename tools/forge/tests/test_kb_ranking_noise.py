"""Regression: the cloud questions must still pass once a large vanilla index is loaded.

On the PC (58,845 vanilla forms), form rows outranked functions for "how do I..." questions
(q03, q13). This re-runs the unchanged CloudQuestions against a DB holding ~59k synthetic
forms whose EditorIDs reuse the questions' own words: a harsher mix than the real data.
"""

from __future__ import annotations

import json
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))

import forge.tests.test_kb_queries as tkq  # noqa: E402
from forge.kb import build as kbuild, query as q  # noqa: E402

WORDS = ("Key Press Read Weather Thunderstorm Storm Force Rain Clear Projectile Owner Source Portal Door "
         "Marker Return Position World Dimension Pocket Persuasion Tutorial Silent Voice Plugin Master Form "
         "Spell Gold Sword Daedric Arrow Find Near Player Scan Mod Change Elys Hang Reloaded").split()
SIGS = "WEAP ARMO MISC KEYM BOOK NPC_ CREA SPEL DOOR STAT ACTI CONT QUST DIAL WTHR LIGH".split()


def noisy_index(path: Path, n: int = 58845) -> None:
    rnd = random.Random(1)
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(n):
            edid = "".join(rnd.choice(WORDS) for _ in range(rnd.randint(2, 4))) + str(i % 100)
            full = " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(1, 3)))
            fh.write(json.dumps({"plugin": "Oblivion.esm", "owner": "Oblivion.esm", "objid": f"{i + 0x1000:06X}",
                                 "formid": f"00{i + 0x1000:06X}", "sig": rnd.choice(SIGS), "edid": edid,
                                 "full": full, "override": False, "deleted": False}) + "\n")
        fh.write(json.dumps({"plugin": "Oblivion.esm", "owner": "Oblivion.esm", "objid": "038EF1",
                             "formid": "00038EF1", "sig": "WTHR", "edid": "Thunderstorm", "full": "",
                             "override": False, "deleted": False}) + "\n")


class NoisyCloudQuestions(tkq.CloudQuestions):
    """Same 14 questions, same assertions, ~59k forms in the index."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="forge-kb-noise-"))
        idx = cls.tmp / "vanilla_index.jsonl"
        noisy_index(idx)
        cls.db = cls.tmp / "kb.sqlite"
        kbuild.build(cls.db, idx, None)
        cls._saved = tkq.DB
        tkq.DB = cls.db

    @classmethod
    def tearDownClass(cls):
        tkq.DB = cls._saved
        q.close_all()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_named_form_still_leads(self):
        r = q.search("How do I force a Thunderstorm? 00038EF1", 3, None, self.db)
        self.assertEqual(r[0]["key"], "Oblivion.esm:00038EF1")

    def test_plain_word_does_not_make_a_form_lookup(self):
        r = q.search("How do I force a thunderstorm?", 10, None, self.db)
        self.assertEqual(r[0]["key"], "ForceWeather")
        self.assertLessEqual(sum(x["kind"] == "form" for x in r), 3)


if __name__ == "__main__":
    unittest.main()
