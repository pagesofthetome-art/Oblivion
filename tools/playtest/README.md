# TES4Forge playtest (Track E)

`forge playtest` runs **the real game**: Oblivion.exe through xOBSE, with a minimal load order
(Oblivion.esm, the DLC, the mod under test, and a small plugin of test actors). It boots straight
into a **vanilla cell**, runs scripted checks, and stays open for you to play with the pad. When
the game exits, the real setup is restored. `forge test` prints the report. The browser preview is
an optional layout check only. Yuri's Rebirth+ setup (Steam copy, Vortex) is never written to.

```
forge playtest tools\playtest\examples\example-firebolt.yaml          boot, check, keep playing
forge playtest <spec.yaml | Mod.esp> [--cell arena|street|open|<InteriorEditorID>|marker:<Map marker>] [--quit] [--dry-run]
forge playtest make-save                     one time: New Game with the pad -> test save (boot plan B)
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

1. `obse_loader.exe` starts with the intro videos switched off.
2. **Plan A:** at the main menu the driver opens the console and types the location's boot
   command: `coc <Interior>`, or `cow <World> x y` for an exterior. Oblivion then starts a default
   character right there: no character creation, no tutorial dungeon.
3. **Plan B:** used if plan A starts no load within 20 s and a test save exists. It presses Enter
   (Continue), which loads `Saves\ForgePlaytest\ForgePlaytestBase.ess`, then types the boot
   command in the in-game console. Make that save once with `forge playtest make-save`: you press
   New Game with the pad, and forge takes over as soon as you can walk.
4. After the load, `bat fpt1` (then `fpt2`… after each `wait`) brings the test actors next to you,
   checks where you are (`GetInCell` / `GetInWorldspace`), and runs the steps.
5. Boot time is measured from the command to "loaded, player in control". The target is 30 s.

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
| `arena` | the Arena interior (EditorID/name says Arena; the one with the most references wins) | spells and combat |
| `street` | the *Market District* map marker in the Imperial City | doors, shops, crowds, a merchant |
| `open` | the *Weye* map marker (shore road west of the city) | weather (`fw`) and projectiles |

Any vanilla interior works with `--cell <EditorID>`, and any map marker with `--cell "marker:<name>"`.
`forge playtest find <text>` searches both.

`ForgeTestCells.esp` adds **only test actors**, parked in an empty holding cell and moved next to
the player by the first batch:
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
    - check: {ref: ForgeArenaDummyRef, fn: GetAV, args: [Health], save: hp}
    - cast: {caster: ForgeArenaCasterRef, spell: ForgeExampleFireboltSpell, target: ForgeArenaDummyRef}
    - wait: 3
    - check: {ref: ForgeArenaDummyRef, fn: GetAV, args: [Health], expect: "< $hp"}
```
Step kinds: `additem removeitem equip addspell cast spawn setav modav moveto weather console wait check`.
Names resolve to console FormIDs in the test load order (EditorIDs from the mod and the test cells,
`Plugin.esp:00ABCD`, or `0x` FormIDs).

**How it runs in game.** Oblivion can't read JSON, and an OBSE quest compiled per manifest would
need the Construction Set on every run. So `playtest_manifest.json` is compiled into console batch
files instead: one per `wait`, run with vanilla `bat`. The first batch turns on `scof forge_test.log`,
so every console result lands in the log. xOBSE's `PrintC` writes a `FORGE|STEP|n` marker before
each step. `forge test` judges the log. A run passes only if:
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
  watched all the time. A confirmed freeze lasting `--hang-seconds` (default 20) closes the test
  game, and the run is reported as `FROZE`, with `Controller\freeze_report.txt`.
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
  plan A failing with and without a save, `make-save`, fail, freeze, refusal, dry run, forge
  crash, masters taken from the play copy.

Every fixture is invented; there is no Bethesda data.
