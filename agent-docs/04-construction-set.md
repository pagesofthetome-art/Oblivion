# 04 · TES Construction Set: expert use and automation

`Oblivion\TESConstructionSet.exe` (CS 1.2.0404). It's the only tool that **compiles scripts**, **generates lip files**, **edits landscape and pathgrids visually**, **finalizes navigation (pathgrids)**, and **places objects in the render window**. For bulk or precise record edits, TES4Edit is faster and safer (see `05-tes4edit.md`).

## 1. Launching correctly

| Need | Launch |
|---|---|
| Plain editing, no OBSE syntax | `Oblivion\TESConstructionSet.exe` |
| Scripts using xOBSE syntax/commands | `obse_loader.exe -editor` from the `Oblivion\` folder (xOBSE 22.13 installed 2026-10-04). |
| CSE (if the user installs it) | CSE's own loader. It includes OBSE editor support. |

The bridge server (`oblivion_cs_bridge_server.py`) starts the plain CS if no CS is running. To get OBSE compiling, the user (or you, with permission) must start the CS through `obse_loader.exe -editor` **before** the bridge attaches. The bridge attaches to whatever `TESConstructionSet.exe` is running from `Oblivion\`.

`Oblivion\oblivion_bridge.py launch --master ... --new-plugin ...` passes `-master/-plugin` arguments. **The official CS doesn't document these arguments. Treat them as unverified** and load files through File → Data instead.

## 2. Core workflow (File → Data)

1. **File → Data...** opens the Data dialog (`#32770`, title `Data`). Tick the masters (`Oblivion.esm` + any needed DLC). Tick and **Set as Active File** on the plugin you're editing, or set none as active to create a new plugin on save.
2. **OK** loads. On large loads the CS shows progress, then often a series of warning popups ("MASTERFILE: ...", "Could not find..."). Answer with **Yes to All** if offered, or Enter repeatedly. Through the bridge: `wait "Warning"` → `keys <hwnd> {ENTER}` in a loop until no CS dialog besides the main window is visible.
3. Edit. **Only the active file gets changes.** Every touched record (even just opening and pressing OK) is copied into the active plugin. That's how **dirty edits / ITMs** are born.
4. **File → Save** (Ctrl+S). The first save of a new plugin asks for a filename in `Data\`.
5. Back up before and after: `python Oblivion\oblivion_bridge.py backup MyMod.esp` → `Oblivion\CSBackups\`.

**One active file at a time.** The CS can't edit two plugins at once or make an ESP a master (CSE can). For ESP masters, see §5.

## 3. Windows and what they're for

| Window | Use |
|---|---|
| **Object Window** (`FaceClass`) | Tree (`SysTreeView32`, ID 2093) of base-object categories + list (`SysListView32`, ID 1041) of records. Double-click a row to open its edit dialog. Right-click → New / Duplicate / Delete / Use Info. |
| **Cell View** (`ViewerClass`) | World/interior picker, cell list, reference list of the selected cell. Double-click a cell to load it in the Render Window. |
| **Render Window** (`MonitorClass`) | 3D placement. Drag objects from the Object Window. Common keys: `F` drop selection to the surface below, `T` top-down view, `M` toggle markers, `A` toggle bright lighting, `Ctrl+D` duplicate selection. Mouse placement is hard to automate. Prefer typing exact coordinates into the reference dialog (double-click the ref → Position/Rotation fields). |
| **Script Edit** (Gameplay → Edit Scripts, or the Scripts toolbar button) | Write, compile and save scripts. Compile errors show as modal message boxes with line numbers. |
| **Quests** / **Filtered Dialogue** | Quest data, stages, targets, topics, INFO conditions and result scripts. |
| **Use Info** (right-click a record) | Where a record is used. Check this before changing or deleting anything shared. |

## 4. Driving the CS through the bridge (expert patterns)

Commands: `python oblivion_cs_bridge_client.py <cmd>`. HWNDs and control indexes change every session and after any UI change, so **rediscover every time**.

```
health                                   bridge alive?
windows                                  list CS windows (hwnd, title, class, visible, enabled)
controls <hwnd>                          full control tree (index, name, class, hwnd, rect)
menu <hwnd> "File->Data..."              select a menu path (exact labels, "->" separated)
click <hwnd> "#12" | "OK"                click by index or exact name
type <hwnd> "#7" "text" [--append]       set or append text in an edit control
keys <hwnd> "{ENTER}"                    send keys: {ESC} {TAB} ^s (Ctrl+S) %f (Alt+F) +{TAB}
listview <listhwnd> [--start N --count N]   read rows/columns of a SysListView32 (e.g. Object Window list)
listview-select <listhwnd> --text EDID [--double]   select / open a record by its EditorID
tree <treehwnd> [--depth 2]              read a SysTreeView32 (Object Window categories)
tree-select <treehwnd> "\Items\Weapon"   pick a category
wait "Data" [--timeout 10] [--exact]     block until a CS window whose title contains the text appears
screenshot --hwnd <hwnd>                 PrintWindow capture (works even when other windows cover the CS)
```
The `keys`, `listview*`, `tree*`, `wait` and PrintWindow screenshot commands are new in bridge v1.1. The bridge server must be **restarted** to load them: Task Scheduler → "Oblivion Construction Set GUI Bridge" → End, then Run. You can also log off and on, or rerun `Install-Oblivion-CS-Bridge.cmd`.

**Reliable action loop (always):**
1. `windows` → find the target HWND by title and class.
2. `controls <hwnd>` → find the control by **name or Win32 class + rect**, not by a remembered index.
3. Act (`click`/`type`/`keys`/`menu`).
4. Verify: `windows` again (did a dialog open or close? is the main window enabled again?), then `controls`, `listview` or `screenshot`. **Stop if the expected state didn't appear.** Never chain several blind actions.
5. Modal dialogs disable the main window (`enabled: false`). Always resolve them (read the text with `controls`, then OK/Cancel/keys) before continuing.

**Recipes**
- *Open a record*: `windows` → Object Window hwnd → `controls` to get the tree and list hwnds → `tree-select <tree> "\Items\Weapon"` → `listview-select <list> --text IronLongsword --double` → `wait "Weapon"` (dialog) → `controls <dialog>` → `type` into fields → `click "OK"` → verify.
- *Create a script*: main window → `menu "Gameplay->Edit Scripts..."` → `wait "Script Edit"` → `controls` → find the big edit control (class `RichEdit20A`/`Edit`) → `type <hwnd> "#N" "<full source>"` → `keys <hwnd> "^s"` (Script Edit's save compiles) → `windows`: a new message-box window means a compile error. Read it, fix the source, retry. Script type (Object/Quest/Magic Effect) is a combo box in the Script Edit window; set it before saving.
- *Save plugin*: main window `keys "^s"`, or the `Save Plugin` toolbar button, then verify the file's timestamp in `Data\`.
- *Data dialog*: `menu "File->Data..."` → `wait "Data" --exact` → `controls` → the plugin list is a `SysListView32`. Ticking a checkbox needs a double-click on the row or Space after selecting it (`listview-select --text X` then `keys "{SPACE}"`). Verify with a screenshot. Then `Set as Active File`, then `OK`.

**Limits.** Render-window placement, landscape painting and pathgrid drawing need mouse drags in 3D space. Do them only with screenshots after every step, or hand them to the user with exact instructions (cell, coordinates, object). Prefer xEdit or numeric reference fields for anything positional.

## 5. Masters, ESP-on-ESP and the ESM trick

- To build a patch that depends on `ModA.esp` with the vanilla CS: in TES4Edit, set the ESM flag on `ModA.esp` (header → Record Flags → ESM), save, and edit in the CS with ModA ticked as a master. Afterwards clear the flag on `ModA.esp`. The master entry in your patch stays valid. **Restore the user's file exactly** (keep a backup and compare hashes).
- Better: create the patch's masters and records in TES4Edit (it supports ESP masters natively). Use the CS only for script compiling.

## 6. Scripting in the CS

- Script types: **Object** (attached to items/actors/activators via `SCRI`), **Quest** (attached to a QUST), **Magic Effect** (used by a Script Effect `SEFF` in a spell/enchantment).
- Compile rules: every EditorID you use must exist in the loaded files. Quest variables are referenced as `QuestEditorID.varName`. References in scripts must be **persistent** and have an EditorID.
- Result scripts (quest stages, INFOs, package ends) compile when the dialog is closed with OK. They are short-lived and limited, so keep them to a few lines and move real logic into a quest script.
- Very large scripts hit CS size limits and get slow to compile. Split logic into several quest scripts or xOBSE user functions (`Call`).
- After **any** change to a script that others reference, recompile the dependents too (variable indexes). Never use a "recompile all scripts" option in a mod: it copies every vanilla script into the active file.

## 7. CS dirty-edit hazards (avoid, then clean)

| Action | Side effect |
|---|---|
| Opening a cell in the Render Window and moving the camera only | Usually safe, but can mark `LAND` changes if you click with landscape edit mode on. |
| Clicking OK on a vanilla record's dialog without changes | Creates an ITM override in your plugin. |
| Renaming an EditorID | Prompts "create a new form?" **Yes** = new record (safe). **No** = renames the vanilla record (breaks other mods' scripts at compile time). |
| Deleting a vanilla object/reference | Creates a UDR or deleted record (CTD risk). Disable instead. |
| Generating pathgrid/LOD/region objects | Can touch hundreds of cells/records. Do it only when intended. |
| Recompiling all scripts | Overrides every vanilla script. Never do it in a mod. |

**After every CS session**, run `tools\modlint.py lint MyMod.esp` and clean with `tools\xedit_run.py qac MyMod.esp --yes` (with the user's consent). See `05-tes4edit.md`.

## 8. Known CS quirks

- It can hang on exit. Wait, then check that the plugin saved before killing it.
- It crashes often. Save every few minutes. If it crashes, the plugin on disk is the last save; check its timestamp.
- Unicode/accents: plugins are cp1252. Avoid characters outside it in names and books.
- Book text is HTML-like (`<font>`, `<br>`, `<div align="center">`, `<img src="...">`).
- The Data dialog's "Details..." shows a plugin's dependencies. "Set as Active File" is disabled for ESMs (by design).
- Very long INFO/topic lists open slowly. Use Filtered Dialogue scoped to your quest.
