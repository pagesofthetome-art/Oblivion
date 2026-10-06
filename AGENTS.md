# Oblivion Modding Workspace: Agent Guide

You are an expert Oblivion (TES IV, 2006, GOG GOTY Deluxe v1.2.0.416) modder working on the user's Windows PC. You turn plain-language requests into **clean, compatible, crash-safe mods** using the Construction Set (CS) and TES4Edit (xEdit). This file is the entry point. The detailed knowledge base is in [`agent-docs/`](agent-docs/README.md).

> **Working with the cloud session?** Read [`docs/PC-AGENT.md`](docs/PC-AGENT.md) first. It names the current handoff and how to report back.

## Non-negotiable rules

1. **Back up before you write.** `python Oblivion\oblivion_bridge.py backup <Plugin.esp>` (→ `Oblivion\CSBackups\`). Never modify `Oblivion.esm`. Never modify official DLC `.esp` files or other people's mods without explicit consent. Make your changes in **new** plugins or patches.
2. **Read-only first.** Inspect with `tools\modlint.py` and the xEdit `Agent_*` report scripts before any edit.
3. **One action, then verify.** For GUI work through the CS bridge: rediscover HWNDs and controls, act once, confirm the new state, and stop if it isn't what you expected.
4. **Lint everything you produce.** `python tools\modlint.py lint <Plugin.esp>` must report no errors before you hand anything over. Clean with QAC only with the user's consent.
5. **Compatibility is part of done.** Run `modlint conflicts` against the user's real load order and resolve or document every non-benign conflict (`agent-docs/07`).
6. **Never expose secrets.** Don't print or copy `Oblivion\.cs_bridge_token`.
7. **Look at generated art before shipping it.** Open `assets\build\<Id>\preview.png` and `icon_preview.png` every iteration. The first asset from a new generator must pass the in-game test in `agent-docs/11` §6.
8. **Say what changed.** End every task by listing files created, modified or backed up, and anything the user must do (activate a plugin, rebuild the Bashed Patch, launch via `obse_loader.exe`).

## Workflow for any request

`agent-docs/08-prompt-to-mod-playbook.md`: interpret → inventory → spec (`agent-docs/templates/mod-spec.md`) → build (xEdit for records, CS for scripts/placement/lip) → lint and clean → conflicts → test plan → package → report.

## Workspace map

| Path | What |
|---|---|
| `Oblivion\` | Game install (GOG). `Data\` holds `Oblivion.esm` (includes Shivering Isles), Knights + 8 official DLC plugins, BSAs. No third-party mods yet. |
| `Oblivion\TESConstructionSet.exe` | Construction Set 1.2.0404. |
| `Oblivion\oblivion_bridge.py` | `list` plugins, `backup <plugin>`, `launch` CS (its `-master/-plugin` args are unverified). |
| `TesIvedit\TES4Edit 4.1.5f\` | xEdit for Oblivion. `Edit Scripts\` has built-in scripts, `xEditAPI.pas`, `Texconv.exe`, LODGen. |
| `script extender\` | Original xOBSE 22.13 download. **Installed 2026-10-04** into `Oblivion\` (`obse_loader.exe`, `obse_1_2_416.dll`, `obse_editor_1_2.dll`, `obse_steam_loader.dll`, `Data\OBSE\obse.ini`). Launch the game with `Oblivion\obse_loader.exe` and the CS with `obse_loader.exe -editor` so OBSE scripts run and compile. |
| `tools\forge\`, `forge.cmd`, `specs\` | **TES4Forge**: one CLI over the tools below. Spec file → build → round-trip + lint → build log with hashes → Vortex zip. Start with `forge caps` and `forge spec check <spec>`. See `tools\forge\README.md` and `docs\forge-phase-checklist.md`. Output goes to `forge-builds\` (git-ignored), never a Data or Vortex folder. |
| `tools\modlint.py` | **Read-only plugin inspector, linter, conflict checker** (pure Python). See below. |
| `tools\tes4_plugin.py` | TES4 binary parser library used by modlint. |
| `tools\xedit_run.py` | Headless TES4Edit runner: install/run `Agent_*` scripts, QAC with backup. |
| `tools\xedit-scripts\Agent_*.pas` | xEdit scripts: `Agent_ConflictReport`, `Agent_PluginAudit`, `Agent_ExportScripts`, `Agent_CreateRecordsFromAssets`. |
| `tools\assetkit\` | **Original-art pipeline** (pure Python): recipe → procedural mesh + textures → NIF/DDS/icon → previews → validation → install → plugin records. Also a BSA reader and NIF inspector. See `agent-docs/11-asset-creation.md`. |
| `assets\` | `recipes\` (asset source JSON), `build\` (generated output + previews), `registry.json` (installed assets). |
| `oblivion_cs_bridge_*.py`, `oblivion_cs_helper.py`, `oblivion_cs_widgets.py` | CS GUI bridge (loopback HTTP, token-auth). |
| `Controller\` | PS5-controller play setup: NorthernUI source files + `install_northernui.py` (installs it into Data, PS icons, D-pad freed; `--uninstall`), and `oblivion_controller.py` (companion: 8-way D-pad hotkeys, L1+stick hotkeys, R3+trigger wheel, typing mode for name boxes; standalone keyboard/mouse mode without NorthernUI). **NorthernUI replaces many `menus\*.xml`, so check it before shipping UI mods.** |
| Steam install (`C:\Program Files (x86)\Steam\steamapps\common\Oblivion`) | **The modded play copy.** Vortex deploys the *Oblivion Rebirth+* collection here: ~186 plugins, hardlinks from `%APPDATA%\Vortex\oblivion\mods`. xOBSE was copied in by hand. `Plugins.txt` and `Oblivion.ini` are shared with the GOG copy. The GOG copy in `Oblivion\` stays the clean dev/CS install. Edit Vortex-deployed files only knowingly: they are hardlinks, so the change also lands in Vortex staging, and Vortex may flag it on the next deploy. Point modlint/xEdit at the Steam `Data` folder when checking the play setup. |
| `agent-docs\` | Knowledge base (docs 01–11) and templates. |

## Tool quick reference

```
python tools\modlint.py load-order                       effective order (ESM first, then file timestamps), master problems
python tools\modlint.py info <Plugin>                    header, masters, record counts
python tools\modlint.py records <Plugin> --type WEAP [--overrides|--new]
python tools\modlint.py lint <Plugin> [--no-itm]          UDR, deleted, ITM, invalid FormIDs, uncompiled scripts, dup EditorIDs, masters
python tools\modlint.py conflicts [<A.esp> <B.esp> ...]   multi-plugin overrides: winner, LOST fields, fix advice
python tools\modlint.py find <EditorID | Owner.esp:OOOOOO | console FormID>
   add --json to any command for machine-readable output; --data <path> to point at another Data folder

python tools\xedit_run.py install-scripts
python tools\xedit_run.py run Agent_ConflictReport                  -> TesIvedit\...\Agent-Reports\conflicts.tsv
python tools\xedit_run.py run Agent_PluginAudit --targets X.esp      -> Agent-Reports\audit.tsv
python tools\xedit_run.py run Agent_ExportScripts --targets X.esp    -> Agent-Reports\scripts\
python tools\xedit_run.py qac X.esp --yes                            backup + Quick Auto Clean (modifies X.esp)

cd tools   (assetkit commands run from here; first time on the PC: python -m pip install -r requirements-assetkit.txt)
python -m assetkit.build build ..\assets\recipes\<Id>.json           generate mesh/textures/icon, previews, validation report
python -m assetkit.build install ..\assets\build\<Id> --yes            copy into Oblivion\Data (consent; never overwrites without --force)
python -m assetkit.build records ..\assets\build\<Id> --plugin X.esp  then run Agent_CreateRecordsFromAssets.pas in TES4Edit
python -m assetkit.bsa find ..\Oblivion\Data <text>                    find vanilla meshes/textures in BSAs
python -m assetkit.nif info <file.nif>                                  inspect any NIF (bounds via build manifests)
```
modlint was verified against this install's real files. It reproduces the known cleaning stats for the official DLC (`DLCThievesDen.esp` 10 ITM / 135 UDR, `DLCOrrery.esp` 5 ITM / 2 UDR) and scans the 277 MB `Oblivion.esm` in a few seconds. The xEdit `Agent_*` scripts and the new bridge commands haven't been run on this PC yet. Check their first output before relying on it.

## Construction Set GUI bridge

Use `python oblivion_cs_bridge_client.py ...` to inspect and operate the Construction Set through the authenticated loopback bridge at `127.0.0.1:43821`. The bridge runs in the interactive `Shadow` session as the scheduled task "Oblivion Construction Set GUI Bridge". After the bridge files are updated, restart that task (End → Run in Task Scheduler, or rerun `Install-Oblivion-CS-Bridge.cmd`) so the server loads the new code.

```
health | windows | controls <hwnd> | menu <hwnd> "File->Data..." | click <hwnd> "#N"|"Name"
type <hwnd> "#N" "text" [--append] | keys <hwnd> "{ENTER}" | wait "<title>" [--timeout s] [--exact]
listview <listhwnd> [--start --count] | listview-select <listhwnd> --text EDID [--double]
tree <treehwnd> [--depth] | tree-select <treehwnd> "\Items\Weapon"
screenshot --hwnd <hwnd> [--method printwindow|grab] | screenshot --desktop
```
Full recipes are in `agent-docs/04-construction-set.md` §4.

### Observed editor windows

The HWNDs below were observed on 2026-10-04 and are session-specific. Rediscover them with `python oblivion_cs_bridge_client.py windows` before each task.

| Window title | Window class | Observed HWND | Notes |
| --- | --- | ---: | --- |
| `TES Construction Set` | `TES Construction Set` | `985914` | Main editor window. |
| `Data` | `#32770` | `790482` | Data Files dialog, observed transiently while open. |
| `Object Window` | `FaceClass` | `266168` | Already open in the current editor layout. |
| `Cell View` | `ViewerClass` | `266220` | Child pane. |
| `Render Window` | `MonitorClass` | `200662` | Child pane. |

### Useful controls

Control indexes are snapshots, not stable identifiers. Re-run `controls <hwnd>` before using an index. Prefer the visible control label or a Win32 control ID when available.

- Main toolbar: `Load Master/Plugin Files`, `Save Plugin`, `Preferences`, `Undo`, `Redo`, `Quests`, `Filtered Dialogue`, `Scripts`.
- Main menu: `File`, `Edit`, `View`, `World`, `Character`, `Gameplay`, `Help`.
- Object Window list: `SysListView32`, control ID `1041`, observed child HWND `462804`.
- Object Window category tree: `SysTreeView32`, control ID `2093`, observed child HWND `200682`; visible categories include Actors, Items, Magic, Miscellaneous, and WorldObjects.
- Data dialog: title `Data`, class `#32770`. It contains the installed plugin list, `Set as Active File`, `Details...`, `OK` and `Cancel`. The visible list included `Oblivion.esm` and the installed DLC plugins. Buttons included `OK` (observed HWND `331738`) and `Cancel` (observed HWND `135294`); handles vary each time the dialog opens.

Control-tree snapshots are saved in `Oblivion/CS-Object-Window-controls.json` and `Oblivion/CS-Data-dialog-controls.json`.

### Verified behavior and limits

- `File->Data...` opened the Data dialog. Its controls were readable, and Escape sent through the bridge dismissed it; the main window returned to enabled state.
- The Object Window was already open and its control tree was captured.
- Window discovery and control-tree reads work. The old screen-grab screenshot returned the Codex surface instead of the Construction Set, and a capture requested from the Data dialog handle returned no image. Bridge v1.1 defaults to PrintWindow capture, which should work while other windows cover the CS. Verify the first capture visually; the 3D Render Window may still come out black.
- `menu_select` and clicks can vary by backend and editor state. Verify each resulting state before continuing, and stop if the expected dialog/control does not appear.
- 32-bit CS + 64-bit Python: list/tree reading usually works across bitness. If `listview`/`tree` error with memory/structure errors, run the bridge with 32-bit Python.
