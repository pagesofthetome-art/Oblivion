# Handoff to the local Claude: run 7 of the TES4Forge playtest on Yuri's PC

You are the Claude on Yuri's Windows PC. The cloud Claude owns `tools/playtest`. Your job:
1. Pull the latest commit of `claude/serene-maxwell-03d2fh` (PR https://github.com/pagesofthetome-art/Oblivion/pull/2).
2. Do the quick check in step 2 below.
3. Write Yuri **one `.bat`**.
4. After he runs it, write your reply **as a file**: `forge-builds\playtest\handoff\HANDOFF-to-cloud-run7.md`.

Speak to Yuri in plain, short steps. He plays with a PS5 pad. **Forge never closes the game: Yuri
quits every time, after the beep.**

## Your run 6 fix list: done
1. **References by EditorID.**
   - `prid` and `<FormID>.` are gone. Every line now names the actors directly:
     - `ForgeArenaDummyRef.moveto player 0 600 0` and `ForgeArenaCasterRef.moveto player 200 100 0`
       (they come to Yuri);
     - `ForgeArenaCasterRef.cast <spell> ForgeArenaDummyRef`;
     - `set ForgeR02 to ForgeArenaDummyRef.GetAV Health`.
   - They are persistent references with EditorIDs in `ForgeTestCells.esp`, as before.
2. **Logging, two routes:**
   - **a.** Each check stores its value in a **result global** in `ForgeTestCells.esp` (`ForgeR01`…).
     It is first set to -99999, so a failed line never looks like a value. Then xOBSE's
     **`PrintToFile`** writes it, plus the markers: `PrintToFile "forge_test.log" "GetAV >> %.2f%r" ForgeR02`
     (`%r` = new line).
   - **b.** The last batch runs `save ForgePlaytestResult`. After Yuri quits, forge reads the result
     globals **out of that save file**, so even with no log at all there's a verdict. The result
     save is deleted afterwards.
3. **All `scof` / `con_SCOF` lines are removed.**
4. **make-save** checks the arena the same way, through the new save's own `ForgeRInPlace` global.
   - New `ForgeTestCells.esp` records were added **at the end**, so the existing test save still matches.
   - **No new make-save is needed.**

## Step 2: quick check (read only)
- In the xOBSE docs (`obse_command_doc.html` / `obse_whatsnew.txt`), copy the **exact** PrintToFile
  entry: syntax, where the file is written (game folder? Data?), and whether it appends and adds a line
  break.
- Also confirm that `%r` (new line) and `%.2f` are valid format specifiers.

## Hard rules (unchanged)
- Never write to the Steam copy or `%APPDATA%\Vortex`.
- Never hand-edit the real Plugins.txt or Oblivion.ini, or the registry.
- Do nothing while Oblivion or the CS runs.
- Never send keys to the game.
- If something looks wrong: `forge playtest restore`, then `forge playtest status`.
- Report problems; don't patch `tools/playtest` or install anything.

## Tell Yuri before he starts
- Close Oblivion.
- At **three beeps**, press Cross on **CONTINUE**.
- In the Arena, the **training dummy** should walk up in front of you and the **spell tester** beside
  you. The tester casts a fire bolt at the dummy.
- At the next beep, play as long as you like, then quit with the pad.

## The .bat to write
1. **Pre-checks.**
   - Nothing running.
   - `forge playtest status`.
   - Tests: `cd tools && python -m unittest discover -s playtest/tests -t .` should give **88 OK**,
     and `forge/tests` **24 OK**.
2. **`call tools\playtest\acceptance.bat --no-pause`.**
3. **Collect** into `forge-builds\playtest\handoff\run7\`:
   - the new run folders, whole (`result.json`, `forge_test.log`, `shots\`, `boot-trace.jsonl`);
   - `acceptance.txt`;
   - the step 2 notes;
   - `<GOG>\obse.log` and `guardian.log`;
   - if `result.json` has `log_source`, which file that was;
   - search `<GOG>` and `My Games\Oblivion` for any `forge_test.log` (`where /r`) and list the hits.

## Reply format (a .md file)
```
# Track E PC results run 7 (<date>)
Commit tested: <git rev-parse HEAD>
## PrintToFile (docs: syntax, where it writes, line breaks)
## Test run
verdict / boot_seconds / checks passed / log_source / save_values (from result.json)
forge test report (paste)
forge_test.log (paste, first 60 lines) and where it was found
## Console screenshots (read 05-output-fpt1 / 07-output-fpt2: type out every error line)
## Did the dummy and caster come to Yuri? Did the fire bolt hit (health dropped)?
## Restore (identical?)
## What Yuri saw
## Anything you changed
## Questions / blockers
```
