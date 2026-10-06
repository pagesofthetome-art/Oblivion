# Project state

Each track updates its own section when it finishes (see the TES4Forge roadmap).

## Track E: playtest (2026-10-06, run 2 prepared)

Code: `tools/playtest/` ([README](tools/playtest/README.md)), CLI group `forge playtest | test | preview`.

- **PC run 1 (commit 685b4ab):**
  - Restore was byte-identical. Unit tests passed on the PC.
  - The boot failed: `coc` typed at the main menu never started a game.
  - Yuri's direction: real Oblivion in vanilla cells, no placeholder art, the preview only optional.
- **Run 2 changes:**
  - Test locations are vanilla cells picked from Oblivion.esm.
  - `ForgeTestCells.esp` is test actors only, with vanilla looks.
  - Boot plan B: Continue on a test save made once with `make-save`.
  - Boot trace and screenshots in every run.
  - The GOG path is configurable (sibling folder, `machine.json`).
  - The preview is no longer opened automatically.
  - 70 playtest tests + 24 forge tests pass in the cloud.
- **Waiting on:** PC run 2 (`tools/playtest/HANDOFF-local-claude.md`).
- **Next after that:**
  - fix whatever the screenshots show;
  - switch the example to a Track B `kind: plugin` build once that exists.
