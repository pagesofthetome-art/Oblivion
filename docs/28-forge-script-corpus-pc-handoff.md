# Handoff 28: script corpus export + decompiler survey (compiler steps S0 + S1)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Approved by Yuri (2026-10-06):**
- Export the vanilla script corpus. Yuri uploads it to the cloud session for local iteration. **Never commit it.**
- The research mods' OBSE scripts may be used for validation later (step S7), **on the PC only**: pass rates may go back to the cloud; script text and bytes stay on the PC. **This handoff doesn't touch them.**

**Goal:** export every vanilla script into one git-ignored bundle, run the new decompiler over it, and report how much of the bytecode it already understands.
**Background:** `docs/forge-script-compiler-plan.md`, steps S0 and S1.
**No game or CS launch.** Read-only on the GOG copy.

## 0. Rules

- GOG copy only (`C:\Users\Shadow\Desktop\Games\Oblivion`), read-only.
- Don't launch the game or the CS. Don't drive the mouse or keyboard.
- The outputs (`vanilla_commands.jsonl`, `forge-script-corpus.jsonl.gz`, `script_log.txt`) are Bethesda-derived and git-ignored. **Never commit or push them.**
  - Check with `git status --short`: none of them may show up.
  - **Never `git add -f` them.**
- Don't open, copy or touch research-mod files.
- If something fails, report it. Don't edit code or tests to make it pass.

## 1. Steps

1. Update the branch:
   ```
   git checkout forge/phase3-plugin
   git pull
   ```
   Report `git log --oneline -1`.
2. Run the batch file from the repo root:
   ```
   "scripts\kb\Export script corpus.bat"
   ```
   It writes `script_log.txt` and does four things:
   1. Re-runs `export-commands`, which now also reads the **block-type table** (GameMode, OnActivate, …) from `Oblivion.exe`.
   2. Runs `forge kb export-scripts`: every SCPT script and every quest-stage/dialogue result script, the EditorIDs needed to resolve names, and the command tables. All of it goes into `forge-script-corpus.jsonl.gz`.
   3. Runs `forge script-decode` over the corpus: the survey.
   4. Runs the unit tests.
3. Run `git status --short`. None of the three outputs may be listed.
4. Pick two scripts from the survey and show them decoded, **with source**. Use the first `e.g.` example under "failures by kind"; if there are no failures, use `GSQuestScript` or any SCPT:
   ```
   forge script-decode forge-script-corpus.jsonl.gz --show <EDID> --source
   ```
   **Second pick:** take one INFO result script from the same log. A formid works too: `--show 0001234A`.
5. **For Yuri:** the file to upload is `forge-script-corpus.jsonl.gz` in the repo root. Report its size.
   - It is a local, uncommitted file; uploading it to the cloud session is Yuri's approved step.
   - If it's over 30 MB, say so: we can split it by plugin.

## 2. If something goes wrong

| What you see | What to do / send |
|---|---|
| `export-commands` says `block_types: 0` | Report it and continue. The survey still runs, and block names show as numbers. |
| `export-scripts` fails or reports 0 scripts | The traceback and the per-plugin counts. Stop. |
| The survey takes more than 10 minutes or runs out of memory | The time and the last log lines. Stop. |
| Unit tests fail | The failing test names and their tracebacks. |
| Any output shows up in `git status` | Don't commit. Report the `.gitignore` lines and the status output. |

## 3. Report back to Yuri (for the cloud session)

- The `git log` line.
- From `script_log.txt`:
  - the `export-commands` counts (script / console / **block_types**);
  - the `export-scripts` summary (scripts, forms, commands, per-plugin SCPT/QUST/INFO counts);
  - the corpus size;
  - **the whole survey section**: pass rate, failures by kind with examples, unknown opcodes, jump fields, SCHR checks, first statement, block types, and the 5 failing listings;
  - the unit test summary line.
- The two `--show … --source` outputs from step 4.
- The `git status --short` output.
- Then Yuri uploads `forge-script-corpus.jsonl.gz` to the cloud session.
