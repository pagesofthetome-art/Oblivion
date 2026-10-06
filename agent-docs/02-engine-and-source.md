# 02 · Engine internals and "source code"

## 1. What source exists (and what doesn't)

- **Bethesda has never released Oblivion's or Gamebryo's source code.** Don't claim to "read the source." What you *can* rely on:
  1. **xOBSE source** (github.com/llde/xOBSE, GPL). Reverse-engineered C++ class layouts for the engine: `GameForms.h` (TESForm and subclasses), `GameObjects.h` (TESObjectREFR, Actor, PlayerCharacter), `GameExtraData.h` (ExtraDataList), `GameTasks.h`, `Script.h` / `ScriptUtils.cpp` (the compiler and bytecode), `GameAPI.cpp` (console and script runner hooks), `Hooks_*.cpp` (exactly where OBSE patches the exe). This is the nearest thing to engine source, and the authority on how forms, scripts and references behave in memory.
  2. **xEdit record definitions** (`wbDefinitionsTES4.pas` in the TES5Edit GitHub repo). The authoritative field-by-field layout of every Oblivion record type, including flags, enums and FormID-bearing fields.
  3. **UESP** `Oblivion_Mod:File_Format` and `Oblivion_Mod:Mod_File_Format/*` (record formats), plus the **CS Wiki** mirror at cs.uesp.net (script functions, CS usage, engine quirks).
  4. Local docs in this workspace: `script extender\obse_command_doc.html` (every xOBSE command with syntax) and `script extender\obse_whatsnew.txt` (version history, including fixes for engine bugs).
- When you need engine behaviour that none of these document, say so. Then design a test (a test plugin plus console checks), not a guess.

## 2. Architecture in one page

```
Oblivion.exe (32-bit, Gamebryo 2.x renderer + Bethesda game layer, Havok physics, SpeedTree, FaceGen, Bink)
├─ Data handler (TESDataHandler): loads ESM/ESP in load order into in-memory TESForm objects
│    every record -> one TESForm subclass (TESObjectWEAP, TESNPC, TESQuest, Script, TESObjectCELL ...)
│    later plugins REPLACE whole records (no field merging) -> "Rule of One"
│    exceptions merged by the engine: INFOs within a DIAL topic and a few lists built at runtime
├─ Archive layer: BSA (v103) + loose files; loose files override BSAs if ArchiveInvalidation is set up
├─ Cell manager: uGridsToLoad (default 5) exterior grid around the player + current interior
│    references (REFR/ACHR/ACRE) are loaded and unloaded with their cell; persistent refs are always in memory
├─ Script runner: compiled bytecode (SCDA) is executed by the engine; source text (SCTX) is only for the CS
│    object scripts run on the object's frame tick while its cell is loaded; quest scripts every fQuestDelayTime (default 5 s)
│    magic-effect scripts: ScriptEffectStart/Update/Finish
├─ AI: process levels (High/Middle-High/Middle-Low/Low) by distance; packages are re-evaluated on schedule/conditions
├─ Save system (.ess): stores CHANGES to forms keyed by FormID (change flags), script variables, ref positions, created forms (FF xxxxxx)
└─ OBSE / xOBSE (obse_1_2_416.dll) injected by obse_loader.exe: hooks the script compiler/runner, adds commands,
     strings and arrays (save co-file .obse), event handlers
```

## 3. Facts that drive mod design

**FormIDs and load order**
- In memory, a FormID is `LL OOOOOO`: load-order index + 24-bit object ID. In a plugin file, the top byte is an index into that file's own master list, and the engine remaps it on load. **Remapping is why masters must stay present and in the right order.**
- Load order is ESM-flagged files first, then the rest, each sorted by **file modification time**. `Plugins.txt` only says *which* files are active. Max 255 plugins (`00`–`FE`). `FF` is reserved for runtime-created forms (spells made at the altar, dropped items, `PlaceAtMe` results).
- The save stores each change against `LL OOOOOO`. When a plugin's index shifts, the save remaps by plugin name. When a plugin disappears, every form from it is dropped, and so are references and inventory items that used it. That's the cause of "my items vanished."

**Records replace, they don't merge**
- If two plugins override the same NPC, the later one's **entire record** wins. A level change in mod A plus an inventory change in mod B means one of them is lost. This is the whole reason for Bashed Patches and compatibility patches.

**References and cells**
- Placed objects are records (`REFR`/`ACHR`/`ACRE`) inside a CELL's children group. Persistent refs (flag `0x400`, required for anything a script or package targets by EditorID) live in the persistent group and stay in memory.
- **Deleting** a vanilla reference (UDR) leaves the engine looking up a missing form when another plugin or the save refers to it. The result is a crash. Always **disable** instead: set *Initially Disabled* and move it to Z −30000. xEdit's QAC does exactly this.
- Exterior landscape (`LAND`), pathgrids (`PGRD`), and region/LOD data are per cell. Two mods editing the same cell's LAND or PGRD can't both win.

**Scripts**
- Scripts compile in the CS to bytecode. **Variable references are stored by index**: local variable *N* of script X, quest variable by index. If you reorder, remove or insert variables in a script other mods or saves rely on, references point at the wrong slots. Always **append** new variables at the end.
- Objects can carry exactly one script (`SCRI`). Adding behaviour to a vanilla object by replacing its script breaks every other mod that does the same. Prefer a separate quest script or an xOBSE event handler.
- `GameMode` blocks run every frame for loaded objects. Heavy loops there cause stutter. Gate them with timers or `DoOnce` flags.
- Quest scripts run only while the quest is running (`StartQuest`). Their delay is `fQuestDelayTime` (`SetQuestDelay` inside the script).

**Memory and stability**
- The exe is 32-bit. Without the 4GB/Large Address Aware patch it's limited to 2 GB. Big texture packs plus high `uGridsToLoad` give out-of-memory crashes. Never raise `uGridsToLoad` in a mod's instructions; it breaks scripts and LOD and causes CTDs.
- Known crash triggers: missing masters, UDRs, a deleted form referenced by a list or script, NIFs with bad collision or controllers, textures with wrong formats/mipmaps (rare CTD, mostly purple/black), too many active scripts on one frame, `PlaceAtMe` spam (save bloat), havok-settled objects in big piles, NPCs without valid AI in combat, a `Disable` on the player, `ResetQuest` on running main-quest scripts.

## 4. How xOBSE changes the rules

- xOBSE only takes effect when the game starts through **`obse_loader.exe`** (or a launcher configured to use it), and the CS through **`obse_loader.exe -editor`**. Without the editor hook, OBSE commands fail to compile in the CS.
- With xOBSE: string variables (`string_var`), arrays (`array_var`), user-defined functions (`Function {args}` + `Call`), event handlers (`SetEventHandler "OnHit" ...`), `Let`/`eval` expression syntax, loops (`While`/`ForEach`/`Loop`), cross-mod soft dependencies (`IsModLoaded`, `GetModIndex`, `GetFormFromMod`) and many get/set commands for form data at runtime.
- Runtime form edits made by OBSE `Set*` commands (e.g. `SetAttackDamage`) are **not saved**: they apply to the base form in memory and must be reapplied on every game load (`GetGameLoaded`, `GetGameRestarted`).
- xOBSE settings: `Data\OBSE\obse.ini`. The one in `script extender\Data\OBSE\` turns on `bWarningUnquotedString`, `bWarningUDFRefVar`, `bQueueEnabledRef`, `bDeallocateReferences` and `bWriteAllRefInventoryReference`.
- Always look up exact command syntax in `script extender\obse_command_doc.html`. Grep it, don't recall it.

## 5. Where engine behaviour is tunable without code

- **GMSTs** (`GMST` records): combat, magic, barter, leveling, AI and UI constants. They apply engine-wide and the last plugin wins. Always tell the user which GMSTs you changed.
- **INI** (`Oblivion.ini`): rendering, memory, grids, archives (`SArchiveList`), `bInvalidateOlderFiles`. INI changes aren't part of a plugin; put them in installation instructions.
- **Globals** (`GLOB`): `TimeScale`, `GameHour`, and mod-defined switches. They're saved in the savegame, so a plugin's value only applies to new games unless a script sets it.
