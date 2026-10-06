# 10 · Testing, debugging and release

## 1. Static checks (always, in this order)

```
python tools\modlint.py lint MyMod.esp                 # must exit 0 (no errors)
python tools\modlint.py conflicts MyMod.esp <each mod it should coexist with>
python tools\xedit_run.py run Agent_PluginAudit --targets MyMod.esp   # xEdit Check-for-errors + ITM/UDR/LOSES
python tools\modlint.py load-order                     # user's order still valid
cd tools && python -m assetkit.build validate ..\assets\build\<Id>   # every generated asset: must PASS
```

## 2. In-game test via console (`~`)

Launch through `obse_loader.exe` if the mod uses xOBSE. Test on a **new game or a throw-away save**, never the user's main save.

| Command | Use |
|---|---|
| `coc <CellEditorID>` | Teleport to an interior or exterior cell (`coc ChorrolCastle`; `coc testinghall` for the dev hall) |
| `player.additem <FormID> <n>` | Give item (console needs the **load-order** FormID: `modlint find <EditorID>` shows `Owner:OOOOOO`; the console form is `<LO index><OOOOOO>`) |
| `player.placeatme <FormID> 1` | Spawn an actor/object (test only; creates FF refs) |
| `help <text>` | (OBSE-enhanced in xOBSE) search forms by name |
| `prid <refID>` / click a ref | Select a reference |
| `getstage <Quest>` / `setstage <Quest> <n>` / `sqv <Quest>` | Inspect and drive quests; `sqv` shows quest variables |
| `startquest` / `stopquest` | |
| `tai` / `tcai` / `tdetect` | Toggle AI / combat AI / detection |
| `tgm` / `tcl` / `tmm 1` | God mode / no-clip / show all map markers |
| `set <Global> to <v>` | Change globals |
| `getav <AV>` / `setav` / `modav` | Actor values |
| `sexchange`, `showracemenu` | Appearance tests |
| `con_SCOF <file>` (xOBSE) | Log console output to a file for review |

Write the test plan as console steps plus the expected observation, e.g. "`coc MMHouseInterior` → the chest `MMHouseChest` contains 3 `MMRuby`; after 3 in-game days (`set gamehour to …` / wait) it still contains 3 (non-respawning)."

## 3. Debugging crashes

1. Reproduce with only the official files + the mod (disable everything else) → is the mod itself at fault?
2. Bisect the load order (halves) when it's an interaction.
3. Check `modlint lint` for UDRs, deleted records and missing masters, and Agent_PluginAudit for `ERROR` rows (unresolved FormIDs).
4. For cell-entry crashes, try `coc` into the cell with `tcl` off, then disable suspect refs one at a time in a test copy of the plugin.
5. Mesh suspicion: swap the record's `MODL` for a vanilla mesh; if the crash disappears, fix the NIF.
6. Script suspicion: add `PrintC` traces (xOBSE) or `Message` lines; check that refs aren't 0 before use.
7. xOBSE crash logs: `obse.ini` `[Runtime] bCreateCrashDump=1` writes minidumps (it's 0 in the provided ini).

## 4. Packaging and release

```
MyMod\
  MyMod.esp
  MyMod.bsa                  (optional; or loose meshes\ textures\ sound\ folders)
  Docs\MyMod Readme.txt
  (optional) BAIN layout: 00 Core\, 10 Optional UOP Patch\, ...
```
Readme must include: requirements (exact: "Oblivion GOTY/1.2.0.416, xOBSE 22+" etc.), install and uninstall instructions, load order advice + Bash tags, **every vanilla record overridden**, known conflicts and patches, save-safety notes, changelog, credits and permissions for third-party assets.

Version bumps: keep FormIDs and EditorIDs stable, keep script variables append-only, and record a `MMVersion` global plus an update routine (`GetGameLoaded` → compare → migrate) so old saves upgrade cleanly.

Use `templates/release-checklist.md` before handing anything to the user.
