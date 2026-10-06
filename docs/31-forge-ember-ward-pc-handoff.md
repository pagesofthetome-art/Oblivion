# Handoff 31: build a spell whose script forge compiled itself (`ak-ember-ward`)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Priority:** short run, about 2 minutes. No game, no CS, nothing deployed.
**Goal:** prove the PC builds the first forge spec with a script:
- `scripts:` in a spec now compile with forge's own compiler into a SCPT record, attached to a spell.
- The PC build must produce **exactly the cloud's bytes**.

## 0. Rules

- Build only into the default `forge-builds\` folder (git-ignored).
- **Don't** copy the plugin into either Data folder, Vortex or a profile. The in-game test is phase 3c, later.
- Read-only on the GOG copy (lint reads its masters).
- Commit nothing. If `specs\ak-ember-ward.ids.json` changes, report it; don't commit.
- If something fails, report it; don't edit code, tests or the spec.

## 1. What's new

| What | Where |
|---|---|
| `scripts:` entries in `kind: plugin` specs | see `tools/forge/README.md`, "Scripts in a spec" |
| The acceptance spec | `specs/ak-ember-ward.yaml`, with its FormID map `specs/ak-ember-ward.ids.json` |

The spec's spell is **Ember Ward**, a lesser power with a script effect. For 30 s it prints "Ember pulse N" every 3 s, and nothing else.
- The cloud built it with the command table from your corpus: sha256 `9de0ace3855499f56bea3db1e5bafb490240259e66685c8cfcf7d39d1688a63b`.
- Your build uses `vanilla_commands.jsonl` in the repo root (export from handoff 28), the same table, so the bytes must match.

## 2. Steps

1. Update the branch:
   ```
   git checkout forge/phase3-plugin
   git pull
   ```
   Report `git log --oneline -1`.
2. Check and build the spec:
   ```
   forge spec check specs\ak-ember-ward.yaml
   forge build specs\ak-ember-ward.yaml
   ```
   Expect `OK`, the sha256 above, records `SCPT AKEmberWardScript` and `SPEL AKEmberWard`, round-trip 0 mismatches, and lint with no errors.
3. Read it back with three commands. `<plugin>` is the path the build printed:
   ```
   forge script-decode <plugin> --show AKEmberWardScript --source
   forge dump <plugin> AKEmberWard
   forge lint <plugin>
   ```
   In the `forge dump` output, look for the SCIT script effect pointing at `AKEmberWardScript`.
4. Run the unit tests:
   ```
   python -m unittest discover -s tools\forge\tests -t tools
   ```
   Expect 110 tests, OK (6 skipped or fewer).
5. Run `git status --short`. Nothing may show up.

## 2b. If something goes wrong

| What you see | What to do / send |
|---|---|
| `compiling scripts needs Oblivion.exe's command and block tables` | Check that `vanilla_commands.jsonl` is in the repo root. If it isn't, run `forge kb export-commands --exe "C:\Users\Shadow\Desktop\Games\Oblivion\Oblivion.exe"` (as in handoff 28) and build again. |
| A different sha256 | The build output, plus `forge script-decode <plugin> --show AKEmberWardScript`. |
| Lint errors | The lint output. |
| Unit tests fail | Test names and tracebacks. |

## 3. Report back to Yuri (for the cloud session)

- The `git log` line.
- The `spec check` output, and the whole `forge build` output.
- The `script-decode` listing, the SPEL part of `forge dump`, and the lint summary.
- The unit test summary line.
- The `git status --short` output.
