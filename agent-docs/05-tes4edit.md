# 05 · TES4Edit (xEdit 4.1.5f): expert use and automation

Location: `TesIvedit\TES4Edit 4.1.5f\TES4Edit.exe`. It's the same binary as all xEdits, and the filename `TES4Edit.exe` (or `-TES4`) selects Oblivion mode. `TES4EditQuickAutoClean.exe` is the same exe; its name starts it in QAC mode.

TES4Edit is the precision tool. Use it to **inspect conflicts, clean plugins, build patches, copy records, set flags and masters, and batch-edit with Pascal scripts.** It **can't compile scripts** (it edits `SCTX` source text but not `SCDA` bytecode), generate lip files, or edit landscape visually.

## 1. Command line (verified against this version's `whatsnew.md`)

```
TES4Edit.exe -TES4 [options]
  -D:"<Data path>\"          data folder (we pass ..\Oblivion\Data\ - avoids registry lookup issues on GOG)
  -P:"<path>\plugins.txt"    alternative active-plugin list
  -autoload                  skip the module-selection dialog, load everything active in plugins.txt
  -quickedit:<Plugin.esp>    preselect only that plugin + its masters (combine with -autoload)
  -script:"<Name.pas>"       run Edit Scripts\<Name.pas> automatically after loading
  -autoexit                  close when the script / QAC / LODGen finishes
  -quickautoclean <Plugin>   QAC: Undelete+disable refs, remove ITMs, repeated 3x, saves each pass
  -quickshowconflicts / -veryquickshowconflicts   open straight into conflict view
  -IKnowWhatImDoing          suppress the edit-warning dialog, unhide advanced functions
  -AllowMasterFilesEdit      (with the above) allow editing .esm files - never on Oblivion.esm
  -nobuildrefs               skip building "Referenced By" (faster; ReferencedBy* functions return 0)
  -O:"<path>"                LODGen output folder
  -cp-trans:<codepage>, -l:<language>
```
`tools\xedit_run.py` wraps this:
```
python tools\xedit_run.py install-scripts                         copy Agent_*.pas into Edit Scripts
python tools\xedit_run.py run Agent_ConflictReport                 -> Agent-Reports\conflicts.tsv
python tools\xedit_run.py run Agent_PluginAudit --targets MyMod.esp -> Agent-Reports\audit.tsv
python tools\xedit_run.py run Agent_ExportScripts --targets MyMod.esp -> Agent-Reports\scripts\*.txt
python tools\xedit_run.py qac MyMod.esp --yes                       backup to Oblivion\CSBackups then QAC
python tools\xedit_run.py cmdline Agent_PluginAudit                 print the command without running
```
Headless runs still open a TES4Edit window. If it never exits, it's waiting on a dialog: a missing master, a plugin that isn't active, or an error. Tell the user. `-autoload` uses `%LOCALAPPDATA%\Oblivion\Plugins.txt`, so **the plugin you want must be active.**

## 2. Reading xEdit's conflict colors

| Row background (record) | Meaning |
|---|---|
| White | Only one version |
| Green | Override identical to master (ITM), or no conflict |
| Yellow | Override without competing overrides (normal mod edit) |
| Red | Conflict: 2+ overrides differ, a later one wins, losers' edits lost |
| Fuchsia | Critical conflict (e.g. deleted vs overridden, identical-to-master winning over a real edit) |

| Text color (column) | Meaning |
|---|---|
| Green | Wins the conflict |
| Red | Loses the conflict |
| Orange | Identical to master **but wins** the conflict: an ITM that reverts another mod's edit (the typical "my mod stopped working" bug) |
| Gray | Identical to master |
| Purple | Master record |

Workflow: select the plugins → right-click → **Apply Filter for Cleaning** (or *Apply filter to show Conflicts*) → walk the red rows.

## 3. Cleaning (do it for every plugin you produce)

1. `tools\modlint.py lint MyMod.esp` lists UDRs, ITMs, deleted records, missing masters and uncompiled scripts.
2. QAC: `tools\xedit_run.py qac MyMod.esp --yes`. It undeletes and disables UDRs (Z −30000, initially disabled) and removes ITMs; xEdit also writes its own backup to `Data\TES4Edit Backups\`.
3. Re-lint. Remaining **deleted non-reference records** and **deleted navigation (PGRD) data** need manual fixes: restore the record and neutralise it (empty its lists, disable it).
4. **Never clean `Oblivion.esm`.** Official DLC .esp files have known ITMs/UDRs (`DLCThievesDen.esp`: 10 ITM / 135 UDR; `DLCOrrery.esp`: 5 ITM / 2 UDR, found by modlint here). LOOT advises cleaning them, but only with the user's consent and a backup.
5. Some ITMs are **intentional** (to revert another mod's change, or to keep a record "in" a plugin for a Bashed Patch tag). When a mod's documentation says so, keep them: `qac` removes all ITMs.

## 4. Building a compatibility patch in xEdit (the standard procedure)

1. Load the conflicting plugins (+ masters). Filter for conflicts.
2. For each red record: right-click the **winning** version → *Copy as override into...* → new file `MyMod - ModB Patch.esp`. xEdit adds the masters automatically.
3. In the patch's column, drag or copy the losing plugin's intended values field by field (inventory items, leveled-list entries, flags, AI data). The result should contain **every intended edit from both mods**.
4. Leveled lists: merge entries (union), not overwrite. A Bashed Patch does this automatically for every list; a manual patch is for exceptions.
5. The patch loads **after** both mods. Masters must include both (that's the point: it's useless without them).
6. Run `Check for Errors` (right-click the file) and `modlint lint` on the patch.

## 5. Pascal scripting (Edit Scripts\*.pas)

Template (from `_newscript_.pas`):
```pascal
unit userscript;
function Initialize: integer; begin Result := 0; end;      // once, before processing
function Process(e: IInterface): integer; begin Result := 0; end; // per selected record
function Finalize: integer; begin Result := 0; end;        // once, after
end.
```
`Result := 1` in `Initialize` stops the run after Initialize, which is how the `Agent_*` scripts work headless: they loop over `FileCount`/`RecordCount` themselves.

Functions you'll use constantly (the full list is in `Edit Scripts\xEditAPI.pas`):

| Purpose | Functions |
|---|---|
| Files | `FileCount`, `FileByIndex(i)`, `FileByLoadOrder(lo)`, `GetFileName(f)`, `MasterCount(f)`, `MasterByIndex(f,i)`, `AddNewFile`, `AddNewFileName(name)`, `AddMasterIfMissing(f, 'X.esp')`, `AddRequiredElementMasters(e, f, False)`, `CleanMasters(f)`, `SortMasters(f)`, `GetIsESM`/`SetIsESM` |
| Records | `RecordCount(f)`, `RecordByIndex(f,i)`, `RecordByFormID(f, id, True)`, `MainRecordByEditorID(GroupBySignature(f,'WEAP'), 'IronLongsword')`, `Signature(e)`, `EditorID(e)`, `FormID(e)`, `GetLoadOrderFormID(e)`, `FileFormIDtoLoadOrderFormID(f,id)` |
| Override chain | `IsMaster(e)`, `Master(e)`, `MasterOrSelf(e)`, `OverrideCount(m)`, `OverrideByIndex(m,i)`, `WinningOverride(e)`, `HighestOverrideOrSelf(e, lo)`, `IsWinningOverride(e)` |
| Conflict status | `ConflictAllForMainRecord(e)` → `caNoConflict … caConflictCritical`; `ConflictThisForMainRecord(e)` → `ctIdenticalToMaster`, `ctConflictWins`, `ctConflictLoses`, …; `ConflictAllForElements(e1, e2, False, False)` |
| Fields | `ElementByPath(e, 'DATA\Damage')`, `ElementBySignature(e,'EDID')`, `GetElementEditValues(e, path)`, `SetElementEditValues(e, path, v)`, `GetElementNativeValues`/`SetElementNativeValues`, `ElementCount`, `ElementByIndex`, `Add(e, 'Items', True)`, `ElementAssign(list, HighInteger, nil, False)`, `Remove`, `RemoveNode` |
| Copying | `wbCopyElementToFile(e, f, False{asNew}, True{deepCopy})`; `wbCopyElementToFileWithPrefix` for renamed copies |
| References | `ReferencedByCount(e)`, `ReferencedByIndex(e,i)` (need refs built: no `-nobuildrefs`), `BaseRecord(ref)`, `GetPosition`, `wbFindREFRsByBase` |
| Flags/state | `GetIsDeleted`/`SetIsDeleted`, `GetIsPersistent`/`SetIsPersistent`, `GetIsInitiallyDisabled`/`SetIsInitiallyDisabled` |
| Output | `AddMessage(s)`, `TStringList.SaveToFile(ProgramPath + 'Agent-Reports\x.txt')` |
| Validation | `Check(e)` returns an error string (recurse over children, as in `Check for errors.pas`) |

**Field paths** are the labels xEdit shows, e.g. `DATA\Value`, `DATA\Weight`, `Items\Item\CNTO\Item`, `Leveled List Entries\Leveled List Entry\LVLO\Reference`, `SCRI`, `FULL`, `MODL\MODL`. Open the record in the GUI to confirm a path before scripting it. Paths differ between record types and between xEdit versions.

**Patch-generation script pattern** (safe, re-runnable):
```pascal
unit userscript;
var patch: IInterface;
function Initialize: integer;
begin
  patch := AddNewFileName('MyMod - Rebalance.esp');   // new file, never edit sources
  AddMasterIfMissing(patch, 'Oblivion.esm');
end;
function Process(e: IInterface): integer;
var r: IInterface;
begin
  if Signature(e) <> 'WEAP' then Exit;
  e := WinningOverride(e);                 // start from the winner -> keep other mods' edits
  AddRequiredElementMasters(e, patch, False);
  r := wbCopyElementToFile(e, patch, False, True);
  SetElementNativeValues(r, 'DATA\Damage', GetElementNativeValues(r, 'DATA\Damage') * 1.2);
end;
end.
```
Copy the **winning** override, not the master, so your patch keeps upstream edits. That's the single most important compatibility habit.

Headless edits: when a script modifies or creates a plugin, xEdit asks which files to save when it closes, and that dialog blocks `-autoexit`. Run editing scripts **with the user watching** (or have the user click Save), then confirm the output file's timestamp and lint it. Don't point editing scripts at the user's existing plugins. Generate **new** patch files.

## 6. Other built-in scripts worth knowing (`Edit Scripts\`)

`Check for errors.pas`, `Conflict Status.pas`, `List master references.pas`, `List records referencing specific plugin.pas`, `Remove identical to previous override records.pas` (ITPO, for generated patches only), `Undelete and Disable References.pas`, `Change load order of FormID.pas` / `Renumber FormID.pas` (dangerous: breaks saves and dependents), `Oblivion - Export all scripts in xml format.pas`, `Oblivion - Export Dialogues.pas`, `Oblivion - Items lookup replacement.pas`, `BASH tags autodetection.pas` (suggests Wrye Bash tags for a plugin), `Merge overrides into master.pas`, `Find records.pas`, `ExportImportTexts.pas`. `Texconv.exe` is in the same folder.

## 7. Other xEdit facts

- xEdit sorts INFOs and fixes some record formats on load ("fixups"). If you see changes you didn't make, that's why. `-nofixup`/`-hidefixup` exist.
- Saving writes `<name>.esp.save.<date>` and renames on exit. If xEdit crashes, the original is intact.
- xEdit can't load more plugins than the game (255).
- Editing values: a FormID field accepts `[XX]OOOOOO` load-order IDs or EditorIDs when typed in the GUI. In scripts, set FormIDs with `SetEditValue(el, IntToHex(GetLoadOrderFormID(target), 8))` or `SetNativeValue(el, GetLoadOrderFormID(target))`.
