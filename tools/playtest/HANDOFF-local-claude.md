# Handoff to the local Claude: run 5 of the TES4Forge playtest on Yuri's PC

You are the Claude on Yuri's Windows PC. The cloud Claude owns `tools/playtest`. Your job:
1. Pull the latest commit of `claude/serene-maxwell-03d2fh` (PR https://github.com/pagesofthetome-art/Oblivion/pull/2).
2. Write Yuri **one `.bat`**.
3. After he runs it, write your reply **as a file**: `forge-builds\playtest\handoff\HANDOFF-to-cloud-run5.md`.

Speak to Yuri in plain, short steps. He plays with a PS5 pad.

## Yuri's rule, now built in: forge NEVER closes the game
- There is no auto-quit anywhere: not in make-save, the test, or acceptance. The `--quit` option is gone.
- Forge does its part, then **beeps** and shows "done, quit when ready", both in the console window and
  in game (a `message` line in the last batch). Then it waits.
- Yuri quits with the pad. Forge waits for the Oblivion process to exit, **then** restores Plugins.txt,
  Oblivion.ini, NorthernUI.ini and the DPI flag.
  - This removes run 4's "Access denied". Restore writes are also retried for about 10 s.
  - If forge is interrupted while the game runs, it does **not** restore under the game: the guardian
    does it after the game exits.
- **Freezes:** forge beeps and reports `FROZE`, but doesn't close the game (Yuri does).
  `--kill-on-freeze` exists as an opt-in, but don't use it.
- **`acceptance.bat`** runs `make-save` only if there is no test save. If no save was made, it
  **stops** and doesn't run the test. Each step starts only after the game from the previous step
  has closed.

## Fixed from your run 4 report
1. **make-save no longer gives up after the second console command.**
   - The location check, the save and the quit note are now **one batch**, `bat fptsave`. It runs
     right after `coc ICArena` has loaded.
   - Opening the console is tried up to three times (run 4's press after the load got lost). Typing
     happens only once the console is confirmed open.
2. **Old test saves are no longer deleted first.**
   - The new save is written as `ForgePlaytestNew`. After Yuri quits, it replaces `ForgePlaytestBase`
     only if the log says the player was in ICArena.
   - If the log says he was somewhere else, the new save is deleted and the old one is untouched.
   - If there is **no log at all** but the save was written, the save is kept with a warning.
     `forge_test.log` has never been found on the PC, so where scof writes is still unconfirmed.
3. **No typing in the main menu any more.** Run 4's menu 1038 was the **Load menu**: the "coc ICArena"
   letters went into the main menu.
   - Without a test save, forge now stops **before launching** and says to run make-save.
   - With one, it beeps for Continue.
4. **Restore under a running or closing game.** Fixed, see above.
5. **Ilvia / the street.**
   - Not needed for spell or mod tests. The default arena test only brings the training dummy and the
     spell caster.
   - Ilvia only comes along with `--cell street`, for mods that touch towns or merchants.
   - **Drop the street hands-on.**

## Hard rules (unchanged)
- Never write to the Steam copy or `%APPDATA%\Vortex`.
- Never hand-edit the real Plugins.txt or Oblivion.ini, or the registry.
- Do nothing while Oblivion or the CS runs.
- Never send keys to the game.
- If something looks wrong: `forge playtest restore`, then `forge playtest status`.
- Report problems; don't patch `tools/playtest`.

## Tell Yuri before he starts
- Close Oblivion. Forge will **never** close it for you: **you quit every time, with the pad, after the beep.**
- **Step 1 (only if there's no test save, and there isn't one now):** the game opens at the main menu.
  1. Choose NEW and skip the intro.
  2. On the character screen, type any name, choose DONE and confirm.
  3. Forge takes you to the Arena and saves.
  4. When it **beeps**, quit the game.
- **Step 2 (the test):** the game opens again.
  1. At **three beeps**, press Cross on CONTINUE.
  2. Forge runs the checks (the training dummy gets hit by a fire bolt).
  3. When it **beeps** again, play as long as you like, then quit with the pad.

## The .bat to write
1. **Pre-checks.**
   - Nothing running.
   - `forge playtest status`.
   - Tests: `cd tools && python -m unittest discover -s playtest/tests -t .` should give **81 OK**,
     and `forge/tests` **24 OK**.
2. **Registry `Layers`** (HKCU and HKLM), read only: before and after. They must be identical.
3. **`call tools\playtest\acceptance.bat --no-pause`.** It does make-save if needed, then the test.
   `acceptance.txt` has everything.
4. **If any `result.json` says there is no forge_test.log, or the make-save result has a "warning":**
   search the **whole** disk once with `where /r C:\ forge_test.log`, plus
   `where /r %USERPROFILE% forge_test.log`. Report every hit with its timestamp.
5. **Collect** into `forge-builds\playtest\handoff\run5\`:
   - every new run folder, whole;
   - `acceptance.txt`;
   - the registry outputs;
   - a listing of the `Saves\ForgePlaytest\` folder;
   - `<GOG>\obse.log`, `guardian.log`, and the last 200 lines of `controller_log`.

## Reply format (a .md file)
```
# Track E PC results run 5 (<date>)
Commit tested: <git rev-parse HEAD>
## Pre-checks
## make-save
result JSON (made? warning? probe lines); did the batch run (screenshots); did Yuri quit himself?
save folder listing after
## Test run
verdict / boot_seconds / checks passed; events; error (exact); forge test report
forge_test.log (first 100 lines) or where it was found
## Restore
restore_check, registry before/after identical, any Access denied?
## Screenshots: one line each (typed-* and console-try* especially)
## Boot trace (around any failure)
## What Yuri saw (did the in-game "quit when ready" message show? did the dummy take damage?)
## Anything you changed
## Questions / blockers
```
