# 06 · Oblivion scripting (vanilla + xOBSE)

Always check command syntax in `script extender\obse_command_doc.html` (it covers vanilla-relevant xOBSE commands, events and expression syntax) and in the CS Wiki (cs.uesp.net) for vanilla functions. **Grep before you write.** A wrong parameter type is a compile error at best and a silent runtime failure at worst.

## 1. Script anatomy

```
scn MyModChestScript            ; ScriptName - must be unique (it's the EditorID)
short doOnce                    ; variables: short, long, float, ref; xOBSE adds string_var, array_var
ref  target

Begin OnActivate                ; block type; most take an optional ActionRef/param
    if IsActionRef player == 1
        Message "The chest hums."
        Activate                ; perform default activation (else activation is blocked)
    endif
End

Begin GameMode                  ; every frame while the object's cell is loaded (quest: every delay tick)
    if doOnce == 0
        set doOnce to 1
    endif
End
```
**Block types (vanilla):** `GameMode`, `MenuMode [menuType]`, `OnActivate`, `OnAdd`, `OnDrop`, `OnEquip`, `OnUnequip`, `OnActorEquip`, `OnHit`, `OnHitWith`, `OnDeath`, `OnMurder`, `OnKnockout`, `OnAlarm`, `OnStartCombat`, `OnPackageStart/Change/Done/End`, `OnLoad`, `OnMagicEffectHit`, `OnReset`, `OnSell`, `OnTrigger`, `OnTriggerActor`, `OnTriggerMob`, `ScriptEffectStart/Update/Finish`. Only the blocks valid for the script's type and object compile or run.

## 2. Script types and where they attach

| Type | Attach to | Runs |
|---|---|---|
| Object | `SCRI` field of ACTI, CONT, DOOR, NPC_, CREA, items, etc. One script per object. | While the object (reference) is loaded; inventory items run while in a loaded container/actor |
| Quest | QUST's script field | While the quest runs, every `fQuestDelayTime` (default 5 s; `SetQuestDelay MyQuest 0.1` for faster) |
| Magic Effect | `SEFF` effect in SPEL/ENCH/ALCH | On the target for the effect's duration |
| Result scripts | Quest stages, INFOs, AI package ends | Once, when fired. No variables of their own (use quest vars) |

## 3. Rules that prevent breakage

1. **Unique names, with a prefix.** Every EditorID you create starts with your mod's prefix (`MMCS…` for "MyMod Chest System"). That prevents collisions with other mods' EditorIDs. Duplicate EditorIDs make scripts compile against the wrong form.
2. **Never reorder or remove variables** in a released script. Append new ones at the end. Variables compile to indexes stored in saves and in other scripts.
3. **Don't edit vanilla scripts** unless the mod's purpose is to fix them. If you must, start from the **UOP version** when UOP is in the user's load order. Reconcile line by line and keep every vanilla variable in its original order.
4. **Don't attach new scripts to vanilla base objects** that may already have one, or that other mods also script (doors, NPCs, common containers). Use a quest script that watches for the condition, an xOBSE event handler (`SetEventHandler "OnActivate"` …), or a **new** object you place.
5. **Persistent references only.** A reference used by EditorID in any script, package or condition must have *Persistent Reference* checked.
6. **Guard per-frame work.** A `GameMode` block that iterates or calls heavy functions every frame causes stutter. Use timers (`set timer to timer - GetSecondsPassed`), quest delay, or `DoOnce` flags.
7. **Check refs before use.** `if target` (non-zero) before `target.Function`. With xOBSE, also `IsFormValid` and `IsReference`. Calling a function on a 0/invalid ref is a common CTD.
8. **`PlaceAtMe` creates permanent FF-forms** that bloat saves. Prefer `MoveTo` on a pre-placed disabled ref, or `Enable`/`Disable`. If you must use PlaceAtMe, clean up with `Disable` + xOBSE `DeleteReference`.
9. **Never `Disable`, `Kill` or `ResetQuest` anything the main quest, guild quests or other mods rely on.** Use your own copies.
10. **Messages:** `Message` (corner), `MessageBox` (modal; buttons via `GetButtonPressed` in a GameMode/MenuMode loop). Never spam them per frame.
11. **No hard-coded load-order FormIDs.** Use EditorIDs, or `GetFormFromMod` for optional dependencies.

## 4. xOBSE essentials (only with xOBSE installed and the CS launched via `obse_loader -editor`)

```
scn MMCSQuestScript
array_var lootTable
string_var label
short i

Begin GameMode
    if GetGameLoaded                      ; once per load/new game, per script
        Let lootTable := ar_Construct Array
        ar_Append lootTable MMCSRuby
        Let label := "MyMod v" + ToString 1.2
        PrintC "%z ready" label           ; console print; %z = string_var
        SetEventHandler "OnDeath" MMCSOnDeathFn   ; register a user-function handler
    endif
    if GetGameRestarted                   ; once per exe start: re-apply non-saved changes
        AddToLeveledList LL0LootClutter100 MMCSRuby 1 1  ; vanilla list; runtime injection, not saved
    endif
End
```
```
scn MMCSOnDeathFn                         ; user function (Object script type, not attached)
ref target
ref killer                                ; OnDeath passes (target:ref, killer:form)
Begin Function {target, killer}
    if killer == player
        PrintC "Player killed %n" target
    endif
End
```
- **Expressions:** `Let x := expr`, `eval`, `if eval (...)`, `While (...)`… `Loop`, `ForEach item <- array`… `Loop`, `Break`, `Continue`. Every While/ForEach has exactly one `Loop` at the same nesting level.
- **Strings:** `string_var` must be initialized with `Let s := "..."` or `sv_Construct`. Never use `set` with strings. `sv_Destruct` when done in long-lived scripts.
- **Arrays:** `ar_Construct Array|Map|StringMap`. Assignment shares the array, it doesn't copy (`ar_Copy` copies). Arrays live in the `.obse` co-save.
- **Soft dependencies (compatibility without masters):**
  ```
  if IsModLoaded "Oscuro's_Oblivion_Overhaul.esp"
      Let otherForm := GetFormFromMod "Oscuro's_Oblivion_Overhaul.esp" "001234"
  endif
  ```
  This lets one plugin adapt to another without making it a master. It's the preferred way to integrate with optional mods.
- **Runtime leveled-list injection** (`AddToLeveledList` in `GetGameRestarted`) adds your items to vanilla lists **without overriding the LVLI record**, which avoids leveled-list conflicts. These changes aren't saved, so redo them on every restart. Remove them on uninstall with `RemoveFromLeveledList`.
- **Runtime `Set*` changes to base forms** (damage, value, name…) aren't saved either. Re-apply them under `GetGameRestarted`.
- **Version guard:** `if GetOBSEVersion < 22` → `MessageBox "This mod needs xOBSE 22+"` and stop.

## 5. Common functions (vanilla)

`GetSelf`, `GetActionRef`, `IsActionRef`, `GetContainer`, `GetItemCount`, `AddItem`/`RemoveItem`, `EquipItem`, `MoveTo`, `PositionCell`, `SetPos`/`GetPos`, `Enable`/`Disable`, `GetDisabled`, `GetDistance`, `GetInCell`, `GetInWorldspace`, `GetStage`/`SetStage`, `GetStageDone`, `StartQuest`/`StopQuest`, `GetQuestRunning`, `GetQuestVariable`-style access (`MyQuest.var`), `Cast`, `AddSpell`/`RemoveSpell`, `ModAV`/`SetAV`/`GetAV`, `ModDisposition`, `SetFactionRank`, `GetIsID`, `GetIsReference`, `StartConversation`, `Say`, `EvaluatePackage`, `AddTopic`, `ShowMap`, `PlaySound`, `GetRandomPercent`, `GameDaysPassed` (global), `GetCurrentTime`, `GetSecondsPassed`.

## 6. Compile-error triage

| Error | Cause / fix |
|---|---|
| "Script 'X' is not a valid ...", "Unknown command" | OBSE command without the OBSE editor hook → launch the CS via `obse_loader -editor`. Or a typo: grep the docs. |
| "Reference 'X' not found" | EditorID missing or misspelled, or its plugin isn't loaded as a master. |
| "...is not a persistent reference" | Tick Persistent on that reference. |
| "Mismatched if/endif", "Missing loop" | Block structure. Count if/endif/while/loop pairs. |
| Compiles but does nothing | Wrong script type, not attached, quest not running (Start Game Enabled flag), `GameMode` on an unloaded object, or SCDA missing (`modlint lint` flags `SCRIPT_NOT_COMPILED`). |
