# Handoff to the local Claude: run 2 of the TES4Forge playtest on Yuri's PC

You are the Claude on Yuri's Windows PC. The cloud Claude owns `tools/playtest`. Your job:
1. Read this file.
2. Write Yuri **one `.bat`** that runs the test and collects the evidence.
3. After he runs it, write the reply in the format at the end of this file.

Speak to Yuri in plain, short steps. He plays with a PS5 pad.

Code: branch `claude/serene-maxwell-03d2fh` (PR https://github.com/pagesofthetome-art/Oblivion/pull/2).
Pull the latest commit. Read `tools/playtest/README.md`.

## What changed since run 1 (Yuri's correction is done)
- **The playtest is now real Oblivion in real vanilla cells.** The placeholder meshes, test
  geometry and generated cells are gone.
  - **Locations:** `arena` is the vanilla Arena interior (`coc`). `street` is the Market District
    map marker (`cow` + `moveto`). `open` is the Weye map marker. They are picked from the GOG
    copy's own Oblivion.esm, which is only read.
  - **Test actors:** `ForgeTestCells.esp` now holds only the actors (dummy, caster, merchant,
    townsfolk). They wear the faces, hair and clothes of real vanilla NPCs, and the first batch
    moves them next to the player.
- **The browser preview is optional.** Nothing opens it any more.
- **The GOG path is configurable.** Forge also finds a sibling `..\Oblivion` next to the clone, so
  `Desktop\Games\Oblivion-repo` → `Desktop\Games\Oblivion` works without the junction. You can also
  write `forge-builds\playtest\machine.json` with `{"game_dir": "C:\\Users\\...\\Desktop\\Games\\Oblivion"}`.
  The junction may stay, but please **remove it** if nothing else needs it, and tell me.
- **Boot diagnostics.** Each run folder now holds:
  - `boot-trace.jsonl`: menu stack, menu mode, focus and window, twice a second;
  - `shots\*.png`: main menu, console, loaded game, any error;
  - `Plugins.test.txt` and `Oblivion.test.ini`.
- **Boot plan B.** If the console at the main menu doesn't start a game, forge presses Continue on
  a dedicated test save, then uses the in-game console. Make that save once with
  `forge playtest make-save`.

## Answers to your questions
1. **Why the arena never loaded.** The timing shows the main menu was detected at 12.9 s (menu id
   1044), so the menu probe works. `coc ForgeTestArena` was then typed, but for 120 s the main menu
   never closed and no loading screen appeared. So the typed command never ran.
   - Most likely the console didn't open at the main menu, or the typing didn't reach it.
   - It was not a mesh problem: nothing loaded at all.
   - The new screenshots (`shots\NN-console-at-menu.png`, `NN-A-no-load.png`) will show which it was.
2. **Window in front.** Forge reported it focused before typing, but I can't confirm Yuri saw it.
   The trace now logs focus and the window rectangle every 0.5 s, and the screenshots show the
   screen.
3. **Logs I need** (copy them if they exist; list the ones that don't):
   - `<GOG>\obse_loader.log`, `<GOG>\obse.log`, `<GOG>\Data\OBSE\obse.log`
   - `<GOG>\Data\OBSE\Plugins\NorthernUI.log`, `<GOG>\Data\OBSE\Plugins\NorthernUI.ini`
   - `<GOG>\Data\OBSE\obse.ini`
   - the **whole newest** `forge-builds\playtest\runs\<time>\` folder: `shots\`, `boot-trace.jsonl`,
     `result.json`, `forge_test.log`, `playtest_manifest.json`, `Plugins.test.txt`, `Oblivion.test.ini`
   - `forge-builds\playtest\guardian.log`, `Controller\freeze_report.txt`, and the last 200 lines
     of `Controller\controller_log.txt`
   - a listing of `Documents\My Games\Oblivion\Saves\ForgePlaytest\`
   - the output of `forge playtest cells` (which vanilla cells were picked)

## Hard rules (unchanged)
- Never write to the Steam copy or `%APPDATA%\Vortex`.
- Never hand-edit the real `Plugins.txt` or `Oblivion.ini`.
- Do nothing while Oblivion or the CS runs.
- Never send keys to the game yourself.
- If anything looks wrong: `forge playtest restore`, then `forge playtest status`.
- Don't patch `tools/playtest`: report instead. One-line environment fixes are OK if you say what you changed.

## The .bat to write
1. **Pre-checks.**
   - No Oblivion, OblivionLauncher, obse_loader or TESConstructionSet in `tasklist`.
   - `forge playtest status` (hashes).
   - The unit tests: `cd tools && python -m unittest discover -s playtest/tests -t .` should give
     **70 OK**, and `forge/tests` **24 OK**.
2. **`forge playtest cells`**: save its output. It builds the actors and prints the chosen
   `arena` / `street` / `open` locations. The first run indexes Oblivion.esm, which can take a minute.
3. **`call tools\playtest\acceptance.bat`**. It runs: status → `--dry-run` → the real run with
   `--quit` → `forge test` → status.
4. **If the real run's error says "Run `forge playtest make-save` once"** (plan A failed and there
   is no save yet):
   - Tell Yuri in big letters: "The game will open at the main menu. With the pad: NEW → skip the
     intro with Cross → finish the character screens any way you like → then wait; forge takes
     over, puts you in the arena, saves, and quits."
   - Run `forge playtest make-save`, then run `acceptance.bat` once more.
5. **Collect** everything in "Logs I need" into `forge-builds\playtest\handoff\`.

Before the run, tell Yuri: close Oblivion, keep hands off the keyboard and mouse until the game
quits by itself (about 40 s), and leave the game window in front.

## Optional hands-on check (only if the automatic run passed)
`forge playtest tools\playtest\examples\example-firebolt.yaml --cell street`. The game stays open.
With the **pad only**:
- talk to "Ilvia the Trader" (she should be standing right in front of you) and Barter;
- walk into a real Market District shop through its door;
- quit the game normally.

Then `forge test` and `forge playtest status`. Note anything that needed the keyboard, NPCs
falling through the world or stuck in walls, and any popup the pad couldn't close.

## Reply format (write `forge-builds\playtest\handoff\HANDOFF-to-cloud.md` and give Yuri the same text)
```
# Track E PC results run 2 (<date>)
Commit tested: <git rev-parse HEAD>
## Pre-checks
tests (playtest n / forge n), GOG path used (auto / machine.json / junction), NorthernUI present?
## forge playtest cells
<paste output>
## Automatic run
verdict / boot_strategy / boot_seconds / checks passed of total
restore_check (same?) and hashes before/after
events (from result.json): <paste>
error (if any): <paste exactly>
forge test report: <paste>
forge_test.log: <paste, first 100 lines>
## make-save (if it was needed)
what Yuri did, result JSON, then the second acceptance run's verdict/boot_strategy/boot_seconds
## Screenshots
for each file in shots\: name + one line on what it shows (main menu? console visible? which place?)
## Boot trace
the lines around the failure, or the first 40 lines if it passed
## What Yuri saw on screen
## Hands-on check (if done)
## Logs (relevant excerpts only) and what's missing
## Anything you changed
## Questions / blockers
```
Paste text exactly. If a step was skipped, say so and why.
