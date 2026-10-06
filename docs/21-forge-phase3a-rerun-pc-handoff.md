# Handoff 21: phase 3a rerun (array fix) + full layout survey

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Goal:** confirm the ESCE fix, then survey every record type in Oblivion.esm so the cloud knows which layouts still need work. **Read-only on the game:** no activation, no INI or `Plugins.txt` changes, no game or CS launch.

## 1. What changed since handoff 20

Branch **`forge/phase3-plugin`**.

- **ESCE fix.**
  - Your report found that MGEF `ESCE` is a list of 4-char codes; forge decoded only the first.
  - The cause was general: every xEdit *array* subrecord (21 of them, e.g. ESCE, ENAM, XCLR, WLST, RDWT) was handled the same way.
  - Arrays now decode as element lists and encode back. The Searing Bolt sha256 is unchanged (`95418054…`).
- **New `forge layout-check --all`:** a per-record-type table for a whole plugin.
- **Dump labels:** SPIT `Type`/`Level` as u8 + 3 unused bytes is how xEdit defines them. The labels stay; the bytes were always right.
- **Your 3c decision (A) is recorded.** It uses the playtest session's swap/restore. Merging that branch is waiting on Yuri, so there's no in-game step in this handoff.

## 2. Steps

Set `GOG=C:\Users\Shadow\Desktop\Games\Oblivion`. Save outputs under `_audit\forge-phase3a\` (overwriting is fine).

1. **Pull:** `git fetch origin`, `git checkout forge/phase3-plugin`, `git pull`. Report `git log --oneline -1`.
2. **Tests:**
   ```
   cd tools
   python -m unittest discover -s forge/tests -t . > ..\_audit\forge-phase3a\tests2.txt 2>&1
   cd ..
   ```
   Expect `OK`, no skips.
3. **SPEL+MGEF again** (must PASS now):
   ```
   forge layout-check Oblivion.esm --data "%GOG%\Data" --sig SPEL --sig MGEF > _audit\forge-phase3a\layout_spel_mgef2.txt
   ```
4. **Full survey** (informational; FAIL rows are expected and wanted):
   ```
   forge layout-check Oblivion.esm --data "%GOG%\Data" --all > _audit\forge-phase3a\layout_all.txt
   ```
   - It can take a few minutes: every record of Oblivion.esm is decoded and re-encoded.
   - If it runs longer than about 15 minutes, stop it and report how far it got.
5. **Sanity rebuild:** `forge build specs\ak-searing-bolt.yaml`. Expect OK, same sha256, `ids` unchanged.

## 3. If something fails

| What you see | What to send |
|---|---|
| step 3 FAIL | the whole `layout_spel_mgef2.txt` |
| step 4 crashes (traceback) | the traceback, and the last record type printed if any |
| tests fail | the FAIL/ERROR blocks from `tests2.txt` |
| step 5 sha256 differs | `build.txt`-style output and `forge-builds\ak-searing-bolt\build-log.json` |

**Don't edit** schema files, tests or `layout_overrides.json`. Report instead.

## 4. Rules

As in `docs\PC-AGENT.md`: commit nothing from this run, don't copy the .esp anywhere, no game or CS launch.

## 5. Report back to Yuri (for the cloud session)

- The `git log` line, and the tests summary.
- The step 3 PASS/FAIL line and counts.
- **Step 4:** the whole table, plus the MISMATCH/TAIL example lines. They're short decoded structs, which is fine to paste.
- The step 5 status and sha256.
