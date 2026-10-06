# Handoff: TES4Forge phase 2 → run the knowledge-store step on the PC

**From:** the Claude Code cloud session that built phase 2 (2026-10-06). It has no game files and can't see the PC.
**To:** the local Claude working in `C:\Users\Shadow\Desktop\Games`.
**Goal:** run one batch file, check the result, and send `kb_log.txt` back to Yuri for the cloud session.

## 1. What was built

- PR: <https://github.com/pagesofthetome-art/Oblivion/pull/1>
- Branch: **`forge/phase2-kb`**, based on `claude/jolly-pasteur-hiurwl` (phase 1).

It adds `forge-kb.sqlite` and the `forge kb` command group. See the "Knowledge store" section of `tools\forge\README.md`. The cloud built and tested everything except the parts that need Bethesda files:

| Test group | Cloud result |
|---|---|
| 14 cloud questions | 14/14 pass |
| 6 PC questions | skipped: need the exports below |
| Integrity checks + exporter tests | pass |

The 6 PC questions:
- q15: FormID of `WeapDaedricLongsword`
- q16: which WTHR records exist
- q17: FormID `00000007` → Player
- q18: `Gold001` → `0000000F`
- q19: `SEWorld` is in Oblivion.esm
- q20: vanilla `PositionWorld` parameters, read from Oblivion.exe

## 2. What to do

1. Get the branch into `C:\Users\Shadow\Desktop\Games`: `git fetch` then `git checkout forge/phase2-kb`. If that folder isn't a git checkout, copy in the files the PR changed. Don't overwrite local files that are newer without asking Yuri.
2. Run **`scripts\kb\Build forge KB.bat`** (double-click it, or run it from cmd at the repo root). It:
   - **Reads only** the clean GOG copy: `Oblivion\Data` (Oblivion.esm + official DLC) and `Oblivion\Oblivion.exe`.
   - **Writes only** git-ignored files in the repo root: `vanilla_index.jsonl`, `vanilla_commands.jsonl`, `forge-kb.sqlite`, `kb_log.txt`.
   - Steps: export-vanilla → export-commands → `forge kb build` → tests (`test_kb_queries` + `test_kb_export`).
3. Open `kb_log.txt`. The last test line should read `TESTS OK`, with "Ran 22 tests" for `test_kb_queries` (20 questions + 2 integrity checks) plus the 3 exporter tests, and **no skips**.

The step makes no Vortex changes, no game-file edits, and doesn't launch the game.

## 3. If something fails

| What you see | Meaning / what to do |
|---|---|
| `export-vanilla FAILED`, or `Oblivion.esm: missing` | `Oblivion\Data` isn't where the batch expects it. Fix the `DATA=` line in the batch file, or run `forge kb export-vanilla --data "<real Data path>"` by hand. |
| `export-commands failed` / `script command table not found` | The exe parser couldn't find the command table. This is **not fatal**: q20 is skipped and everything else works. Report the exact message and the exe's size and version (right-click → Properties → Details). Don't try other exes. |
| q16 fails (`clear` / `thunderstorm` not found) | The cloud guessed those EditorIDs. The test prints the real WTHR list; send it. **Don't edit the test to make it pass.** |
| q15 / q17 / q18 / q19 fail | Send the assertion message. It shows what the DB actually returned. |
| `no such module: fts5` | Python's SQLite lacks FTS5. Report the Python version (`python --version`). |
| `ModuleNotFoundError: forge` | Run the batch from the repo, not a copy. It sets `PYTHONPATH` to `tools`. |

## 4. Rules

- **Never commit** `vanilla_index.jsonl`, `vanilla_commands.jsonl`, `forge-kb.sqlite` or `kb_log.txt`. They're Bethesda-derived or local, and `.gitignore` already covers them. Only the log's text goes back to the cloud session.
- Don't edit tests or `kb/data/curated.json` to force a pass. Report the failure instead.
- Research mods stay out of Vortex and both Data folders (unchanged rule).

## 5. Report back to Yuri (for the cloud session)

- The whole of `kb_log.txt`. If it's long, send at least these sections: export counts per plugin, the `forge kb build` counts table, and the test summary.
- The pass count for the PC questions (x/6) and the total (x/20).
- Any failure message, quoted exactly.

**Optional extra checks**, if they're quick:
- `forge kb form WeapDaedricLongsword`
- `forge kb forms --sig WTHR`
- `forge kb func PositionWorld`

After a clean run, the cloud session will tick the PC box in `docs\forge-phase-checklist.md` and move on to phase 2b (engine notes).
