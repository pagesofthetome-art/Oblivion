# 01 · Oblivion: the game, for modders

Read this to understand what you are changing and what players expect. Everything here applies to **classic Oblivion (2006, v1.2.0.416)**. This workspace has the **GOG Game of the Year Deluxe** build in `Oblivion\`.

> **Not Oblivion Remastered.** The 2025 *Oblivion Remastered* runs the old game logic under Unreal Engine 5 and uses a different mod setup (UE4SS, pak files, a separate OBSE64). Nothing in these docs applies to it unless stated. If a user mentions "Remastered", "UE5", ".pak" or "OBSE64", stop and confirm which game they mean.

## 1. Setting and content

- Cyrodiil, the Imperial province of Tamriel, Third Era 433. Main quest: the Oblivion Crisis (Martin Septim, Mehrunes Dagon, Oblivion Gates).
- Factions: Fighters Guild, Mages Guild (Arcane University), Thieves Guild, Dark Brotherhood, Arena, plus Knights of the Nine (DLC) and the Daedric shrines.
- **Shivering Isles** (`DLCShiveringIsles.esp` + its BSAs). The Realm of Madness, Sheogorath. It is its own worldspace (`SEWorld`). In the GOG install the `.esp` is a tiny stub of about 85 bytes. Its records live inside `Oblivion.esm` (GOTY merge), so SI forms have `Oblivion.esm` FormIDs.
- **Knights of the Nine** (`Knights.esp`, `Knights.bsa`), the Crusader's relics questline.
- Official mini-DLC ("Bethesda plugins"): Horse Armor, Mehrunes' Razor, Vile Lair (Deepscorn Hollow), Frostcrag Spire, Battlehorn Castle, Spell Tomes, Thieves Den, Orrery. All of these are `.esp` files with `Oblivion.esm` as their only master.

## 2. Core systems you will touch

| System | How it works | Where it lives in data |
|---|---|---|
| **Character** | 8 attributes, 21 skills (7 major), class, race, birthsign. Leveling happens by raising major skills 10 times; level-up multipliers come from governing skills. | `CLAS`, `RACE`, `BSGN`, `SKIL`, GMSTs (`fXXX`, `iXXX`) |
| **Level scaling** | Most loot, creatures and NPCs scale to player level through **leveled lists**. This is the most-patched system in Oblivion modding. | `LVLI`, `LVLC`, `LVSP`, plus `NPC_`/`CREA` level flags (PC-level offset) |
| **Magic** | Spells are lists of magic effects (`MGEF`, hard-coded 4-char codes like `FIDG` and `REHE`). Custom spellmaking happens at the Arcane University. Enchanting uses soul gems and sigil stones. | `SPEL`, `ENCH`, `MGEF`, `SGST`, `SLGM`, `ALCH`, `INGR` |
| **Alchemy** | Ingredients have 4 effects, revealed by the Alchemy skill. Apparatus quality matters. | `INGR`, `APPA`, `ALCH` |
| **Combat** | Real-time. Fatigue matters. Weapon/armor condition. Combat styles drive AI. | `WEAP`, `ARMO`, `AMMO`, `CSTY`, GMSTs |
| **Radiant AI** | NPCs follow **AI packages** (Eat, Sleep, Wander, Travel, Find, Follow, Escort, UseItemAt...) on a 24h schedule with conditions. | `PACK`, plus each `NPC_`'s package list |
| **Dialogue** | Topic-based. `DIAL` topics hold `INFO` responses filtered by conditions. GREETING/HELLO/GOODBYE are shared topics, so every mod's INFOs merge into them. Each INFO belongs to a quest. | `DIAL`, `INFO`, `QUST` |
| **Quests** | Stages (0–255) with result scripts, journal entries, objectives and map targets. Quest scripts run while the quest is running. | `QUST`, `SCPT` |
| **Crime & factions** | Ownership on references and cells, bounty, faction ranks and disposition. | `FACT`, ownership fields on `REFR` and `CELL` |
| **World** | The `Tamriel` worldspace (exterior grid, 4096 units per cell) plus interior cells. Exterior regions control weather and sounds. LOD is pre-generated. | `WRLD`, `CELL`, `LAND`, `REFR`, `PGRD`, `REGN`, `WTHR`, `CLMT` |
| **Economy** | Merchant containers, barter gold, `fBarter*` GMSTs, item `Value`. | `NPC_` services flags, `CONT` |

## 3. Things players notice and complain about

- **Level scaling extremes**: bandits in glass armor, Daedra everywhere. Overhauls (OOO, MMM, Francesco's, FCOM, Maskar's, OOO-like custom) all rewrite leveled lists, so they conflict with each other unless merged.
- **UI**: the console-era UI. DarnifiedUI, Oblivion XP, BTmod and NorthernUI replace `menus\*.xml` in `Data\menus` (or a BSA override).
- **Stability**: the vanilla engine leaks memory and has many crash paths. Players expect mods not to make this worse (see `07-conflicts-and-compatibility.md` §6).
- **Save bloat and broken saves**: scripted mods that are uninstalled mid-game leave orphaned script data behind. Changing a mod's scripts or quest variable layout between versions can break existing saves.
- **Immersion**: lore-friendly names, vanilla-style art, sensible prices. A "quality" mod blends in unless the user asks for something different.

## 4. Popular framework mods agents should know

Assume none of these are installed. `Oblivion\Data` currently holds only official files. Use `tools\modlint.py load-order` to check. Never add a hard dependency the user did not ask for.

| Mod | What it is | Why it matters |
|---|---|---|
| **xOBSE** (Oblivion Script Extender, 22.x) | Script engine extension. Strings, arrays, user functions, event handlers, hundreds of commands. | **Installed** (xOBSE 22.13, 2026-10-04): start the game via `Oblivion\obse_loader.exe`. Required by most advanced script mods. |
| **Unofficial Oblivion Patch (UOP)**, **USIP**, **UOMP** | Thousands of fixes to vanilla, SI and the official plugins. | Almost every user has them. They touch many vanilla records, so your edits to vanilla records will often conflict with UOP. |
| **Wrye Bash** | Mod manager + **Bashed Patch** (merges leveled lists and record fields by tag). | The standard conflict-resolution tool for Oblivion. |
| **LOOT** | Load-order sorter with masterlist cleaning info. | Replaces BOSS. |
| **Engine Bug Fixes, Oblivion Display Tweaks, 4GB patch, Oblivion Stutter Remover (older)** | Engine-level stability fixes. | Some change memory and heap behaviour; mention them in crash troubleshooting. |
| **OBSE plugins** (`Data\OBSE\Plugins\*.dll`): Pluggy, ConScribe, Blockhead, MenuQue, OneTweak, etc. | Extra script functions and engine features. | A script using their functions only compiles and runs with them installed. |
| **Construction Set Extender (CSE)** | Huge CS enhancement: script editor with IntelliSense, loading ESPs as masters, crash protections, batch editing, coda scripting. | Strongly recommended for serious CS work. Not installed. |

## 5. File-level picture (details in `03-data-files-and-formats.md`)

```
Oblivion\
  Oblivion.exe, OblivionLauncher.exe, TESConstructionSet.exe
  Oblivion_default.ini          template; the live INI is Documents\My Games\Oblivion\Oblivion.ini
  Data\
    Oblivion.esm                master: all vanilla + SI records (~277 MB)
    *.esp                       official DLC plugins
    *.bsa                       archives: meshes, textures, sounds, voices, misc
    Textures\, Music\, Video\, Shaders\, LSData\   loose files (override BSA contents)
Documents\My Games\Oblivion\    Oblivion.ini, OblivionPrefs.ini, Saves\
%LOCALAPPDATA%\Oblivion\Plugins.txt   active plugin list
```
