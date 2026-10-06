# Handoff 30: forge's own script compiler against vanilla (`forge script-check`)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Priority:** short run, about 2 minutes. No exports, no game, no CS.
**Goal:** confirm on the PC what the cloud measured on the uploaded corpus.
- Forge's compiler turns the source text of the vanilla scripts back into **byte-identical** compiled data for **99.86%** of them: 10,705 of 10,720.
- The other 15 are explained (stale data, the `PlayerRef` alias, one raw FormID). See `docs/forge-script-compiler-plan.md` §3d.

## 0. Rules

- Read-only on the GOG copy.
- Don't launch the game or the CS.
- The log (`check_log.txt`) is git-ignored. **Never commit or push it**, or any other output.
- If something fails, report it; don't edit code or tests.

## 1. What's new

| What | Where |
|---|---|
| The compiler | `tools/forge/script/compiler.py` |
| `forge script-check <corpus|plugin>` | `tools/forge/script/check.py` |

`script-check` compiles each script's source and compares the bytes with the vanilla SCDA. It pins two things to the original, because they carry editing history the source can't show:
- the reference-list order;
- the variable indices.

It reports separately whether forge's own ordering rule gives the same list.

## 2. Steps

1. Update the branch:
   ```
   git checkout forge/phase3-plugin
   git pull
   ```
   Report `git log --oneline -1`.
2. Run the check on the corpus, from the repo root:
   ```
   forge script-check forge-script-corpus.jsonl.gz > check_log.txt 2>&1
   ```
3. Run it again, straight from Oblivion.esm (read-only):
   ```
   forge script-check "C:\Users\Shadow\Desktop\Games\Oblivion\Data\Oblivion.esm" >> check_log.txt 2>&1
   ```
   Expect 9,646 scripts, with the same failures as the Oblivion.esm part of the corpus run.
4. Run the unit tests:
   ```
   python -m unittest discover -s tools\forge\tests -t tools
   ```
   Expect 109 tests, OK, 6 skipped or fewer.
5. Run `git status --short`. Nothing may show up.

## 2b. If something goes wrong

| What you see | What to do / send |
|---|---|
| The corpus run isn't `10705/10720` | Its whole report: failures by kind with examples. |
| A `crash:` failure kind | The kind, its examples, and the traceback if one was printed. |
| The Oblivion.esm run differs from the corpus run by more than the DLC scripts | Both summary blocks. |
| Unit tests fail | Test names and tracebacks. |

## 3. Report back to Yuri (for the cloud session)

- The `git log` line.
- From `check_log.txt`, for both runs:
  - the first 4 lines: scripts compiled, `SCDA byte-identical`, `RESULT`, and the reference-list line;
  - the whole `failures by kind` block.
- The unit test summary line.
- The `git status --short` output.
