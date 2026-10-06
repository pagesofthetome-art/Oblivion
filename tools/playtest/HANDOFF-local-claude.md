# Handoff to the local Claude: run 6 of the TES4Forge playtest on Yuri's PC

You are the Claude on Yuri's Windows PC. The cloud Claude owns `tools/playtest`. Your job:
1. Pull the latest commit of `claude/serene-maxwell-03d2fh` (PR https://github.com/pagesofthetome-art/Oblivion/pull/2).
2. Do the **read-only research** in step 2 below.
3. Write Yuri **one `.bat`**.
4. After he runs it, write your reply **as a file**: `forge-builds\playtest\handoff\HANDOFF-to-cloud-run6.md`.

Speak to Yuri in plain, short steps. He plays with a PS5 pad. **Forge never closes the game: Yuri
quits every time, after the beep.**

## Run 5 was the breakthrough. Thank you, the console screenshot was exactly what I needed
### Fixed
1. **Test actors "not found".**
   - Oblivion's console does not accept `<FormID>.Command`. `0C00080A.GetAV` is read as a command name,
     which gives "Script command not found".
   - Every command on another reference is now `prid <FormID>` followed by the command. That covers:
     - bringing the dummy and the caster to the player (that also failed in run 5, which is why there
       was no NPC);
     - `GetAV`;
     - `cast`.
   - The player still uses `player.`.
2. **Behind the Arena gate.** The `setpos` to the Bloodworks-gate spot is gone. In the Arena forge
   now leaves Yuri where `coc ICArena` puts him. (The street still uses an outdoor door spot; Yuri liked it.)
3. **HasSpell printed nothing**, so it's removed from the example. The example now checks the dummy's
   health before and after the fire bolt, and that it isn't dead.
4. **No log file.**
   - After the game exits, forge now searches the game folder and `My Games\Oblivion` for **any**
     .log/.txt written during the run that contains the run's BEGIN marker. That would catch an OBSE
     console-logging plugin, for example.
   - The console is photographed after every batch (`shots\NN-output-fptN.png`), while it still shows
     that batch's output.
   - Your eyes on those screenshots are the fallback evidence.

### Still open: a log file
`scof` / `con_SCOF` wrote nothing anywhere. I can't see the docs of the OBSE build on the PC, so I
need you to look (step 2).

## Hard rules (unchanged)
- Never write to the Steam copy or `%APPDATA%\Vortex`.
- Never hand-edit the real Plugins.txt or Oblivion.ini, or the registry.
- Do nothing while Oblivion or the CS runs.
- Never send keys to the game.
- If something looks wrong: `forge playtest restore`, then `forge playtest status`.
- Report problems; don't patch `tools/playtest`, and **don't install anything** (no plugins), only report.

## Step 2: research (read only, before the .bat)
1. Which OBSE is it?
   - The version from `<GOG>\obse.log` (first lines).
   - The file versions of `<GOG>\obse_1_2_416.dll` and `obse_loader.exe` (PowerShell
     `(Get-Item ...).VersionInfo`).
2. In the command docs, search for these, with each entry's syntax and description (a few lines
   each): **SCOF**, **con_SCOF**, **SetConsoleOutputFile**, **WriteToFile**, **WriteToLog**,
   **PrintToFile**, **ToFile**, **Log**, **SaveINI**, **ConScribe**, **Pluggy**.
   - The docs are in `<repo>\script extender\obse_command_doc.html` and `obse_whatsnew.txt`, or the
     xOBSE docs next to the GOG copy.
3. Is any console-logging OBSE plugin already in `<GOG>\Data\OBSE\Plugins\` or in the Steam
   `Data\OBSE\Plugins\`? For example `ConScribe.dll`. List the DLL names; read only.

## Tell Yuri before he starts
- Close Oblivion.
- At **three beeps**, press Cross on **CONTINUE** (the test save from run 5 is still there, so no new save is needed).
- You should now see **two NPCs come to you** in the Arena: a training dummy in front and a spell
  tester at your side. The tester casts a fire bolt at the dummy.
- At the next beep, play as long as you like, then **quit with the pad**.

## The .bat to write
1. **Pre-checks.**
   - Nothing running.
   - `forge playtest status`.
   - Tests: `cd tools && python -m unittest discover -s playtest/tests -t .` should give **84 OK**,
     and `forge/tests` **24 OK**.
2. **`call tools\playtest\acceptance.bat --no-pause`.** The test save exists, so it skips make-save.
3. **Collect** into `forge-builds\playtest\handoff\run6\`:
   - the new run folders, whole;
   - `acceptance.txt`;
   - the step 2 research notes;
   - `<GOG>\obse.log`, `guardian.log`, and the last 200 lines of `controller_log`;
   - if `result.json` has a `log_source`, a copy of that file.

## Reply format (a .md file)
```
# Track E PC results run 6 (<date>)
Commit tested: <git rev-parse HEAD>
## Research: OBSE version, logging commands found (syntax), logging plugins present
## Test run
verdict / boot_seconds / checks passed / log_source; events; error (exact); forge test report
## Console output screenshots (READ them): for each shots\NN-output-fptN.png, type out the console lines you can see
   (especially: what does `GetAV Health` print? any "not found"? what did con_SCOF/scof print?)
## Did the dummy and the caster appear next to Yuri? Did the dummy get hit (fire)? Where was Yuri standing?
## Restore (identical?)
## What Yuri saw
## Anything you changed
## Questions / blockers
```
