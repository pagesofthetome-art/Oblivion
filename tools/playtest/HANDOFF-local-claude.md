# Handoff to the local Claude: run 4 of the TES4Forge playtest on Yuri's PC

You are the Claude on Yuri's Windows PC. The cloud Claude owns `tools/playtest`. Your job:
1. Pull the latest commit of `claude/serene-maxwell-03d2fh` (PR https://github.com/pagesofthetome-art/Oblivion/pull/2).
2. Write Yuri **one `.bat`**.
3. After he runs it, write your reply **as a file**: `forge-builds\playtest\handoff\HANDOFF-to-cloud-run4.md`.

Speak to Yuri in plain, short steps. He plays with a PS5 pad.

## Fixed from your run 3 report (thanks: the DPI and chargen diagnoses were right)
1. **Arena.**
   - Pinned to **`ICArena`** (exact EditorID). The player arrives on the spot where the
     **Bloodworks gate** lets you in.
   - The "busiest cell with Arena in the name" rule is gone, so the ruin `XPCann04` can't be picked
     again.
2. **Test save made before character creation.**
   - `make-save` now waits until the character screen has been **opened and closed**.
   - It then runs `coc ICArena`, and **checks in the log** that the player is really in ICArena
     before saving. If not, it saves nothing and says why.
   - Autosaves and quicksaves in `Saves\ForgePlaytest\` (that folder only) are deleted, so Continue
     always loads the test save.
   - If a run still loads a save with a chargen menu open, it stops with "Run make-save again".
3. **Screen 2/3 visible (DPI scaling).** In the test run, forge now:
   - reads the DPI compatibility flag of the **Steam** `Oblivion.exe` (HKCU, then HKLM
     `...\AppCompatFlags\Layers`);
   - if one is there (e.g. `HIGHDPIAWARE`), sets the same flag on the GOG `Oblivion.exe` **for the
     run only**, journaled and removed afterwards like Plugins.txt, and renders at the physical
     1920x1080;
   - if not, renders at the **logical** size (1280x720) and lets Windows scale it up.

   `result.json` → `display` says which happened.
4. **The street run logged nothing.** Three changes:
   - the batches now exist as `fptN.txt` **and** `fptN` (in case `bat` doesn't add `.txt`);
   - logging starts with both `con_SCOF` (xOBSE) and `scof`;
   - every console command gets a screenshot after typing (`shots\NN-typed-*.png`).
5. **Speed.** With a test save, forge goes straight to the Continue beep: there's no 20 s plan A
   wait any more. Plan A only runs while no save exists.
6. **Focus.** Forge re-focuses the game once before typing, and never sends Enter after losing focus.

## Hard rules (unchanged)
- Never write to the Steam copy or `%APPDATA%\Vortex`.
- Never hand-edit the real Plugins.txt or Oblivion.ini, and never edit the registry yourself
  (forge sets and removes its one compatibility value).
- Do nothing while Oblivion or the CS runs.
- Never send keys to the game.
- If something looks wrong: `forge playtest restore`, then `forge playtest status`.
- Report problems; don't patch `tools/playtest`.

## Tell Yuri before he starts
- Close Oblivion, and turn the Discord overlay off for Oblivion.
- **Step A (once): a new test save.** The game opens at the main menu. With the pad:
  1. choose **NEW** and skip the intro with Cross;
  2. when the **character screen** opens, change nothing and **don't touch the name box**: just
     choose **DONE** and confirm;
  3. wait. Forge takes the character to the Arena, saves and quits.
- **Step B: the test.** Hands off. **At three beeps, press Cross on CONTINUE.** The game quits by itself.
- **Step C: hands-on, in the street.** Three beeps again → Cross on CONTINUE, then play with the pad
  and quit normally.

## The .bat to write
1. **Pre-checks.**
   - Nothing running (tasklist).
   - `forge playtest status`.
   - Tests: `cd tools && python -m unittest discover -s playtest/tests -t .` should give **77 OK**,
     and `forge/tests` **24 OK**.
2. **Registry, read only.** Save the output of both:
   - `reg query "HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"`
   - `reg query "HKLM\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"`

   Save them **before** step A and again **after** step C. They must be identical.
3. **`forge playtest cells`**: save the output. The index format changed, so the first run
   re-indexes Oblivion.esm. The arena line should say `coc ICArena … arriving from ICArenaBloodworks`.
4. **Step A:** `forge playtest make-save`, then list `Saves\ForgePlaytest\`.
5. **Step B:** `call tools\playtest\acceptance.bat --no-pause`.
6. **Step C:** run `forge playtest tools\playtest\examples\example-firebolt.yaml --cell street`.
   Decide whether to run it from step B's **real-run** `result.json`: use the run folder whose
   `dry_run` is false, **not the newest folder** (that mistake skipped it in run 3). Run it if that
   run's `boot_seconds` isn't null. Afterwards: `forge test`, then `forge playtest status`.
7. **If any run reports no forge_test.log:** search for it with `where /r C:\ forge_test.log`, and
   with the same command under `%USERPROFILE%\Documents\My Games\Oblivion`. Report where it is, or
   that it isn't anywhere.
8. **Collect** into `forge-builds\playtest\handoff\run4\`:
   - every new run folder, whole (`shots\`, `boot-trace.jsonl`, `result.json`, `forge_test.log`);
   - `acceptance.txt`;
   - the outputs from steps 2, 3 and 4;
   - `<GOG>\obse.log` and `NorthernUI.log`;
   - `guardian.log`;
   - the last 200 lines of `controller_log`.

## Reply format (a .md file)
```
# Track E PC results run 4 (<date>)
Commit tested: <git rev-parse HEAD>
## Pre-checks
## Registry before/after (identical?) and what the Steam exe's Layers value is
## forge playtest cells
## make-save
result JSON; did the character screen close normally; save folder listing
## Automatic run (step B)
verdict / boot_strategy / boot_seconds / checks passed; display (from result.json)
events, error (exact), forge test report, forge_test.log (first 100 lines)
Is the whole screen visible now? Is it the Arena floor?
## Street run (step C)
## Screenshots: one line each (especially the typed-* shots: is the console open with the text in it?)
## Boot trace (around any failure)
## What Yuri saw
## Logs / where forge_test.log ended up (if missing)
## Anything you changed
## Questions / blockers
```
