# Handoff 27: CS script-editor recon, take 3 (optional cross-check oracle)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Priority:** optional. Yuri decided forge will get its **own** script compiler (`docs/forge-script-compiler-plan.md`); the CS stays only as an optional cross-check. Run this when there's PC time; it isn't blocking.
**Approved by Yuri (2026-10-06):** starting the **plain** Construction Set from the GOG copy. Nothing is saved.
**Goal:** create a new script in Script Edit without the mouse, type into it, and record what a good and a failing compile look like.

## 0. Rules

Same as handoff 26: GOG copy only, plain `TESConstructionSet.exe` (never `obse_loader`), no plugins loaded, never save, answer **No** to save prompts, record and close unexpected dialogs and stop, don't drive the mouse or keyboard yourself, never print the token, stop if the game is running. Outputs go to `_audit\forge-phase3b\take3\`.

## 1. What's new

Branch **`forge/phase3-plugin`**. The bridge gained:
- `forge cs toolbar <hwnd>`: lists a toolbar's buttons (index, command id, enabled, separator).
- `forge cs toolbar-press <hwnd> --index N`: presses one by posting `WM_COMMAND` to its owner (no mouse).
- `forge cs menus <hwnd>`: the window's menu bar as a tree, with command ids.
- `forge cs menu-command <hwnd> <id>`: posts a menu command id (no mouse).
- `FORGE_CS_BRIDGE_PORT`: lets the client talk to a second, temporary bridge.

**Why a temporary bridge:** the scheduled bridge task runs the *workspace* copy, `C:\Users\Shadow\Desktop\Games\oblivion_cs_bridge_server.py`, so it doesn't have the new commands. **Don't edit or restart that task.** Start a second bridge from the repo clone on port 43822 just for this run, and stop it afterwards.

## 2. Steps

1. `git checkout forge/phase3-plugin`, `git pull`. Report `git log --oneline -1`.
2. Record the before-state (same as handoff 26 §1.2: `dir … Data\*.es?`, `tasklist` for the CS and the game). Stop if either is running.
3. **Start the temporary bridge** from the repo root, in its own window:
   ```
   start "forge-bridge-43822" python oblivion_cs_bridge_server.py --port 43822 --token-file "C:\Users\Shadow\Desktop\Games\Oblivion\.cs_bridge_token" --no-launch-editor
   ```
   Then, **in the console you use for all following commands**: `set FORGE_CS_BRIDGE_PORT=43822`. Run `forge cs health` and expect `"ok": true`.
4. **Start the plain CS:**
   ```
   start "" /D "C:\Users\Shadow\Desktop\Games\Oblivion" "C:\Users\Shadow\Desktop\Games\Oblivion\TESConstructionSet.exe"
   ```
   Then run `forge cs wait "TES Construction Set" --timeout 180`, then `forge cs windows`.
5. **Open Script Edit:** run `forge cs menu <main> "Gameplay->Edit Scripts..."`, then `forge cs wait "Script Edit" --timeout 30`.
6. **Explore** (save each output):
   - `forge cs controls <scriptedit>` → `controls_0.txt`
   - `forge cs menus <scriptedit>` → `menus_scriptedit.txt`
   - `forge cs menus <main>` → `menus_main.txt`
   - `forge cs toolbar <toolbar hwnd>` → `toolbar.txt`. The toolbar is the `ToolbarWindow32` control, #3 in handoff 26.
   - `forge cs screenshot --hwnd <scriptedit>`
7. **New script:**
   - If `menus_scriptedit.txt` has an item like **New**: `forge cs menu-command <scriptedit> <id>`.
   - Otherwise, press toolbar buttons one at a time, starting at index 0 and skipping separators. Use **at most 4** buttons. After each press, run `forge cs windows` and `forge cs controls <scriptedit>`, and stop as soon as the `RichEdit20A` control is **enabled**.
   - If a press opens a dialog (e.g. a script list), record its controls, close it with `forge cs keys <h> "{ESC}"`, and continue with the next button.
   - **Don't press a button whose tooltip or effect looks like Delete or Recompile All.** If you can't tell, stop and report.
   - Record which button or menu id created the new script.
8. **Good compile** (PowerShell, so the line breaks survive). Use the index of the **visible** `RichEdit20A` (#4 in handoff 26), and re-check it in the latest controls output:
   ```powershell
   $env:FORGE_CS_BRIDGE_PORT = "43822"
   forge cs type <scriptedit> "#<richedit index>" "scn ForgeReconGood`r`n`r`nbegin GameMode`r`nend"
   forge cs keys <scriptedit> "^s"
   ```
   Then `forge cs windows` → `after_good.txt`. Record the Script Edit title, the type combo text (from `controls`), and any dialog's controls (close it with `{ESC}` or `{ENTER}`).
9. **Error compile:** create another new script (same method), type `scn ForgeReconBad`r`n`r`nbegin GameMode`r`n  ForgeNotARealFunction`r`nend`, run `^s`, then `forge cs windows` → `after_bad.txt`. For each error dialog: `forge cs controls <h>` → `error_controls.txt` (we need the exact message, and whether it gives a line number), then `forge cs keys <h> "{ENTER}"`.
10. **Close without saving:**
    - Close Script Edit with `forge cs keys <scriptedit> "%{F4}"`. If asked to save the script, record the prompt and answer **No**.
    - Then `forge cs menu <main> "File->Exit"`; answer **No** to any save prompt, recording it first.
    - Check the CS is gone (`tasklist`). Record the after-state `dir` and run `fc` against the before-state; only the free-space line may differ.
11. **Stop the temporary bridge:** close the `forge-bridge-43822` window, or `taskkill /FI "WINDOWTITLE eq forge-bridge-43822*" /T`. Check the scheduled bridge is untouched: `set FORGE_CS_BRIDGE_PORT=` and then `forge cs health` should still answer on 43821.

## 3. If something goes wrong

| What you see | What to do / send |
|---|---|
| The temporary bridge doesn't start (e.g. `ModuleNotFoundError: pywinauto`) | the error; use the same Python the scheduled task uses (`pythonw.exe` from the task's "Task To Run"). Don't install packages without asking Yuri. |
| `toolbar` errors (OpenProcess / VirtualAllocEx) | the error text; continue with the menus route only |
| No New item in the menus, and none of the 4 buttons enables the editor | stop and report the toolbar, menus and screenshot |
| The CS hangs or crashes | the time, the last command, and `tasklist`; don't retry more than once |
| A Data timestamp changed | **stop and report immediately** |

## 4. Report back to Yuri (for the cloud session)

- The `git log` line, plus `health` on 43822 and later on 43821.
- `menus_scriptedit.txt`, `menus_main.txt` (the Gameplay and File parts are enough), `toolbar.txt`.
- Which menu id or toolbar button created a new script, and the controls after it (editor enabled? type combo text?).
- `after_good.txt`, plus the title and combo after the good compile.
- `after_bad.txt` and `error_controls.txt` (the exact error text).
- The close prompts and your answers, and the `fc` result.
