# TES4Forge playtest (Track E)

`forge playtest` runs **the real game**: Oblivion.exe through xOBSE, with a minimal load order
(Oblivion.esm, the DLC, the mod under test, and a small plugin of test actors). It boots straight
into a **vanilla cell**, runs scripted checks, and stays open for you to play with the pad. When
the game exits, the real setup is restored. `forge test` prints the report. The browser preview is
an optional layout check only. Yuri's Rebirth+ setup (Steam copy, Vortex) is never written to.

```
forge playtest tools\playtest\examples\example-firebolt.yaml          boot, check, keep playing
forge playtest <spec.yaml | Mod.esp> [--cell arena|street|open|<InteriorEditorID>|world:<World>|marker:<Map marker>] [--bright] [--dry-run] [--kill-on-freeze]
forge playtest make-save                     one time: New Game with the pad -> test save (Continue loads it)
forge playtest find <text>                   search vanilla interiors and map markers for --cell
forge playtest restore | status | cells      fix-up; hashes; test actors + chosen locations
forge test [RUN_DIR] [--json]                report of the last run
forge preview <spec | Mod.esp | cells> [--cell X] [--open]    optional browser layout check
```
Exit codes: 0 pass, 1 setup/usage error, 2 checks failed (also: no checks, froze, never ran).
PC acceptance run: `tools\playtest\acceptance.bat`, which writes `forge-builds\playtest\acceptance.txt`.

Where the GOG copy is found, in this order:
1. `FORGE_PLAYTEST_GAME_DIR`.
2. `forge-builds\playtest\machine.json` (`{"game_dir": "...", "steam_dir": "...", "plugins_txt": "...", "ini": "..."}`).
3. `<repo>\Oblivion`.
4. A sibling `..\Oblivion` next to the clone.

## The method, and why

**Game: the clean GOG copy** (`Desktop\Games\Oblivion`, override with `FORGE_PLAYTEST_GAME_DIR`).
It has xOBSE, Oblivion.esm and the DLC, and no Vortex hardlinks. It starts without Steam, and every
main-menu freeze in `Controller\_project_notes.md` came from the Steam route. Forge refuses a game folder
under `steamapps`, one that holds `Data\vortex.deployment.json`, and any write into Steam or Vortex folders.

**Profile: swap-in under a restore journal.** Oblivion has no switch for another `Plugins.txt`
or `Oblivion.ini`. It always reads `%LOCALAPPDATA%\Oblivion\Plugins.txt` and
`Documents\My Games\Oblivion\Oblivion.ini`, and the Steam and GOG copies share both files. So
forge builds the profile in `forge-builds\playtest\profile\` and swaps it in for one run:

1. It refuses if Oblivion.exe, OblivionLauncher.exe, obse_loader.exe or the CS is running.
2. It backs up both files and writes `restore-journal.json` (with SHA-256 hashes, fsynced) before changing anything.
3. It replaces them atomically. The test `Plugins.txt` lists Oblivion.esm, the DLC, the mod's
   masters, the mod and `ForgeTestCells.esp` (test actors only), nothing else. The test ini is the real one with these
   changes: no intro videos, its own save folder (`Saves\ForgePlaytest\`), no autosaves.
4. It stages the plugins and the console batches into the GOG copy. Each new file
   goes into the journal first. Existing files are never overwritten. A missing master is copied
   from the Steam Data folder (read only).
5. Restore puts the original bytes back (and their timestamps), checks the hashes, and deletes
   only the files it created, and only if they are unchanged. It runs:
   - in a `finally` when the game exits;
   - from a detached guardian process (`python -m playtest.guardian`) if forge dies;
   - at the start of every `forge playtest` / `forge test`, after a power cut;
   - when you run `forge playtest restore`.

   Each run records the before/after hashes in `result.json` (`restore_check`).

Rejected options: the GOG copy alone (it still reads the shared files); `sTestFile1=` ini entries
(how they mix with Plugins.txt is undocumented for Oblivion); env-var redirection (Oblivion asks
Windows for the folders, not the environment); a second Windows user (too heavy).

## Quick boot

The test ini is your real Oblivion.ini with these changes:
- intro videos off, its own save folder, no autosaves;
- **windowed at the desktop size**, and forge removes the window border (as `Controller --prepare-display`
  does for play). Under Windows display scaling (150 % on Shadow), a DPI-unaware Oblivion.exe gets
  drawn 1.5x too big (runs 2 and 3: 2/3 of the frame visible). So:
  - if the play copy's Oblivion.exe has a DPI compatibility flag (HKCU/HKLM `AppCompatFlags\Layers`,
    e.g. `HIGHDPIAWARE`), the GOG exe gets the same flag for the run only (journaled, removed
    afterwards) and renders at the physical size;
  - otherwise it renders at the logical size, and Windows scales it up to fill the screen;
- `bUse Joystick=0`, so the pad goes through NorthernUI only. For the run, NorthernUI uses **the play
  setup's NorthernUI.ini**: it is copied in from the Steam Data folder, read only, and the GOG copy's
  own file is restored afterwards. The controller companion starts in NorthernUI mode;
- `--bright` adds `bFullBrightLighting=1` for dark places.

**Yuri's rule: forge never closes the game.** Forge does its steps, then beeps and shows
"done, quit when ready" in the console window and in game. You play on and quit with the pad. Forge
waits for the Oblivion process to exit before it restores anything (run 4: restoring while the game
was still exiting gave Access denied; writes are now also retried for ~10 s). If forge itself dies,
the guardian restores after the game exits.

The boot itself:
1. A test save must exist: without one, forge stops before launching and says to run
   `forge playtest make-save`.
2. `obse_loader.exe` starts the game. At the main menu forge **beeps**, and you press Cross on
   **CONTINUE**. Forge never types into the main menu: that never started a game on the PC and
   opened other menus (run 2: a message box; run 4: the Load menu).
3. After the load, the boot command (`coc <Interior>` / `cow <World> x y`) runs from the in-game
   console. Opening the console is tried up to three times, and typing happens only once the console
   is confirmed open. If the save brings up a character-creation menu, the run stops and asks for a
   new `make-save`.
4. **`forge playtest make-save`** (once): New Game with the pad, type any name, choose DONE and
   confirm (DONE needs a name). Forge waits until the character screen has closed, `coc`s to the
   arena, then runs one batch that logs where you are and saves as `ForgePlaytestNew`. It beeps, and
   you quit. Only if the log confirms you were in the arena does the new save replace
   `Saves\ForgePlaytest\ForgePlaytestBase.ess`. Otherwise the old save is left exactly as it was. Then
   autosaves in that folder (and only there) are removed so that Continue always loads it.
5. After the load, `bat fpt1` runs (each batch exists as `fptN.txt` and `fptN`, so `bat` finds it
   either way):
   - Outdoors it puts you on a **door arrival spot**. Indoors you stay where `coc` put you: run 5's
     arrival spot was behind the Arena gate.
   - It brings the test actors next to you, checks where you are (`GetInCell` / `GetInWorldspace`), and
     runs the steps.
   - References are named by their **EditorID** (`SomeBeggarRef.GetAV Health`). Each batch line
     is compiled as a one-line script, and scripts name persistent references that way. Two other
     forms don't work in a batch: `<FormID>.Command` (run 5: "Script command not found") and `prid`
     (run 6: the next batch line ignores the selection).
   - Results take two routes:
     1. Each check value goes into a result global from `ForgeTestCells.esp`. The global is first
        set to a sentinel, so a failed line never counts as a value.
     2. xOBSE's `PrintToFile` writes the markers and values to `forge_test.log`; `scof` doesn't exist
        in this xOBSE (run 6). After the game exits, forge looks for that log in the game folder and
        `My Games\Oblivion`. If it has no values, forge reads the result globals from the
        `ForgePlaytestResult` save that the last batch made.
   - The console is photographed after every batch (`shots\NN-output-fptN.png`) as evidence.
   - The last batch shows the "quit when ready" message in game.
6. Boot time is measured from the command to "loaded, player in control". The target is 30 s, once
   you press Continue at the beep.

Every run folder (`forge-builds\playtest\runs\<time>\`) also keeps:
- `boot-trace.jsonl`: menu stack, menu mode, focus and window, twice a second;
- `shots\*.png`: screenshots of the main menu, the console, the loaded game, and any error;
- `Plugins.test.txt` and `Oblivion.test.ini`: exactly what the game was given.

So a failed boot can be read afterwards.

## Test locations: real vanilla cells

These are picked from the test game's own Oblivion.esm, which is only read. The index is cached in
`forge-builds\playtest\vanilla-index.json`. `forge playtest cells` shows the choices.

| key | where | for |
|---|---|---|
| `arena` | the Imperial City Arena's fighting floor: `coc ICArena` | spells and combat |
| `street` | the Market District worldspace: its busiest cell, outside a shop door | doors, shops, crowds, a merchant |
| `open` | the *Weye* map marker (shore road west of the city) | weather (`fw`) and projectiles |

Any vanilla interior works with `--cell <EditorID>`, any worldspace with `--cell world:<EDID>`, and
any map marker with `--cell "marker:<name>"`. `forge playtest find <text>` searches all three.

**Test actors are real vanilla beggars** (Yuri's choice: the console already resolves vanilla
persistent references by EditorID). `vanilla.test_actors` picks them from Oblivion.esm:
- the NPC's class is Beggar, and it is not essential;
- the reference is persistent and has an EditorID;
- NPCs without their own script come first, then the order is by EditorID, so the pick is stable.

The first is **`TestTarget`**, the second **`TestCaster`**. Specs use these role names, and
`forge playtest cells` prints which beggars they are. The first batch brings both to the player.
It gives the target 500 health and sets aggression 0 / confidence 100 on both, so a test spell
doesn't kill the target or start a fight (the test save is thrown away anyway).

`ForgeTestCells.esp` still carries forge-made actors, but they are not used, because it isn't
proven that the console can name them. It also carries the result globals. The forge actors were:
- `ForgeArenaDummyRef`: essential, never fights back, 500 health;
- `ForgeArenaCasterRef`: passive caster for `cast` steps;
- `ForgeStreetMerchantRef`: barter; work 08-20, off duty 20-08;
- two townsfolk.

They copy the hair, eyes, FaceGen face and clothes of real vanilla Imperial NPCs. The plugin adds
no meshes, statics or doors, and overrides no vanilla record.

## Automated checks

```yaml
test_plan:
  cell: arena
  steps:
    - addspell: ForgeExampleFireboltSpell
    - check: {ref: TestTarget, fn: GetAV, args: [Health], save: hp}
    - cast: {caster: TestCaster, spell: ForgeExampleFireboltSpell, target: TestTarget}
    - wait: 3
    - check: {ref: TestTarget, fn: GetAV, args: [Health], expect: "< $hp"}
```
Step kinds: `additem removeitem equip addspell cast spawn setav modav moveto weather console wait check`.
Names resolve to console FormIDs in the test load order (EditorIDs from the mod and the test cells,
`Plugin.esp:00ABCD`, or `0x` FormIDs).

**How it runs in game.** Oblivion can't read JSON, and an OBSE quest compiled per manifest would
need the Construction Set on every run. So `playtest_manifest.json` is compiled into console batch
files instead: one per `wait`, run with vanilla `bat`. Markers and values reach `forge_test.log` via
xOBSE's `PrintToFile`, or via the result save's globals (see above). `forge test` judges the
result. A run passes only if:
- the BEGIN marker matches the manifest's run id;
- `GetInCell` returned 1;
- every check has a value that meets its expectation;
- no step logged a console error;
- the END marker is there;
- there is at least one check.

"It launched" is never a pass.

## Controller first

There are no key-only prompts. The boot is automatic, and playing afterwards uses NorthernUI (PS5
pad), which preflight checks is in the test game. Forge also starts the controller companion
(`--no-companion` to skip it). The vanilla Persuasion tutorial page that ignores the pad
(docs/new-mods-audit-2026-10-06.md) is detected through the menu stack: a MessageMenu over
PersuasionMenu. It is dismissed automatically with Down, Enter.

## Safety

- The freeze probe (`Controller\oblivion_freeze.py`) and Windows' "not responding" state are
  watched all the time. A confirmed freeze lasting `--hang-seconds` (default 20) is reported as
  `FROZE`, with a beep and `Controller\freeze_report.txt`. Forge does not close the game (close it
  yourself); `--kill-on-freeze` makes forge close it.
- Nothing happens while another Oblivion or the CS is open. Keys go only to the test game's own
  window (checked by process id).

## Browser preview (optional)

The preview is a quick layout check, not a playtest, and nothing opens it automatically.
`forge preview` builds a page from `preview/oblivion-preview-template.html`. It keeps the template's
engine as is (WebGL with the `?soft` canvas fallback, keyboard/mouse/touch/gamepad) and draws:
- **for a mod:** the cells the mod places objects in;
- **for `forge preview cells`:** a vanilla interior from Oblivion.esm.

Objects are boxes sized from each base's bound radius. Click an NPC, or aim at it and press
E / Cross, to see its packages and schedule.

## Tests

```
cd tools
python -m unittest discover -s playtest/tests -t .
```
The suite covers:
- profile swap/restore: byte-identical files and timestamps, crash recovery, the guardian, refusals;
- manifest and log parsing;
- the test-actor plugin: deterministic, no geometry, looks copied, lints clean against a fixture master;
- picking vanilla locations;
- the preview page;
- the CLI;
- an end-to-end run against a fake game that executes the batch files: pass, the street exterior,
  no save, `make-save` (good and bad), a save made before character creation, the DPI flag,
  fail, freeze (reported, or killed with the opt-in), refusal, dry run, forge interrupted (before and
  during the game), masters taken from the play copy. In every run the player quits, never forge.

Every fixture is invented; there is no Bethesda data.
