# Handoff 32: first in-game test, Ember Ward in the Arena (`forge playtest`, results from the save)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Approved by Yuri (2026-10-06):**
- Track E (the playtest harness) is merged into `forge/phase3-plugin`.
- Ember Ward is the first in-game test, in the Imperial City Arena (`ICArena`).
- Results come from the result save's globals only: **no `PrintToFile`, no `scof`**.

**Goal:** run the forge-compiled Ember Ward power in the real game. These checks must pass:
- the player has it;
- the self-cast effect is active;
- its script counts pulses into the `AKEmberPulses` global;
- the effect ends after 30 s.

The verdict comes from the result save.
**Who does what:** you prepare and start the run. **Yuri** presses Continue and plays. **Yuri quits the game himself.**

## 0. Playtest rules (Track E, unchanged)

- **Forge never closes the game; Yuri quits** with the pad after the last beep. Never send keys to the game yourself.
- **Restore after exit:**
  - Forge swaps the test `Plugins.txt`/`Oblivion.ini` in under a restore journal, and restores both once the game has exited.
  - If anything looks wrong: `forge playtest restore`, then `forge playtest status`.
- **Never touch Rebirth+:**
  - no writes to the Steam copy, `%APPDATA%\Vortex`, or the real `Plugins.txt`/`Oblivion.ini` by hand;
  - no registry edits.

  Forge itself refuses Steam or Vortex folders.
- **The game copy:** only the GOG copy (`C:\Users\Shadow\Desktop\Games\Oblivion`) runs the test.
- **Nothing else running:** do nothing while Oblivion, the launcher, obse_loader or the CS runs.
- **Report, don't patch:** report problems. Don't edit `tools/playtest`, `tools/forge`, the spec or tests, and don't install anything.
- **Commit nothing.** Run folders stay in `forge-builds\` (git-ignored).

## 1. What's new

| What | Details |
|---|---|
| Ember Ward spec | `specs/ak-ember-ward.yaml` now also builds a global `AKEmberPulses`. The script adds 1 to it every pulse, next to the on-screen "Ember pulse N". New sha256: `7ec8a70511172c253007a55c0d5543bfe732cb5cf55410c138a36de383847b71`. The FormID map gains `AKEmberPulses = 000802`. |
| Test plan | In the spec (`test_plan`): `cell: arena`, `results: save`. The steps are listed below. |
| `--results save` / `results: save` | The batches contain **no `PrintToFile` lines**. The values come only from the `ForgePlaytestResult` save's globals (sentinel-guarded), read after Yuri quits. Any log file is ignored. |
| Checks without a calling reference | A check with `ref: none` runs without a reference: `GetGlobalValue AKEmberPulses`. |

The test steps:
1. Add the power.
2. Check `HasSpell` = 1, and `AKEmberPulses` = 0.
3. Self-cast: `player.cast AKEmberWard player`.
4. After 2 s: `IsSpellTarget` = 1.
5. After 15 s: pulses ≥ 3.
6. After 40 s: `IsSpellTarget` = 0, and pulses ≥ 8.

**Fixed after the first attempt (dry run: `need two non-essential beggars … found 0`):**
- **No actors when the plan doesn't use them.** The beggar lookup now runs only when a step names TestTarget or TestCaster. Ember Ward names neither, so no beggars are looked up, moved or prepared. The log says `test actors: none (the plan doesn't use TestTarget/TestCaster)`.
- **The beggar query.** Oblivion's beggars have the class **Pauper**, not "Beggar", so the old query found none.
  - It now matches class Pauper or Beggar, or an NPC EditorID starting with `Beggar`.
  - The vanilla corpus has 25 beggar NPCs, all with persistent EditorID refs (e.g. `ImusTheDullRef`, `PennilessOlvusRef`).
  - City beggars come before the quest ones.
  - `forge playtest cells` shows the pick. It's not needed for this run.

## 2. Steps

1. **Update and check.**
   ```
   git checkout forge/phase3-plugin
   git pull
   git log --oneline -1
   ```
   Confirm `tools\playtest\` exists.
2. **Pre-checks.**
   - Make sure no `Oblivion.exe`, `OblivionLauncher.exe`, `obse_loader.exe` or `TESConstructionSet.exe` is running (`tasklist`).
   - Run `forge playtest status`. It must say the test profile is off. If a journal is open, run `forge playtest restore` and check again.
3. **Run the tests.**
   ```
   cd tools
   python -m unittest discover -s forge/tests -t .
   python -m unittest discover -s playtest/tests -t .
   cd ..
   ```
   Expect **110 OK** (6 skipped or fewer) and **96 OK**.
4. **Build.**
   ```
   forge build specs\ak-ember-ward.yaml
   ```
   Expect OK, sha256 `7ec8a705…7b71`, records `SCPT AKEmberWardScript`, `GLOB AKEmberPulses` and `SPEL AKEmberWard`, round-trip 0 mismatches, and lint with no errors.
5. **Check the test save.**
   - It must exist: `%USERPROFILE%\Documents\My Games\Oblivion\Saves\ForgePlaytest\ForgePlaytestBase.ess` (or wherever `forge playtest status` / run 7 put it).
   - If it's missing, stop and ask Yuri to run `forge playtest make-save` first (README, "Quick boot" step 4).
6. **Dry run** (no launch):
   ```
   forge playtest specs\ak-ember-ward.yaml --cell arena --results save --dry-run
   ```
   - Expect `DRY-RUN`, identical restore hashes, and `forge playtest status` off afterwards.
   - In the dry run's `playtest_manifest.json`, `findstr /i "printtofile scof"` must find **nothing**.
7. **Tell Yuri, then start the real run:**
   ```
   forge playtest specs\ak-ember-ward.yaml --cell arena --results save
   ```
   Tell Yuri, in short steps:
   - Close Oblivion first.
   - At the **beeps** at the main menu, press **Cross on CONTINUE**.
   - In the Arena you'll see "Ember Ward: warmth settles into your limbs.", then "Ember pulse 1", "2", … every 3 s, and after 30 s "The ember ward fades after 10 pulses."
   - **For about 45 s after loading, don't pause, open menus or wait/sleep.** The test waits in unpaused game time.
   - At the last beep ("checks done… quit when ready"), play on if you like, then **quit with the pad**.
   - Forge restores everything after the game has exited.
8. **After the game has exited:**
   ```
   forge test
   forge playtest status
   ```
   The status must be off.
9. **Collect** the new run folder (`forge-builds\playtest\runs\<time>\`, whole) into `forge-builds\playtest\handoff\ember1\`.

## 2b. If something goes wrong

| What you see | What to do / send |
|---|---|
| The build sha differs | The build output, plus `forge script-decode <plugin> --show AKEmberWardScript`. Don't run the game. |
| The dry run's manifest contains PrintToFile | Stop; send the manifest's first chunk. |
| Boot doesn't reach the Arena | The screenshots `shots\*`, `boot-trace.jsonl` (last 20 lines) and `result.json`. Yuri quits; forge restores. |
| `HasSpell` 1 but `IsSpellTarget` 0 | Read the console screenshots after `fpt1`/`fpt2`: type out any error line (e.g. about `cast`). |
| Pulses stay 0 while `IsSpellTarget` is 1 | The script effect isn't running. Say what Yuri saw on screen (messages or none). |
| `FROZE` | `Controller\freeze_report.txt`. Yuri closes the game; forge doesn't. |
| A restore not identical, or status still on | `forge playtest restore`, then `forge playtest status`; send both outputs. |

## 3. Report back to Yuri (for the cloud session)

Write it as a file: `forge-builds\playtest\handoff\HANDOFF-to-cloud-ember1.md`.
- The `git log` line, the test summaries, and the build output (sha256).
- The `test actors:` line from the run output (expected: none).
- The dry run's verdict and the `findstr` result.
- From the real run:
  - `forge test` (paste);
  - from `result.json`: `verdict`, `boot_seconds`, `log_source`, `save_values`, `restore_check`;
  - every check with its value.
- What Yuri saw on screen: the messages, the pulse count at the end, and any error.
- The console screenshots after each batch: type out any error line.
- `forge playtest status` after the run.
- Anything that was changed by hand (should be nothing).
