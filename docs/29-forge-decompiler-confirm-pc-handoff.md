# Handoff 29: confirm the 100% script decode on the PC (step S1 sign-off)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Priority:** short run, about 2 minutes. No exports, no game, no CS.
**Goal:** confirm on the PC what the cloud measured on the uploaded corpus.
- The decompiler decodes **100%** of the vanilla scripts.
- It gives the same result read straight from the plugins, without the corpus in between.

## 0. Rules

- Read-only on the GOG copy.
- Don't launch the game or the CS.
- The log (`decode_log.txt`) is git-ignored. **Never commit or push it**, or the corpus, or any other output.
- If something fails, report it; don't edit code or tests.

## 1. What changed (from your handoff 28 report)

| Fix | What it covers |
|---|---|
| Message, MessageBox and EssentialDeathReload layouts | the 902 "leftover param bytes" |
| `Z` + u16 (a reference used as a value) and `~` (unary minus) in expressions | the 216 "bad expression byte" |
| Quest and reference variables now print by name | `SE43.DogAttackPC`, not `SE43.s3` |
| `/Oblivion` added to `.gitignore` | the junction you reported |
| New survey lines | which commands the decoder found but the source text doesn't mention (should be **none**), and which parameter types occur |

Two things your report suggested were right:
- The SCHR variable count is a high-water mark: 432 scripts equal the highest index; 171 are stale and higher.
- Expressions turned out to be postfix.

## 2. Steps

1. Update the branch:
   ```
   git checkout forge/phase3-plugin
   git pull
   ```
   Report `git log --oneline -1`.
2. Run the survey from the corpus, from the repo root:
   ```
   forge script-decode forge-script-corpus.jsonl.gz > decode_log.txt 2>&1
   ```
3. Run it again, straight from the plugins. These read the GOG `Data` files directly (read-only), so they also prove the plugin path matches:
   ```
   forge script-decode "C:\Users\Shadow\Desktop\Games\Oblivion\Data\Oblivion.esm" >> decode_log.txt 2>&1
   forge script-decode "C:\Users\Shadow\Desktop\Games\Oblivion\Data\Knights.esp" --commands vanilla_commands.jsonl >> decode_log.txt 2>&1
   ```
4. Run the unit tests:
   ```
   python -m unittest discover -s tools\forge\tests -t tools
   ```
5. Show two scripts:
   ```
   forge script-decode forge-script-corpus.jsonl.gz --show SE12AnimatingDoorSCRIPT --source
   ```
   Report only the first 20 lines of each part (source and decoded).
   ```
   forge script-decode forge-script-corpus.jsonl.gz --show 00072DAB
   ```
6. Run `git status --short`. Nothing new may show up; the `Oblivion/` junction should be gone from the list.

## 2b. If something goes wrong

| What you see | What to do / send |
|---|---|
| Any run is below 100% | The `failures by kind` block with its examples, and the first `--fail 3` listing (`forge script-decode <same input> --fail 3`). |
| `commands decoded but absent from the source text` isn't `none` | The line and its examples. |
| The Oblivion.esm run differs from the corpus run in its counts | Both summary blocks. |
| Unit tests fail | Test names and tracebacks. |

## 3. Report back to Yuri (for the cloud session)

- The `git log` line.
- From `decode_log.txt`, for each of the three runs, the first 4 lines: scripts, commands loaded, `decoded with no leftover bytes`, `RESULT`.
- From the corpus run, also: `commands decoded but absent…`, `SCHR checks`, and the `jump fields` block.
- The unit test summary line.
- Step 5: the two `--show` outputs (first 20 lines each).
- The `git status --short` output.
