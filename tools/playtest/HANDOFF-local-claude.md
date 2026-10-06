# Handoff to the local Claude: run 3 of the TES4Forge playtest on Yuri's PC

You are the Claude on Yuri's Windows PC. The cloud Claude owns `tools/playtest`. Your job:
1. Pull the latest commit of branch `claude/serene-maxwell-03d2fh` (PR https://github.com/pagesofthetome-art/Oblivion/pull/2).
2. Write Yuri **one `.bat`**.
3. After he runs it, write the reply in the format at the end of this file, **as a file**:
   `forge-builds\playtest\handoff\HANDOFF-to-cloud-run3.md`.

Speak to Yuri in plain, short steps. He plays with a PS5 pad.

## What I fixed from your run 2 report (thank you, the screen diagnosis was spot on)
- **Screen size.** The test ini is now windowed at the **desktop size** (1280x720 on Shadow), and
  forge removes the window border once the window appears, the same as `Controller --prepare-display`
  does for play. Menus, the console and message boxes should all be on screen now.
- **Controller.**
  - The test ini sets `bUse Joystick=0`.
  - For the run, the GOG copy uses **the play setup's NorthernUI.ini**. It is read from the Steam
    Data folder, swapped in under the restore journal, and the GOG file comes back byte for byte
    afterwards.
  - The controller companion starts with `--mode northernui`.

  Together these should give pad-only control, with no stick-driven cursor.
- **Arena.**
  - The pick is now the busiest interior whose EditorID or name says "Arena". Side rooms are
    excluded: holding, bloodworks, quarters, storage, hall, champion, tunnel, gate, lobby, team,
    blue/yellow…
  - The player is put on a **door arrival spot** (where the gate lets you in), never on a random
    coordinate.
  - I can't see Oblivion.esm from the cloud, so please paste `forge playtest find arena` and
    confirm from a screenshot that it's the real fighting floor.
- **Street.** The Imperial City districts have no map markers named after them. `street` now picks
  the busiest cell of the `ICMarketDistrict` worldspace and stands you outside a shop door (falling
  back to the other IC districts). `--cell world:<Worldspace>` works for any worldspace.
- **Open.** Weye's grid is now computed from the marker's position (run 2 showed `0,0` because
  persistent refs sit in the world's persistent cell).
- **Plan B.** Forge no longer presses keys in the main menu (Down+Enter opened that off-screen
  message box). Instead it **beeps three times**, and Yuri presses **Cross on CONTINUE**. The test
  save from run 2 is reused, and the location is then reached from the in-game console.
- **Darkness.** `--bright` sets `bFullBrightLighting=1`. Use it only if the arena is still too dark.
  (fGamma most likely has no effect in windowed mode, so I left it alone.)
- **Discord.** The preflight prints a note when Discord is running. Ask Yuri to turn its overlay
  off for Oblivion: Discord → Settings → Game Overlay.
- `acceptance.bat --no-pause` now skips the final pause, so you don't need `< nul`.
- **The junction.** Keep it. The Controller scripts expect `<repo>\Oblivion`. Forge works either
  way: it also finds the sibling folder, or reads `forge-builds\playtest\machine.json`.

## Hard rules (unchanged)
- Never write to the Steam copy or `%APPDATA%\Vortex`. Reading the Steam NorthernUI.ini is fine, and forge does it.
- Never hand-edit the real Plugins.txt or Oblivion.ini.
- Do nothing while Oblivion or the CS runs.
- Never send keys to the game yourself.
- If something looks wrong: `forge playtest restore`, then `forge playtest status`.
- Report problems; don't patch `tools/playtest`.

## Tell Yuri before he starts
- Close Oblivion, and turn off the Discord overlay for Oblivion.
- Hands off the keyboard and mouse.
- **If you hear three beeps, press Cross on CONTINUE.** That's the only button needed until the
  game quits by itself.
- After that, a second run stays open (the hands-on check). Play with the pad only.

## The .bat to write
1. **Pre-checks.**
   - `tasklist` shows no game or CS processes.
   - `forge playtest status`.
   - Tests: `cd tools && python -m unittest discover -s playtest/tests -t .` should give **73 OK**,
     and `forge/tests` **24 OK**.
2. **Location info.** Save the output of each:
   - `forge playtest cells` (the first run re-indexes Oblivion.esm, because the index format changed);
   - `forge playtest find arena`;
   - `forge playtest find market`.
3. **NorthernUI.ini.** Run `fc /n` on the Steam and the GOG `Data\OBSE\Plugins\NorthernUI.ini`
   (read only) and save the diff.
4. **Automatic run:** `call tools\playtest\acceptance.bat --no-pause`.
5. **Hands-on run,** only if step 4 reached the game:
   `forge playtest tools\playtest\examples\example-firebolt.yaml --cell street`.
   The game stays open; Yuri plays, then quits normally. After that, run `forge test` and
   `forge playtest status`.
6. **Collect** into `forge-builds\playtest\handoff\run3\`:
   - both newest run folders, whole, including `shots\` and `boot-trace.jsonl`;
   - `acceptance.txt`;
   - the outputs from steps 2 and 3;
   - `<GOG>\obse.log` and `<GOG>\Data\OBSE\Plugins\NorthernUI.log`;
   - `forge-builds\playtest\guardian.log`;
   - the last 200 lines of `Controller\controller_log.txt`;
   - a listing of `Documents\My Games\Oblivion\Saves\ForgePlaytest\`.

## Reply format (save it as a .md file, then give Yuri the file)
```
# Track E PC results run 3 (<date>)
Commit tested: <git rev-parse HEAD>
## Pre-checks
tests, status hashes, Discord overlay off?
## Locations
forge playtest cells / find arena / find market (paste)
Is the arena pick the real fighting floor? (from the screenshot and Yuri)
## NorthernUI.ini diff (Steam vs GOG)
## Automatic run
verdict / boot_strategy / boot_seconds / checks passed of total; did Yuri have to press Continue?
restore_check and hashes before/after; NorthernUI.ini restored (hash same as before)?
events, error (exact), forge test report, forge_test.log (first 100 lines)
## Screenshots
one line each: what is visible, is the whole menu/console/HUD on screen now
## Boot trace
the lines around any failure (or the first 40 if it passed)
## Hands-on run (street)
where he stood, merchant/barter, shop door, pad only? cursor gone? brightness? anything off-screen?
## Logs (relevant excerpts) and what's missing
## Anything you changed
## Questions / blockers
```
