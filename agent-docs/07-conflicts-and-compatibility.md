# 07 · Conflicts, compatibility and crash prevention

Your job isn't done when the mod works alone. It's done when it **works in the user's load order** and **fails safely** when something it expects is missing.

## 1. The Rule of One and its exceptions

- Two plugins overriding the same record: **the later-loaded one's whole record wins.** No field merging.
- The engine merges **INFOs within a DIAL topic** (each INFO is its own record), so adding dialogue to GREETING doesn't conflict. *Editing the same INFO* does.
- Everything else needs merging by tools: the **Wrye Bash Bashed Patch** (leveled lists, plus tag-driven field merging for NPCs, creatures, containers, cells, names, stats, etc.), or a **hand-made compatibility patch** in TES4Edit.

## 2. Conflict classes, ranked by how much they hurt

| Severity | Record types | What breaks | Resolution |
|---|---|---|---|
| **Critical** | `SCPT` (vanilla script replaced), `QUST`, `WRLD`, `LAND`, `PGRD` | Quests stall, other mods' script logic disappears, terrain seams/floating objects, NPCs stuck or walking through new buildings | Hand-reconcile. For scripts, merge source line by line keeping variable order, then recompile. For LAND/PGRD, build a dedicated patch in the CS (redo the pathgrid for the combined layout). |
| **Merge** | `LVLI`, `LVLC`, `LVSP` | Items or creatures from one mod never spawn | Bashed Patch (plugin tags `Delev`/`Relev`), or runtime injection with xOBSE `AddToLeveledList` (no record override at all) |
| **Patch** | `NPC_`, `CREA`, `CONT`, `CELL`, `RACE`, `INFO`, `REFR`/`ACHR`/`ACRE`, items, `REGN` | One mod's stats/inventory/faction/AI/cell lighting/ownership changes vanish | Bashed Patch tags, or an xEdit patch forwarding each intended field (`05-tes4edit.md` §4) |
| **Low** | `GMST`, `GLOB`, `DIAL` header | Last value wins; usually intended | Confirm intent; document the setting |
| **Benign** | Identical overrides, ITMs | Nothing, unless the ITM wins over a real edit (orange in xEdit) | Clean ITMs (QAC) |

## 3. Detecting conflicts (do all three before you call a mod done)

```
python tools\modlint.py load-order                      # missing/inactive/late masters, >255, timestamp ties
python tools\modlint.py lint MyMod.esp                  # UDR, deleted records, ITM, invalid FormIDs, uncompiled scripts, dup EDIDs
python tools\modlint.py conflicts                       # every record 2+ non-official plugins override, with LOST fields
python tools\modlint.py conflicts MyMod.esp OtherMod.esp --min-severity patch
python tools\xedit_run.py run Agent_ConflictReport      # xEdit's authoritative field-aware status
```
`modlint conflicts` compares subrecords byte by byte. Because FormIDs inside a field are file-relative, plugins with **different master lists** can show false "lost" FormID fields. Confirm in TES4Edit (Agent_ConflictReport, or visually) before building a patch.

## 4. Designing for compatibility from the start (choose the least invasive technique)

1. **Add, don't change.** New records (new items, NPCs, cells, quests) never conflict. New INFOs in shared topics don't conflict.
2. **Inject instead of override.** Leveled lists: xOBSE `AddToLeveledList` at `GetGameRestarted`. Containers: script `AddItem` into a persistent container once (`DoOnce`), rather than overriding the CONT record. Spells: `AddSpell` via quest script, rather than editing NPC records.
3. **New references over edited references.** Place your own objects. If a vanilla object is in the way, **disable** it (initially-disabled flag) instead of deleting or moving it. Moving it collides with UOP and other cell mods.
4. **Touch the fewest fields and the fewest records.** Every override is a future conflict. After building, run `modlint lint` and clean ITMs.
5. **Avoid the hot zones** unless that's the mod's purpose: Imperial City districts, Chorrol/Bravil/Anvil exteriors, roads (Unique Landscapes, Better Cities and Open Cities all edit these), Weye, the Arcane University, vanilla merchants' inventories, `GREETING` conditions, and vanilla quest scripts.
6. **Soft dependencies.** Integrate with optional mods through `IsModLoaded` + `GetFormFromMod` instead of adding masters. Masters are hard requirements: a missing master = no game start.
7. **Ship patches as separate plugins** (`MyMod - UOP Patch.esp`), each with exactly the masters it patches.
8. **Bash tags.** Put `{{BASH:Delev,Relev,Invent,...}}` in the plugin description (the TES4 `SNAM`) so Wrye Bash knows which fields to forward. `Edit Scripts\BASH tags autodetection.pas` suggests tags.
9. **Respect the Unofficial Patches.** If the user has UOP/USIP/UOMP, base vanilla overrides on the **UOP-fixed values** (copy the winning override in xEdit), or the mod reintroduces bugs.

## 5. Reconciling code (scripts) between mods

When two mods replace the same vanilla script (or your mod needs to change one another mod changed):

1. Export both versions: `python tools\xedit_run.py run Agent_ExportScripts --targets ModA.esp ModB.esp Oblivion.esm`.
2. Diff each version against vanilla and list each mod's intent (e.g. "A adds a gold reward at stage 50; B skips the escort").
3. Write a merged version that:
   - keeps **every vanilla variable** in vanilla order, then A's added variables, then B's (append-only);
   - includes both behaviours, guarded so each runs only when its mod is present (`if IsModLoaded "ModB.esp"`, xOBSE) when the patch should work with either;
   - doesn't break quest-stage contracts (stage numbers other mods call with `SetStage`).
4. Put it in a patch plugin that masters both mods. Compile in the CS **with both mods loaded as masters** (ESM-flag trick or CSE). Then run `modlint lint` (`SCRIPT_NOT_COMPILED` must be absent).
5. Test the quest path in game with console commands (`10-testing-and-release.md`).

## 6. Crash and breakage catalogue (cause → prevention)

| Symptom | Common cause | Prevention / fix |
|---|---|---|
| CTD at startup, before main menu | Missing master; master after dependent; >255 plugins; corrupt plugin | `modlint load-order` |
| CTD on loading a save or entering a cell | UDR/deleted record that the save or another mod references; bad NIF in that cell; script on a deleted ref | `modlint lint` → QAC; NifSkope check of new meshes |
| CTD when an NPC/creature appears | Bad NIF/skeleton, missing race/hair/eyes record, invalid AI package target | `Check for errors` in xEdit; verify assets exist |
| Item/NPC shows a red "!" (missing mesh) or is invisible | Wrong mesh path, BSA not loaded, loose file not invalidated | Paths relative to `meshes\`; ArchiveInvalidation |
| Purple/pink textures | Missing texture or wrong path | Paths relative to `textures\` |
| Quest stalls | Conflicting QUST/SCPT/INFO; a non-persistent ref used by a script; stage set too early | Conflict report; persistent refs; test with `SetStage` |
| Features silently missing | Load order lets another mod win; leveled lists not merged; ITM revert | `modlint conflicts`; Bashed Patch; clean ITMs |
| Stutter growing over time | Per-frame scripts, PlaceAtMe spam, havok piles | Script guards; reuse refs |
| Old save broken after updating the mod | Removed or reordered script variables, renumbered FormIDs, changed quest stage logic | Append-only variables; never renumber released FormIDs; write an update handler (`GetGameLoaded` + version global) |
| "Mod doesn't work" with xOBSE functions | Game not launched via `obse_loader.exe`; xOBSE not installed; wrong version | Version guard (`GetOBSEVersion`); install docs |

## 7. Load-order rules of thumb

Official files first (`Oblivion.esm`, then DLC in the official order), then unofficial patches, then large overhauls, then quests and locations, then smaller tweaks, then compatibility patches, and finally the Bashed Patch last. LOOT handles this. Oblivion orders plugins by **file timestamp**: changing a file's modified time changes its load position, and copying a plugin can change its timestamp. Mention this when you install plugins for a user.
