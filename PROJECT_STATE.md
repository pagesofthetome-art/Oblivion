# Project state

Each track updates its own section when it finishes (see the TES4Forge roadmap).

## Track E: playtest (2026-10-06, run 7 prepared)

Code: `tools/playtest/` ([README](tools/playtest/README.md)), CLI group `forge playtest | test | preview`.

- **PC run 1:** restore OK; the boot failed (`coc` at the main menu never ran). Yuri's direction: real
  Oblivion, vanilla cells, preview optional.
- **PC run 2:** restore OK; `make-save` worked. Root cause found: the game drew 1920x1080 into a 1280x720
  desktop, so the menus were off-screen. Also: the stick moved a cursor, the arena pick was a side room,
  no street marker, too dark.
- **Run 3 fixes:**
  - windowed at the desktop size, made borderless;
  - `bUse Joystick=0`, the play setup's NorthernUI.ini swapped in (journaled), the companion in NorthernUI mode;
  - arena = busiest Arena interior minus side rooms, standing on a door arrival spot;
  - street = Market District worldspace, outside a shop door;
  - plan B = a beep, then Cross on Continue;
  - `--bright`, a Discord note, `acceptance.bat --no-pause`;
  - 73 tests.
- **PC run 3:**
  - Fixed: pad-only control, Continue via the beep, a real Market District street.
  - Still wrong:
    - the arena pick was the ruin XPCann04;
    - the test save was made before character creation;
    - 2/3 of the screen showed (Windows 150 % DPI scaling);
    - the street batches logged nothing.
- **Run 4 fixes:**
  - arena pinned to ICArena, arriving from the Bloodworks;
  - make-save waits for the character screen to close and verifies the location before saving;
  - autosaves are cleaned from the test save folder;
  - the play exe's DPI flag is mirrored onto the GOG exe for the run (journaled), else logical-size rendering;
  - each batch exists with and without `.txt`, logging starts with `con_SCOF` and `scof`;
  - a screenshot after every typed command;
  - Continue directly when a save exists;
  - 77 tests.
- **PC run 4:**
  - Fixed: the whole screen is visible, the controller works, ICArena loads.
  - Still wrong:
    - make-save gave up on its second console command;
    - the restore hit Access denied while the game was exiting;
    - old saves were deleted too early.
- **Yuri's rule:** forge never closes the game.
- **Run 5:**
  - no auto-quit anywhere: forge beeps, Yuri quits, restore runs after the process exits (writes retried);
  - a freeze is only reported (killing it is opt-in);
  - make-save uses one batch (probe + save + note) and replaces the old save only once the new one is verified;
  - no typing in the main menu;
  - acceptance stops if make-save fails;
  - 81 tests.
- **PC run 5:** the pipeline worked end to end: make-save made a save, Continue reached ICArena in
  25 s, the batches ran, and Yuri quit himself. Still wrong:
  - `<FormID>.Command` is not accepted by the console, so the test actors failed;
  - scof wrote no file;
  - the player was set behind the Arena gate.
- **Run 6:**
  - `prid` + command for every other reference;
  - no interior setpos;
  - the log is searched by its run marker anywhere under the game folder and My Games;
  - the console is photographed after each batch;
  - HasSpell is dropped from the example;
  - 84 tests.
- **PC run 6:** the console printed values (`GetInCell >> 1.00`) and the quit note showed. Still wrong:
  - prid doesn't carry over between batch lines ("requires a reference");
  - `scof` doesn't exist in xOBSE 22.13.
- **Run 7:**
  - references named by EditorID in every line;
  - check values go to sentinel-guarded result globals, logged with xOBSE PrintToFile;
  - a result save is read back (`essglobals.py`) when there is no log;
  - make-save confirms the location from the new save's own global;
  - 88 tests.
- **Run 7 revised (Yuri):**
  - the test actors are two real vanilla beggars, TestTarget and TestCaster, picked from
    Oblivion.esm: non-essential, persistent references with EditorIDs;
  - the forge-made actors are unused;
  - 90 tests.
- **Waiting on:** PC run 7. The goal is a PASS (the fire bolt lowers the target's health, the target survives).
