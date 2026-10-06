# Project state

Each track updates its own section when it finishes (see the TES4Forge roadmap).

## Track E: playtest (2026-10-06)

Code: `tools/playtest/` ([README](tools/playtest/README.md)), CLI group `forge playtest | test | preview`.

- **Done, tested in the cloud (59 unit + end-to-end tests with a fake game):**
  - test profile swap and restore, byte-identical, with crash recovery (journal, guardian, auto-restore);
  - generated `ForgeTestCells.esp`: arena, street and open cells; lints clean;
  - assetkit mesh kit;
  - manifest compiled into console batches, and the `forge_test.log` judge;
  - quick-boot driver, freeze kill, auto-dismiss of the Persuasion tutorial;
  - browser preview from plugin data, checked in headless Chromium with WebGL and the canvas fallback.
- **Not yet run on the PC:**
  - real boot time;
  - in-game behaviour of: `coc` from the main menu, `bat`/`scof`, the console-open probe, the test-cell records and kit meshes, the Cast step.
  - Acceptance: `tools\playtest\acceptance.bat`.
- **Next:**
  - feed the PC results back;
  - switch the example to a Track B `kind: plugin` build when that lands;
  - pathgrids for the street NPCs;
  - a real exterior worldspace patch (Track G).
