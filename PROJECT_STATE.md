# Project state

Each track updates its own section when it finishes (see the TES4Forge roadmap).

## Track E: playtest (2026-10-06, run 4 prepared)

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
- **Waiting on:** PC run 4 (`tools/playtest/HANDOFF-local-claude.md`).
