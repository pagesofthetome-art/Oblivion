# Handoff to the local Claude: run the TES4Forge playtest on Yuri's PC

You are the Claude running on Yuri's Windows PC, with file access. A cloud Claude built **Track E of TES4Forge** (`forge playtest`, `forge test` and `forge preview`) without a PC. Nothing in it has run against the real game yet.

**Your job:**
1. Check the PC.
2. Write Yuri **one `.bat`** that runs the test and collects the evidence.
3. After Yuri runs it, read the results and write a **handoff message back to the cloud Claude**, in the format at the end of this file.

Read `AGENTS.md` and `tools/playtest/README.md` first. Speak to Yuri in plain, short steps. He plays with a PS5 pad.

## Hard rules (do not break them)
- **Never write** to the Steam copy (`C:\Program Files (x86)\Steam\steamapps\common\Oblivion`) or to anything under `%APPDATA%\Vortex`.
- **Never edit** `%LOCALAPPDATA%\Oblivion\Plugins.txt` or `Documents\My Games\Oblivion\Oblivion.ini` by hand. Only forge swaps them, and forge restores them.
- **Do nothing while Oblivion or the Construction Set is running.** The `.bat` must check for that first and stop.
- Don't print or copy `Oblivion\.cs_bridge_token`.
- If a restore ever looks wrong, the fix is `forge playtest restore`. Don't improvise.

## 1. Get the code
The work is on branch `claude/serene-maxwell-03d2fh` (PR https://github.com/pagesofthetome-art/Oblivion/pull/2). It is based on the Phase 1 branch `claude/jolly-pasteur-hiurwl`.

The workspace root is the repo root: `Desktop\Games`, where `forge.cmd`, `Controller\` and `Oblivion\` sit. Check out that branch, or copy `tools\playtest\`, `tools\forge\cli.py`, `preview\forge-test-cells.html` and `forge.cmd` from it.

Stop and tell Yuri if the workspace has uncommitted changes you'd overwrite.

## 2. Pre-checks: read-only, report every result
Write the `.bat` so that it prints each of these:

1. **Python and libraries.** Check that `python --version` works (`forge.cmd` calls `python`). Check that numpy, Pillow and PyYAML import; if not, install them with `python -m pip install -r tools\requirements-assetkit.txt -r tools\requirements-forge.txt`.
2. **The test game** = the GOG copy at `<repo>\Oblivion`:
   - `Oblivion\obse_loader.exe` and `Oblivion\Data\Oblivion.esm` exist;
   - list the DLC `.esp` files in `Oblivion\Data`;
   - `Oblivion\Data\vortex.deployment.json` must **not** exist (if it does, forge will refuse, correctly);
   - `Oblivion\Data\OBSE\Plugins\NorthernUI.dll` exists? If not, the pad only works through the companion. Note it, but don't install anything yet.
3. **Paths forge will use:** run `forge playtest status`. It prints whether the profile is off, plus the SHA-256 of the real Plugins.txt and Oblivion.ini. If it says the profile is ON, run `forge playtest restore` first and report that.
4. **Unit tests:** `cd tools && python -m unittest discover -s playtest/tests -t .` should print `Ran 59 tests ... OK`, and the same for `forge/tests` (24). Paste failures verbatim.
5. **Nothing running:** `tasklist` shows no `Oblivion.exe`, `OblivionLauncher.exe`, `obse_loader.exe` or `TESConstructionSet.exe`.

## 3. The run
`tools\playtest\acceptance.bat` already does the core run:
- hashes before;
- `--dry-run`;
- the real run with `--quit`;
- `forge test`;
- hashes after;
- `forge preview --open`.

Its output goes to `forge-builds\playtest\acceptance.txt`.

Your `.bat` should:
1. Do the pre-checks above, then `call tools\playtest\acceptance.bat`.
2. Then **collect the evidence** into one folder, `forge-builds\playtest\handoff\`:
   - `acceptance.txt`;
   - the newest `forge-builds\playtest\runs\<timestamp>\` folder, whole: `result.json`, `forge_test.log`, `playtest_manifest.json`;
   - `forge-builds\playtest\guardian.log`, if it exists;
   - `Controller\freeze_report.txt` and the last 200 lines of `Controller\controller_log.txt`, if they exist;
   - from the GOG copy: `Oblivion\obse_loader.log`, `Oblivion\obse.log` (or `Data\OBSE\obse.log`) and `Oblivion\Data\OBSE\Plugins\NorthernUI.log`, if they exist;
   - a listing (`dir /s /b`) of `Oblivion\Data\meshes\forge` and `Oblivion\fpt*.txt`. Both should be **empty or missing** after the run, because forge removes what it staged.
3. **Never** pause in the middle of the boot, and never send keys to the game. Forge does the typing.

Tell Yuri, in big plain text before he starts:
- close Oblivion;
- don't touch the keyboard or mouse for about 40 seconds;
- the game will open, jump into a stone arena, then quit by itself;
- after that a browser page opens: walk around with WASD or the pad, click the NPCs, then close it.

## 4. Short hands-on check (optional, after the automatic run)
If Yuri is up for it, ask him to run `forge playtest tools\playtest\examples\example-firebolt.yaml --cell street`. This time the game stays open. With the **pad only**, he should:
- walk to the merchant ("Ilvia the Trader"), talk to her and open Barter;
- go through the door at the far end of the street and check he arrives in the arena;
- cast "Forge Firebolt" at the training dummy (R1) and check its health bar drops;
- quit the game normally.

Then run `forge test` and `forge playtest status`. Note anything that needed the keyboard, any invisible or floating geometry, NPCs that don't move or fall through the floor, and any popup the pad couldn't close.

## 5. What to look for, and the likely failures
If something below happens, record it exactly (copy text and timings). **Don't patch the code yourself**: the cloud Claude owns `tools/playtest`. The exception is a one-line environment fix, and you must say what you changed.

| Symptom (in `acceptance.txt` or `result.json` → `events`, `error`) | What it tells the cloud Claude |
|---|---|
| `the main menu never appeared` | The menu probe (`oblivion_osk.GameUIProbe`) didn't see menu 1044. Note what the screen showed. |
| `the console did not open; not typing into the game` | The console doesn't register as menu mode. Note whether the console was visibly open on screen. |
| `... did not finish loading`, or the game sits at the main menu with "coc ..." typed | `coc` from the main menu didn't work. Note what happened on screen. |
| `GetInCell >> 0` / "player was not in ForgeTestArena" | `moveto` or the cell name failed. |
| `no FORGE markers in the log` | xOBSE `PrintC` didn't run from a batch file. Check `obse.log`. |
| `no forge_test.log` | `scof` wrote elsewhere, or `bat` didn't find `fpt1.txt`. Search the GOG folder and My Games for `forge_test.log`. |
| step 4 (`cast`) fails, or health unchanged | The console `cast` from an NPC didn't fire. |
| Invisible floor/walls, the player falls, or the game crashes on entering the cell | Kit mesh or record problem. Copy any crash text and `freeze_report.txt`. |
| `FROZE` | Attach `freeze_report.txt`. |
| `restore: ... DIFFERENT`, or hashes before ≠ after | **Most important.** Run `forge playtest restore` at once, then `forge playtest status`, and report both. |

**Boot time:** report `boot_seconds` from `result.json`. The target is under 30 s.

## 6. The handoff message back to the cloud Claude
When the run is done, write `forge-builds\playtest\handoff\HANDOFF-to-cloud.md`, and also give Yuri the same text to paste into the cloud session. Use exactly these sections:

```
# Track E PC results (<date>)
Branch/commit tested: <git rev-parse HEAD>
## Pre-checks
python/libs, GOG game files, DLC list, vortex.deployment.json absent?, NorthernUI.dll present?, unit tests (n OK / failures)
## Automatic run
verdict: <PASS/FAIL/FROZE/NOT-RUN>   boot_seconds: <n>   checks: <passed>/<total>
restore_check: plugins_txt same=<true/false>, ini same=<true/false>; hashes before/after: <...>
staged files left behind: <none / list>
events (from result.json): <paste>
forge test report: <paste>
forge_test.log: <paste whole file if under 100 lines, else first 100>
## What Yuri saw on screen
<plain notes: menu, console, loading, arena look, anything odd>
## Hands-on check (if done)
merchant/barter, door, firebolt on dummy, pad-only? popups? geometry?
## Preview page
opened? arena visible? NPC click shows packages/schedule? pad worked?
## Logs attached / excerpts
obse.log / NorthernUI.log / freeze_report.txt / guardian.log excerpts (relevant lines only)
## Anything you changed
<files and why, or "nothing">
## Questions / blockers for the cloud Claude
```

Keep the facts exact: paste text, don't paraphrase error messages. If a step was skipped, say so and why.
