# Handoff 25: phase 3b recon (Construction Set script editor, through the bridge)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Approved by Yuri (2026-10-06):** you may start the Construction Set from the **GOG copy** for this recon.
**Goal:** learn exactly how the CS script editor behaves under the bridge, so phase 3b can compile scripts automatically: window and control layout, what a successful compile looks like, and what a compile error looks like. **Nothing is saved.** No plugin is written, and Rebirth+, Vortex, the INI, `Plugins.txt` and saves are not touched.

> Run handoff 24 first if it isn't done. This handoff is independent of it, but do them one at a time.

## 0. Rules for this run (read first)

- **GOG copy only:** `C:\Users\Shadow\Desktop\Games\Oblivion`. Never the Steam copy.
- **Never save:** never click Save, never press Ctrl+S in the *main* CS window, and answer **No** to any "save changes?" prompt. Ctrl+S inside the *Script Edit* window is allowed: it only compiles into memory. No plugin is active, so nothing reaches the disk.
- **Load no plugins:** cancel the Data dialog if it appears. The recon doesn't need loaded data.
- **Unexpected dialog:** if anything unexpected appears, take a screenshot (`forge cs screenshot --hwnd <h>`), note its title and text (`forge cs controls <h>`), close it with **Cancel/No/Escape**, and report it. Don't improvise further steps.
- **Hands off:** don't drive the mouse or keyboard yourself. Use only the bridge commands below.
- **Secrets:** never print or copy `Oblivion\.cs_bridge_token`.
- **Game:** if Oblivion (the game) is running, stop and report. Don't close it.

Save all outputs under `_audit\forge-phase3b\` (not committed).

## 1. Before

1. Branch: run `git checkout forge/phase3-plugin` then `git pull`. Report `git log --oneline -1`.
2. Record the state so we can prove nothing changed:
   ```
   dir "C:\Users\Shadow\Desktop\Games\Oblivion\Data\*.es?" /T:W > _audit\forge-phase3b\data_before.txt
   tasklist /FI "IMAGENAME eq TESConstructionSet.exe" > _audit\forge-phase3b\cs_before.txt
   tasklist /FI "IMAGENAME eq Oblivion.exe" >> _audit\forge-phase3b\cs_before.txt
   ```
   If a CS is already running, stop and report. Don't close it.
3. Check whether the bridge task is running: `forge cs health`. Record the output. Run it **after** step 2.4, so that if the bridge isn't running yet, its own start doesn't launch a plain CS.

## 2. Start the CS with the script extender

Do this **before** anything starts the bridge server. The server starts the *plain* CS if none is running, and that one can't compile OBSE syntax.

1. Start: `start "" /D "C:\Users\Shadow\Desktop\Games\Oblivion" "C:\Users\Shadow\Desktop\Games\Oblivion\obse_loader.exe" -editor`
2. Wait for the main window: `forge cs wait "TES Construction Set" --timeout 180`
3. Run `forge cs windows > _audit\forge-phase3b\windows_start.txt`. If a **Data** dialog or warnings are open, close them with Cancel/Escape (`forge cs keys <h> "{ESC}"`) and list the windows again.
4. Run `forge cs health > _audit\forge-phase3b\health.txt` (also fine if the bridge task was already running before).
5. Note the main window's HWND (title `TES Construction Set`).

## 3. Open the script editor

1. `forge cs menu <main> "Gameplay->Edit Scripts..."`
   If the menu command fails, don't guess other labels: run `forge cs controls <main>` and report the error plus that output.
2. `forge cs wait "Script Edit" --timeout 30`
3. `forge cs windows > _audit\forge-phase3b\windows_script.txt` and note the Script Edit HWND.
4. `forge cs controls <scriptedit> > _audit\forge-phase3b\script_controls.txt`
   This is the most important file: index, class, name and HWND of every control. We need the big text box (`RichEdit20A` or `Edit`), the script-type combo (Object / Quest / Magic Effect), and the toolbar or menu items.
5. `forge cs screenshot --hwnd <scriptedit>`, then note where the PNG was saved.

## 4. A good compile (in memory only)

1. Click **New script** if the editor needs one (toolbar or `Script -> New`), then list controls again if anything changed.
2. Put this text in the editor. Use PowerShell so the line breaks survive:
   ```powershell
   forge cs type <scriptedit> "#<textbox index>" "scn ForgeReconGood`r`n`r`nbegin GameMode`r`nend"
   ```
3. Set the script type combo to **Object** if it isn't already (report how: `click`/`type` on the combo).
4. Compile: `forge cs keys <scriptedit> "^s"`
5. Immediately run `forge cs windows > _audit\forge-phase3b\after_good.txt`. Did a new window appear (title, class)? Did the Script Edit title change (e.g. now shows `ForgeReconGood`)? If a dialog appeared, save `forge cs controls <h>` of it and close it with Escape.

## 5. A compile error

1. Replace the text:
   ```powershell
   forge cs type <scriptedit> "#<textbox index>" "scn ForgeReconBad`r`n`r`nbegin GameMode`r`n  ForgeNotARealFunction`r`nend"
   ```
2. `forge cs keys <scriptedit> "^s"`
3. `forge cs windows > _audit\forge-phase3b\after_bad.txt`
4. For the error window(s): `forge cs controls <h> > _audit\forge-phase3b\error_controls.txt` (we need the message text with the line number), then a `forge cs screenshot --hwnd <h>`. Dismiss with `forge cs keys <h> "{ENTER}"`. Repeat if several dialogs chain, and record each.

## 6. Close without saving

1. Close the Script Edit window: `forge cs keys <scriptedit> "%{F4}"` (Alt+F4). If it asks to save the script, answer **No** and record that dialog's controls first.
2. Close the CS: `forge cs menu <main> "File->Exit"`. Answer **No** to any "save changes?" prompt, recording its controls first.
3. Check the CS is gone: `tasklist /FI "IMAGENAME eq TESConstructionSet.exe" > _audit\forge-phase3b\cs_after.txt`
4. Prove nothing changed: `dir "C:\Users\Shadow\Desktop\Games\Oblivion\Data\*.es?" /T:W > _audit\forge-phase3b\data_after.txt`. Then run `fc _audit\forge-phase3b\data_before.txt _audit\forge-phase3b\data_after.txt`, which should report no differences.

## 7. If something goes wrong

| What you see | What to do / send |
|---|---|
| The CS doesn't appear within 180 s | `tasklist`, any `obse_editor` log in the GOG folder (`obse_editor.log`), and a desktop screenshot (`forge cs screenshot --desktop`). Stop. |
| A plain CS started instead (no OBSE) | report it; close it with No to saving; stop |
| The `menu` command fails | the error text plus `forge cs controls <main>` |
| `type` fails or the text is cut | the error; try once with a one-line text (`scn ForgeReconGood`) and report both |
| The CS hangs or crashes | the time, the last command, and `cs_after.txt`. Don't retry more than once. |
| A Data file timestamp changed | **stop and report immediately**, with both `dir` files |

## 8. Report back to Yuri (for the cloud session)

- The `git log` line, and `health.txt`.
- `windows_start.txt` and `windows_script.txt`.
- **`script_controls.txt` in full**, the most important file.
- `after_good.txt`, and what changed after the good compile.
- `after_bad.txt` and `error_controls.txt`: the exact error text, and whether it includes the line number.
- What the close prompts were and how you answered them.
- The `fc` result (Data unchanged).
- Screenshot file paths. The PNGs themselves don't need to be sent unless something looked odd.
