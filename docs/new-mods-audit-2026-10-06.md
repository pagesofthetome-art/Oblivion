# New mods audit (2026-10-06)

This audit compares 44 new archives from `Downloads` against the Rebirth+ setup: 185 active plugins in the Steam copy. It checks:
- records, against Oblivion.esm and every installed plugin;
- exterior cell placement and terrain (LAND/height maps);
- placed-reference overrides;
- dialogue (INFO/DIAL);
- loose assets, against `vortex.deployment.json`.

The tools are in the cloud scratch folder `/home/claude/modscan`: `analyze.py`, `compare.py`, `loc.py`, `cellpos.py`, `qstages.py` and `infoovr.py`.

## Consolidated or dropped
- **The Legacy 1.3** is dropped. Tears of the Fiend 1.22 already contains The Legacy and The Butcher of Armindale, and its readme says TotF *replaces* both.
- **Bounty Quests 3.0** replaces the installed 2.6. The OOO patch is not needed.
- **Mannimarco Resurrection** is kept alongside Mannimarco Revisited.
  - Resurrection is self-contained: it has no vanilla record overrides and is a post-questline story.
  - Revisited changes the vanilla Mannimarco fight.
  - Resurrection has 2 injected worldspace FormIDs (index 00). Nothing else uses them.
- **Patches for mods that aren't installed** are skipped: Weynon Priory Alive, Better Cities, Lush Woodlands/UL, KOTN Revelation, Milewood, MTC Expanded Villages, Cyrodiil Rebuild, Walkabout, Golden Crest, Griffon Fortress, Integration, OOO, and SM Orrery.
  - Some of these carry the same file name as the main plugin (`SOC-RegionalFarms.esp` for WPA, `WickmereFarm.esp` for Milewood). Use the normal versions.
- **Patch kept:** `Rumare-AFK_Weye Patch.esp`, because both AFK Weye and Region Revive are installed (7 cells of shared terrain and buildings).
- **Cobl 1.74:** Main.esm, Glue and Si only. Skip the tweak, race and dev options.
- **Elys Silent Voice 30s update:**
  - Install `Elys_USV.dll/.lip/.mp3` into `OBSE\Plugins`.
  - Do NOT copy the bundled `Construction Set Extender.dll` into the game.
  - Existing bug: the installed v93 deployed `Elys_USV.dll` to `Data\` root, so OBSE never loaded it.

## Missing or broken downloads (page: `Desktop\Oblivion missing mods.html`)
- **MTC Thieves Grotto:** Nexus only has V3 (the re-download is byte-identical). The official SoC `LegionOutposts-ThievesGrotto Patch.esp` is mastered on V4.1, but all 26 objects it moves exist in V3 with the same FormIDs and bases, so the fix is ported into `Rebirth Plus - New Mods Patch.esp` (job `port_patch` in `world_edits.py`). Install TG V3; do NOT install the official patch.
- **Elsweyr Anequina:** the archive has a CRC error in the textures BSA, and the esp is missing. Re-download it.
  - It needs borders off; `bBorderRegionsEnabled=1` is currently on.
  - Recommended: the OCO Elsweyr patch (Nexus 46057).
  - The re-download is the same size as the first one: the CRC error is most likely Windows tar's RAR decoder, not the file. `prepare_new_mods.ps1` now uses 7-Zip (Vortex ships one) and copies the plugins to `_audit\inspect` for checking before packaging.
  - Result (Oct 6 run): 7-Zip was not found on the PC, and tar failed again at the textures BSA, so no esp was extracted. Next step: install the original .rar straight through Vortex, which has its own 7-Zip. Then inspect the esp from the Vortex staging folder.
  - The OCO Elsweyr patch holds loose assets only (meshes/textures under `characters\AnequinaRaces`, 62 files, no plugin). It overlaps nothing in Rebirth+ and is packaged as `OCO Elsweyr patch 1.0.2.zip`.
- **Packaging (Oct 6):** `prepare_log.txt` reports OK for all 37 mods plus Thieves Grotto V3, written to `_audit\vortex_ready`.
- **TES4LODGen:** optional, for SoC distant buildings.

## Location clashes (terrain and placed objects)
| Cells | Mods | Severity | Plan |
|---|---|---|---|
| 51,-3 / 51,-4 | Mannimarco Resurrection site vs Minotaur Encampments camp | Severe: objects 0.4 m apart, terrain up to 4 m off | Ask Yuri: disable that one ME camp and restore terrain |
| 19..20,-40..-41 | Thieves Grotto V3 vs SoC Legion Outposts farm | Severe | Fixed: official LO-TG patch ported to V3 inside the merge patch |
| -23,15 | Villages vs ROTDB terrain | 84 of 136 Villages objects float | Load Villages after ROTDB |
| -17,3 / -18,3 | ROTDB inn vs Knightly Orders chapter | Minor: 4 KOfC walls about 1 m off | ROTDB after KOfC |
| 45,-6 / 46,-6 | Thieves Grotto ruin vs Mehrunes Razor DLC terrain | Fine if TG loads after DLC | Load order |
| 13,-9, 14,-10, 4,12, 5,36, 20,-38, -21,23 | terrain-only edits | None found | none |

## Record conflicts needing a merge patch
**NPC overrides that wipe OCO faces, BNLC levels, UOP/AIO fixes, Mage Equipment outfits and hair fixes:**
- Join the Mythic Dawn: 105 NPCs
- Join the Blackwood Company: 50
- Daedric Quests Revised: 10
- Tears of the Fiend: 4
- Count Bravil: 3
- AFK Weye: 3
- Region Revive: 2
- House Valranis: 1
- Rumare-AFK patch: 10

**Quest records edited by several mods** (stage-level merge is possible; most stages don't overlap):
- Fighters Guild FGC05/06/09/10, FGD02/03/06/07/08/09: C&C, JBC, JMD and UOP/OCRP.
  - Stages changed by two new mods: FGC06 stage 10 (C&C + JBC), FGD07 stage 10 (C&C + JBC), FGD08 stage 80 (C&C + JBC).
- Mages Guild MG00/06/14: C&C, JMD and UOP.
- Main quest MQ05/06: JMD, Time Enough and UOP. No stage overlap between JMD and Time Enough.
- Generic dialogue quests (Generic, Vampire, Crime, CurrentEvents, Khajiit, Disease): only the quest header was touched by TotF, Ownable Tavern, Extended Dialogue and DialogTweaks. Harmless.

**Single-record reverts:**
- Thieves Guild HQ overrides `CreatureMudCrab` and `TGGrayCowlScript`.
- Wintermist overrides `UpperRobe01` and `UpperShoes04`; EVE/VGR are installed.
- JBC overrides 5 troll creatures; Balanced Creatures is installed.

**Dialogue:**
- Star's Extended Dialogue overrides 1190 vanilla INFO/DIAL records. It overlaps with UOP (86), USIP (33), DialogTweaks (30), Vilja (26), Expanded Greetings (24) and JBC (20).

## Assets
Only small overlaps.
- Cobl ships older copies of a few textures: Artifacts Redone icons, WellDiver ghoul tongue, Better Dungeons water, MVO twinkle. Rule: Cobl loads before them.
- Kovahn, Viking Village and Ownable Tavern share identical resource textures. Either can win.

## Mechanics
- No second leveling, needs, combat or engine-fix system is added.
- Four Dark Brotherhood add-ons (Infinitum, DBAQ, DB Continued beta 0.7, ROTDB) and three Thieves Guild add-ons have no record conflicts, but they overlap in story.
- DBAQ needs Elys USV: it is machine-translated and unvoiced.

## Install result (Oct 5 evening, done by Claude in Vortex)
- Installed in Vortex and deployed: 39 packaged zips, Elsweyr Anequina (from the original .rar, which Vortex's 7-Zip unpacked fine) and the OCO Elsweyr patch (rar). vortex.deployment.json was checked: every mod has its files deployed.
- Disabled (not removed): Bounty Quests 2.6, OBSE Elys USV v93 (it put the dll in the Data root), and merge patch v1. v2 replaces v1.
- Plugins: Cobl Main/Glue/Si, AFK_Weye, Rumare-AFK patch and SettlementsOfCyrodiil.esm needed enabling (via "Enable all" / deploy). Now 228 active, and all 57 masters of the patch are active.
- Vortex/LOOT re-sorted the whole load order on install. The merge patch was REBUILT (v2) against the live order. It includes ElsweyrAnequina.esp and three plugins Yuri installed earlier that only got deployed now: Curse of Hircine Resurrected, LTD Vampire Overhaul and ScriptEffectSubduer. Results: 342 CELL, 168 NPC_, 135 INFO, 75 PACK, 33 QUST, 7 CREA, plus 7 other records; 57 masters; round-trip check 791 records, 0 mismatches.
- Plugin rules: `Rebirth Plus - New Mods Patch.esp` loads after the AIO and the Knights compatibility patches, so it is last.
- File rules saved:
  - Cobl loads before Artifacts Redone, Better Dungeons non-BSA, Glittering Prizes, Magic Visuals Overhaul, WellDiver, USIP and UOP.
  - Elsweyr loads after UOP.
  - The Elys fix loads after Tales of Cyrodiil.
  - BPN loads before BPN Compatibility.
  - Kovahn loads before Ownable Tavern Redone and Viking Village.
  - SoC Meshes loads before Viking Village.
- Left unresolved (Yuri's own, pre-existing): Basic Primary Needs 6.3 and Curse of Hircine share files with Expanded Greetings, Crime has Witnesses, LINK, Unarmored, Dynamic Map, Ultimate Leveling and Vacuity.
- Oblivion.ini: border regions off (`bBorderRegionsEnabled=0`, `bEnableBorderRegion=0`). Backup: `Oblivion.ini.bak-20261006`. Vortex's `Oblivion.ini.base` picked the change up.
- Vortex's "requires DLCShiveringIsles.esp" warning is the known false alarm: the DLC loads via DLCList.txt.

## Known controller trap: Persuasion tutorial (vanilla, one-time)
- Page 3 of the vanilla Persuasion tutorial ("The potential gain or loss...") ignores the gamepad under NorthernUI. Mouse clicks and plain Enter do nothing either.
- Fix used on Oct 5: with the tutorial on top, press keyboard **Down** to focus Continue, then **Enter**.
- Only arrow keys + Enter work in that menu.
