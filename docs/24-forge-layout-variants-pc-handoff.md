# Handoff 24: layout variants (CLMT TNAM, XLOC, XNAM, LIGH DATA)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Goal:** confirm the full survey PASSes again, with the size-mismatch variants now decoded. **Read-only on the game:** no activation, no INI or `Plugins.txt` changes, no game or CS launch, no merges.

## 1. What changed since handoff 23

Branch **`forge/phase3-plugin`**. Check it out yourself.

- **Handoff 23 result:** every byte identical. One FAIL (CLMT TNAM 1-byte tail). The top raw count dropped from 1.03M to 8,181.
- **Fixes**, all read from xEdit's real definitions, not from memory:
  - **CLMT TNAM:** the 6th byte, `Moons / Phase Length`, sits behind `IfThen(Assigned(aPhaseCallback), …, nil)` in `wbDefinitionsCommon.pas`. The extractor now evaluates `IfThen`.
  - **FACT XNAM:** xEdit picks per game with `IsTES4(<Oblivion>, <later games>)`. For Oblivion the combat-reaction field is `nil`, so XNAM is **8** bytes. Your "8 or 12" note came from the later games' layout.
  - **LIGH DATA (24/32), CTDA (20/24), INFO DATA (2/3):** xEdit marks them `SetOptionalFrom(n)`. A shorter vanilla subrecord now decodes when it ends on a field boundary, and `present: N` re-encodes it the same way.
  - **REFR XLOC (12/16):** a filler union of 0 or 4 bytes, chosen by the subrecord's size.
  - **`forge dump --has SIG`:** only records that contain that subrecord (your suggestion).
- Cloud: 88 tests OK. The Searing Bolt sha256 is unchanged (`95418054…`).

## 2. Steps

Set `GOG=C:\Users\Shadow\Desktop\Games\Oblivion`. Save outputs under `_audit\forge-phase3a\`.

1. **Branch:** `git fetch origin`, `git checkout forge/phase3-plugin`, `git pull`. Report `git log --oneline -1`.
2. **Tests:**
   ```
   cd tools
   python -m unittest discover -s forge/tests -t . > ..\_audit\forge-phase3a\tests5.txt 2>&1
   cd ..
   ```
   Expect `OK`, no skips.
3. **Surveys** (both must PASS):
   ```
   forge layout-check Oblivion.esm --data "%GOG%\Data" --all > _audit\forge-phase3a\layout_all4.txt
   forge layout-check Knights.esp  --data "%GOG%\Data" --all > _audit\forge-phase3a\layout_knights3.txt
   ```
4. **Spot checks**, using the new filter:
   ```
   forge dump Oblivion.esm --data "%GOG%\Data" --sig REFR --has XTEL --limit 1 > _audit\forge-phase3a\dump_xtel.txt
   forge dump Oblivion.esm --data "%GOG%\Data" --sig INFO --has CTDA --limit 1 > _audit\forge-phase3a\dump_ctda.txt
   forge dump Oblivion.esm --data "%GOG%\Data" --sig REFR --has XLOC --limit 1 > _audit\forge-phase3a\dump_xloc.txt
   forge dump Oblivion.esm --data "%GOG%\Data" SEWorldClimate                   > _audit\forge-phase3a\dump_clmt.txt
   ```
5. **KB refresh:** `forge kb build > _audit\forge-phase3a\kb_build3.txt`
6. **Sanity rebuild:** run `forge build specs\ak-searing-bolt.yaml`. Expect OK, the same sha256, and `ids` unchanged.

## 3. If something fails

| What you see | What to send |
|---|---|
| step 3 FAIL | the FAIL rows and every MISMATCH/TAIL example line |
| a traceback | the traceback |
| tests fail | the FAIL/ERROR blocks from `tests5.txt` |
| step 6 sha256 differs | the build output and `forge-builds\ak-searing-bolt\build-log.json` |

**Don't edit** schema files, tests or `layout_overrides.json`. Report instead.

## 4. Rules

As in `docs\PC-AGENT.md`: commit nothing from this run, don't copy the .esp anywhere, no game or CS launch, no branch merges.

## 5. Report back to Yuri (for the cloud session)

- The `git log` line, and the tests summary.
- **Step 3:** both PASS/FAIL lines, plus the "most common undecoded (raw)" list for Oblivion.esm.
- **Step 4:** the decoded XTEL, CTDA, XLOC and CLMT TNAM fields (short).
- Step 5: the counts line. Step 6: status and sha256.
