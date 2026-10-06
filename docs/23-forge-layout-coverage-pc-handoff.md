# Handoff 23: layout coverage (most "raw" subrecords now have names)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Goal:** confirm `layout-check --all` still PASSes now that most former "raw" subrecords decode into named fields, and measure what's left. **Read-only on the game:** no activation, no INI or `Plugins.txt` changes, no game or CS launch, no merges.

## 1. What changed since handoff 22

Branch **`forge/phase3-plugin`**. Check it out yourself; the playtest helper may leave the clone on another branch.

- **Handoff 22 result:** `--all` PASS on Oblivion.esm (63 types) and Knights.esp (37). Your raw list showed what to fix next.
- **Why those were raw:** xEdit defines them through helpers the extractor couldn't follow. It now handles:
  - case-insensitive Pascal names (`wbCNTOS` defined, `wbCNTOs` used);
  - list variables (`wbConditionMembers`);
  - helper functions in `wbDefinitionsCommon.pas` (`wbVec3PosRot`, `wbNextSpeaker`, `wbLandHeights/Normals/Colors/Layers`, `wbXLOD`), with their arguments and defaults bound;
  - fixed-count arrays inside structs;
  - unsized trailing byte arrays.
- **Overrides:**
  - CTDA parameter sizes: xEdit builds them at runtime; patchlib already reads them at offsets 12/16.
  - The `wbTexturedModel` Oblivion branch: MODL string, MODB float, MODT model info.
- **Unions** are kept as sized raw bytes inside the struct.
- **NaN safety:** a float whose bytes wouldn't survive conversion (signaling NaN) is kept as hex, so garbage in float fields still round-trips.
- **Now named:** REFR DATA (position/rotation), XTEL (door + position), XLOD; INFO CTDA/DATA; PACK CTDA/PLDT; NPC_/CONT CNTO; LVLI LVLO; SCPT SLSD; NPC_ SNAM; STAT MODL/MODB; LAND VHGT/VNML/VCLR/ATXT/VTXT/BTXT.
- **Still raw:** PGRD PGRR (variable connections per point) and PACK PKDT (4 or 8 bytes).
- Cloud: 87 tests OK. The Searing Bolt sha256 is unchanged (`95418054…`).

## 2. Steps

Set `GOG=C:\Users\Shadow\Desktop\Games\Oblivion`. Save outputs under `_audit\forge-phase3a\`.

1. **Branch:** `git fetch origin`, `git checkout forge/phase3-plugin`, `git pull`. Report `git log --oneline -1`.
2. **Tests:**
   ```
   cd tools
   python -m unittest discover -s forge/tests -t . > ..\_audit\forge-phase3a\tests4.txt 2>&1
   cd ..
   ```
   Expect `OK`, no skips.
3. **Full survey** (must PASS; the raw column should drop a lot):
   ```
   forge layout-check Oblivion.esm --data "%GOG%\Data" --all > _audit\forge-phase3a\layout_all3.txt
   forge layout-check Knights.esp  --data "%GOG%\Data" --all > _audit\forge-phase3a\layout_knights2.txt
   ```
4. **Spot check:** decode one placed door and one dialogue line:
   ```
   forge dump Oblivion.esm --data "%GOG%\Data" --sig REFR --match Door --limit 1 > _audit\forge-phase3a\dump_refr.txt
   forge dump Oblivion.esm --data "%GOG%\Data" --sig INFO --limit 1          > _audit\forge-phase3a\dump_info.txt
   ```
   The `--match` filter works on EditorIDs and names. If `dump_refr.txt` says "no matching record", use `--sig REFR --limit 3` instead.
5. **KB refresh** (the schemas changed): `forge kb build > _audit\forge-phase3a\kb_build2.txt`
6. **Sanity rebuild:** run `forge build specs\ak-searing-bolt.yaml`. Expect OK, the same sha256, and `ids` unchanged.

## 3. If something fails

| What you see | What to send |
|---|---|
| step 3 FAIL | the FAIL rows and every MISMATCH/TAIL example line (likely suspects: MGEF DATA, PACK PLDT, LAND V*) |
| a traceback | the traceback |
| tests fail | the FAIL/ERROR blocks from `tests4.txt` |
| step 6 sha256 differs | the build output and `forge-builds\ak-searing-bolt\build-log.json` |

**Don't edit** schema files, tests or `layout_overrides.json`. Report instead.

## 4. Rules

As in `docs\PC-AGENT.md`: commit nothing from this run, don't copy the .esp anywhere, no game or CS launch, no branch merges.

## 5. Report back to Yuri (for the cloud session)

- The `git log` line, and the tests summary.
- **Step 3:** both PASS/FAIL lines, plus the "most common undecoded (raw)" list for Oblivion.esm (25 lines).
- **Step 4:** the decoded REFR (DATA and any XTEL fields) and the INFO's CTDA/DATA lines.
- Step 5: the counts line. Step 6: status and sha256.
