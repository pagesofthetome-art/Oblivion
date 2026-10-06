# Handoff 22: phase 3a, full layout survey must PASS + what's still raw

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Goal:** confirm the XSED fix makes `layout-check --all` PASS on every record type of Oblivion.esm, and collect the list of subrecords that still round-trip only as raw bytes. **Read-only on the game:** no activation, no INI or `Plugins.txt` changes, no game or CS launch.

> **Branch note:** helper 2 (playtest) left the clone on `claude/serene-maxwell-03d2fh`. Check out `forge/phase3-plugin` yourself (step 1) before running anything. Don't merge branches.

## 1. What changed since handoff 21

Branch **`forge/phase3-plugin`**.

- **Handoff 21 result:** SPEL+MGEF PASS. The `--all` survey (63 types, ~2.9M REFR subrecords) had 0 mismatches. The only gap was 573 REFR `XSED` tails.
- **Fix:** xEdit writes `XSED` as `Seed u8` + `wbUnused(0)`, and `wbUnused(0)` means "padding to the end of the subrecord", 1 or 4 bytes in vanilla. A trailing zero-size unused field now takes whatever bytes remain. Your three examples (`a5`, `a5ec0400`, `83060f00`) round-trip in the cloud tests.
- **`--all` lists raw subrecords:** it now prints the 25 most common subrecords that still decode as **raw**. Raw ones round-trip byte for byte, but their fields aren't named yet. That list sets the next layout work.
- The Searing Bolt sha256 is unchanged (`95418054…`).

## 2. Steps

Set `GOG=C:\Users\Shadow\Desktop\Games\Oblivion`. Save outputs under `_audit\forge-phase3a\` (overwriting is fine).

1. **Branch:** `git fetch origin`, `git checkout forge/phase3-plugin`, `git pull`. Report `git log --oneline -1` (expect `Phase 3a: open-ended padding…` or newer).
2. **Tests:**
   ```
   cd tools
   python -m unittest discover -s forge/tests -t . > ..\_audit\forge-phase3a\tests3.txt 2>&1
   cd ..
   ```
   Expect `OK`, no skips.
3. **Full survey** (must PASS now; about 2 minutes):
   ```
   forge layout-check Oblivion.esm --data "%GOG%\Data" --all > _audit\forge-phase3a\layout_all2.txt
   ```
4. **The DLC** (informational):
   ```
   forge layout-check Knights.esp --data "%GOG%\Data" --all > _audit\forge-phase3a\layout_knights.txt
   ```
5. **Sanity rebuild:** run `forge build specs\ak-searing-bolt.yaml`. Expect OK, the same sha256, and `ids` unchanged.

## 3. If something fails

| What you see | What to send |
|---|---|
| step 3 FAIL | the FAIL rows of the table plus every MISMATCH/TAIL example line |
| a traceback | the traceback |
| tests fail | the FAIL/ERROR blocks from `tests3.txt` |
| step 5 sha256 differs | the build output and `forge-builds\ak-searing-bolt\build-log.json` |

**Don't edit** schema files, tests or `layout_overrides.json`. Report instead.

## 4. Rules

As in `docs\PC-AGENT.md`: commit nothing from this run, don't copy the .esp anywhere, no game or CS launch, no branch merges.

## 5. Report back to Yuri (for the cloud session)

- The `git log` line, and the tests summary.
- **Step 3:** the PASS/FAIL line, and the whole "most common undecoded (raw) subrecords" list (25 lines). The full table isn't needed if it PASSes.
- **Step 4:** the PASS/FAIL line and any FAIL rows.
- Step 5: status and sha256.
