# Handoff: TES4Forge phase 2, PC run 2 (confirm 20/20)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude in `C:\Users\Shadow\Desktop\Games`.
**Goal:** rerun the knowledge-store batch after the ranking fix, then report back.

## 1. What changed since PC run 1 (18/20)

Branch **`forge/phase2-kb`**, commit **`cacd48e`** or later. PR: <https://github.com/pagesofthetome-art/Oblivion/pull/1>

- **Ranking fix for q03 and q13.**
  - Vanilla forms now have their own search index (`fts_forms`).
  - They come first only when the question names one exactly: a CamelCase or digit EditorID, or a FormID. Otherwise they take at most a third of the results, after functions and techniques.
  - The 20 questions are unchanged.
- **New test `test_kb_ranking_noise.py`.** It reruns the 14 cloud questions against ~59k synthetic forms. It failed on the old ranking and passes now.
- **`export-vanilla` summary fixed.** It no longer prints `Oblivion.esm: 0`. The empty SI stub was overwriting the count.
- **`Build forge KB.bat` takes the game folder as an argument.** Without one, it checks `<repo>\Oblivion`, then `<repo>\..\Oblivion`, then `%USERPROFILE%\Desktop\Games\Oblivion`. It stops with a message if none holds `Data\Oblivion.esm`.

## 2. Steps

1. Pull the branch: `git fetch origin` then `git checkout forge/phase2-kb` then `git pull`. Confirm with `git log --oneline -1`: it should show `cacd48e` or newer.
2. Run, passing the GOG folder explicitly:
   ```
   "scripts\kb\Build forge KB.bat" "C:\Users\Shadow\Desktop\Games\Oblivion"
   ```
   - It **reads only** that folder's `Data\` and `Oblivion.exe`.
   - It **writes only** git-ignored files in the repo root: `vanilla_index.jsonl`, `vanilla_commands.jsonl`, `forge-kb.sqlite`, `kb_log.txt`.
   - It makes no Vortex changes, no game-file edits, and doesn't launch the game.
3. Check `kb_log.txt`:
   - **Export summary:** `Oblivion.esm` now shows a real count (most of the 58,845), and `DLCShiveringIsles.esp: 0` is expected.
   - **Commands:** `script_commands: 369`, `console_commands: 131`.
   - **Tests:** the 22 tests in `test_kb_queries` (20 questions + 2 integrity checks) all pass with **no skips**. The 3 exporter tests and 16 noise-regression tests also pass. The last line is `TESTS OK`.

## 3. If something fails

- **Any question fails:** quote the assertion message exactly. For q03/q13, also run these and send the output:
  - `forge kb query "What OBSE function reads a key press, and what does its parameter mean?" --limit 5`
  - `forge kb query "How do I force a thunderstorm?" --limit 5`
- **Do not** edit tests, `kb/data/curated.json` or the ranking code to force a pass. Report the failure instead.
- **The batch can't find the game:** pass the folder as shown in step 2.

## 4. Rules (unchanged)

- Never commit `vanilla_index.jsonl`, `vanilla_commands.jsonl`, `forge-kb.sqlite` or `kb_log.txt`.
- Research mods stay out of Vortex and both Data folders.
- The GOG copy is read-only for this task.

## 5. Report back to Yuri (for the cloud session)

- Pass count: x/20, plus the totals of the other test groups.
- The export summary lines and the `forge kb build` counts table.
- Any failure, quoted exactly, with the two `forge kb query` outputs if q03/q13 are involved.

On 20/20, the cloud session will tick "PC run 2" in `docs\forge-phase-checklist.md`, mark phase 2 done, and prepare phase 3 (records and scripts from the spec).
