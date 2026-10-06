# Handoff 20: TES4Forge phase 3a on the PC (layout proof + first built spell)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Goal:** prove the new record codec against real vanilla records, and build the first spec-made spell. **Read-only on the game:** no plugin is activated, no INI or `Plugins.txt` changes, no game or CS launch.

## 1. What changed since handoff 19

Branch **`forge/phase3-plugin`**.

- **Your recon found an extractor bug.** EFIT/SCIT had no layout (`wbStructSK` sort-key list). It's fixed, and enums/flags are now named.
  - FYI: TestPetStay's SPIT type 3 is **Lesser Power**, not Ability (xEdit enum: 0 Spell, 1 Disease, 2 Power, 3 Lesser Power, 4 Ability, 5 Poison).
- **New `kind: plugin` builder.** It reads `specs/ak-searing-bolt.yaml` (FIDG 30, 5 ft, target, Apprentice) and writes the plugin.
  - In the cloud, its SPIT/EFIT bytes match vanilla Flash Bolt's layout exactly.
  - Its sha256 is pinned in the spec: `9541805498eb24ae876ecdf675e87792443195b1e5159ad6d7117197a1bc474b`.
- **New `forge layout-check`.** It decodes every record of a type and re-encodes it. PASS means identical bytes and nothing left undecoded.
- **CS bridge token path fixed.** New `tools/gamepaths.py` finds the game beside a repo clone: `<repo>\..\Oblivion`.
- **Cloud tests:** 82 run, 0 failures, 6 skipped (the KB's PC-only questions).

## 2. Steps

Set `GOG=C:\Users\Shadow\Desktop\Games\Oblivion`. Save outputs under `_audit\forge-phase3a\` (not committed).

1. **Pull:** `git fetch origin`, then `git checkout forge/phase3-plugin`, then `git pull`. Report the `git log --oneline -1` line.
2. **Tests:**
   ```
   cd tools
   python -m unittest discover -s forge/tests -t . -v > ..\_audit\forge-phase3a\tests.txt 2>&1
   ```
   Expect `OK`. The 6 KB PC questions should now **pass**, not skip, because your `vanilla_index.jsonl` / `forge-kb.sqlite` exist. If they skip, run step 3 first, then rerun.
3. **Rebuild the KB.** The record schemas changed, and the old exports are reused:
   ```
   forge kb build > _audit\forge-phase3a\kb_build.txt
   ```
4. **Layout proof** (the main result):
   ```
   forge layout-check Oblivion.esm --data "%GOG%\Data" --sig SPEL --sig MGEF  > _audit\forge-phase3a\layout_spel_mgef.txt
   forge layout-check Oblivion.esm --data "%GOG%\Data" --sig ENCH --sig ALCH --sig INGR --sig SGST > _audit\forge-phase3a\layout_effects.txt
   ```
   Each prints PASS or FAIL, counts, and up to 10 examples of MISMATCH/TAIL.
5. **Build the spell:**
   ```
   forge build specs\ak-searing-bolt.yaml > _audit\forge-phase3a\build.txt
   ```
   - Expect `OK`, sha256 `95418054…` (the spec's `expect.sha256` enforces it), lint with no errors against the real GOG Data.
   - The plugin lands in `forge-builds\ak-searing-bolt\` (git-ignored), **not** in Data.
6. **Side-by-side dump:**
   ```
   forge dump forge-builds\ak-searing-bolt\AKSearingBolt.esp AKSearingBolt  > _audit\forge-phase3a\dump_ours.txt
   forge dump Oblivion.esm --data "%GOG%\Data" StandardFireDamageTarget2Apprentice > _audit\forge-phase3a\dump_flashbolt.txt
   ```
7. **CS bridge path check:** run `forge cs health`.
   - Expected now: either a health answer, or a *connection* error if the bridge task isn't running.
   - It must **not** be `FileNotFoundError ...Oblivion-repo\Oblivion\.cs_bridge_token`.
   - Don't start the bridge. Never print or copy the token.

## 3. If something fails

| What you see | What to send |
|---|---|
| `layout-check ... FAIL` | The whole output file. The MISMATCH/TAIL lines name the record and show the decoded struct. **Don't change the schema files.** |
| build `FAIL sha256 ... != expected` | `build.txt`, `dump_ours.txt` and the `forge-builds\ak-searing-bolt\build-log.json` `tool_versions.git` block. |
| build lint errors | `build.txt` |
| tests fail | `tests.txt` (at least the FAIL/ERROR blocks) |
| `forge cs health` still looks in the repo | the exact error |

## 4. Rules

- Commit nothing from this run. The only committed IDs file is `specs\ak-searing-bolt.ids.json`, and the build should report `ids` unchanged. If the build says it wrote **new** IDs, report that: it shouldn't happen.
- Don't copy `AKSearingBolt.esp` into any Data folder, and don't activate it. In-game testing is phase 3c and needs the test-profile decision first.
- Everything else as in `docs\PC-AGENT.md`.

## 5. Report back to Yuri (for the cloud session)

- The `git log` line.
- The `tests.txt` summary (Ran N, OK/FAILED, skips).
- The PASS/FAIL line and counts from both layout files.
- The build status and sha256.
- The two dumps (short).
- The `forge cs health` result.
- Anything that failed, quoted exactly.
