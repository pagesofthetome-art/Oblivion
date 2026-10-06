# Research-mod index (private research specimens)

Updated 2026-10-06 by Claude.
- Rule: research only. Never install via Vortex or copy into either Data folder.
- Analysed from copies in Claude's cloud scratch space. The PC copies in `Downloads` were left untouched.
- SHA-256 hashes are of the archives in `C:\Users\Shadow\Downloads`.
- Permissions are UNKNOWN_PERMISSION unless stated, so treat these as PRIVATE_RESEARCH_ONLY.

## Projectile Manipulating Magic (aaBlazesPlusMod) — Nexus 28948
- Archive: `ProjectileMagicUpdate3-28948-3-0.zip`
- SHA-256: `f96e79734d5d66d34de1f345ac4f8f902f4cce9d026f6512799dade49ac4bd9e`
- Author: Blaze (aaBlazes)
- Version: 3.0
- Runtime needs: OBSE
- Technique: Projectile loop: GetFirstRef/GetNextRef scan, GetProjectileType/Source, SetProjectileSource (reflect), SetVelocity/SetProjectileSpeed, GetMagicProjectileSpell; runtime spell editing via SetNthEffectItem*. Has a gravity vortex, a projectile portal, a mirror shield and puppet-master (possession).
- Notes: Best reference for CAP_PROJECTILE_* (freeze, redirect, re-own). 124 scripts, 52 MGEF.

## Telekinetic Damage — Nexus 22957
- Archive: `Telekinetic Damage v6-22957.zip`
- SHA-256: `93f3b348f548c3fb5b0f3a60e2ce2373558721e6f7cc06528ecb6015cd92a28d`
- Author: Colin_man & Critterman
- Version: 0.5
- Runtime needs: none found
- Technique: Damage applied to an object held by vanilla Telekinesis: GetCrosshairRef + PushActorAway + spell cast.
- Notes: Small (6 scripts). Ships a quest with 35 INFOs and an NPC.

## Supreme Magicka (old 0.66) — Nexus 10791
- Archive: `Supreme Magicka 0.66 Fixed-10791.zip`
- SHA-256: `cfc106aae98c075347da0dbc1d187d2cbdc78e1ad7dd3a10f974065c02af9674`
- Author: flyfightflea
- Version: 0.66
- Runtime needs: OBSE v0011+
- Technique: Magic overhaul: 103 MGEF/439 SPEL edits, IsKeyPressed2 hotkeys, levitation platform (actor follows SetPos), CloneForm, SetNthEffectItemMagnitude/Duration, RunBatchScript config.
- Notes: Rebirth+ already runs Supreme Magicka *Lite* via Vortex. Never load both.

## Fearsome Magicka — Nexus 30973
- Archive: `FearsomeMagicka_0_2_RC -30973.7z`
- SHA-256: `6caa375dafb2cb59188bb55c3413e2479bce2738c45c22cdc29352f12f9e5ec8`
- Author: (see readme)
- Version: 0.2 RC
- Runtime needs: OBSE + ScreenEffects.esm (OBGE v1) + RefStuff plugin
- Technique: Largest specimen: 653 scripts. Time-stop quest, magic missiles, combat telekinesis, mirror image, veil of darkness. Heavy use of projectile APIs (GetProjectileLifetime/Speed, SetMagicProjectileSpell) and a ref-scanner quest.
- Notes: Main reference for time stop and enemy spell AI. OBGE v1 conflicts with ORC. Research only.

## PJ's Spell Compendium — Nexus 3892
- Archive: `PJsSpellCompendium-3892.zip`
- SHA-256: `e20871d3ba8a4866bf6ee52c49701fc5497ff08487eb25cf7fa64927f4252825`
- Author: PJ
- Version: 1.2+ (3 variants)
- Runtime needs: none (vanilla script)
- Technique: 180 spells with vanilla-only tricks: PlaceAtMe/SetPos activator FX (585 SetPos), ForceWeather storms, SetRigidBodyMass, CreateFullActorCopy, black hole and rolling-rock traps.
- Notes: Shows how far scripting goes WITHOUT OBSE. The 3 esps are the same content in 3 versions.

## Dimensional Pocket — Nexus 1882
- Archive: `Dimensional Pocket-1882.zip`
- SHA-256: `f51e9ae507180432109d3818e7ffdc29c709ab888e815f82ee1a7b4d3bdb1bf8`
- Author: Symbiode & Skullguise
- Version: 3.0
- Runtime needs: none
- Technique: Pocket worldspace (DIMHubDimension) with its own weather and climate; enter/exit via MoveTo/PositionWorld; return marker.
- Notes: Clean pocket-dimension pattern.

## Pocket Dimension Player Home — Nexus 49144
- Archive: `Pocket Dimension Player Home for Oblivion-49144-V7-1692676995.zip`
- SHA-256: `eb3dbe9be037051dd59a8eb718a66008a5dedffc48536e966ef3464218aa96a5`
- Author: (see readme)
- Version: V7
- Runtime needs: OBSE (IsKeyPressed3, RunBatchScript)
- Technique: Full pocket worldspace (2458 REFR, 25 LAND). Return position stored per worldspace via PositionWorld/PositionCell + placeholder worlds for Tamriel/SI/other dimensions; portal pod item.
- Notes: Best 'remember return position across worldspaces' reference.

## Demiplane House — Nexus 18419
- Archive: `Demiplane House-18419.zip`
- SHA-256: `f70616e55ef62143d415bf50a48d648252a0aed4a231903a352466b715f47db5`
- Author: GoggleDragon
- Version: n/a
- Runtime needs: none
- Technique: Simple worldspace demiplane + teleport spell/door.
- Notes: Permission: 'use however you want, credit appreciated' → CAN_DISTRIBUTE (with credit).

## Portal — Nexus 13673
- Archive: `Portal v0-2-13673.rar`
- SHA-256: `62c7d8e8dae82aba51afb2d937a0161db72abd773412b2028f7d182735d69048`
- Author: Isatin
- Version: 0.2 (2007)
- Runtime needs: none found
- Technique: Linked portal pairs as DOOR refs repositioned at runtime (SetPos/SetAngle on door + linked marker), 'anchored' checks, SI variant esp.
- Notes: Reusable pattern: movable door pairs = CreatePortal/DestroyPortal.

## Madness Portal — Nexus 19180
- Archive: `Madness Portal 1point1-19180.rar`
- SHA-256: `5bef1a41b09415175a06b63c605987846980e9aece0bd03196611b30a3dd7f03`
- Author: Nolle
- Version: 1.1
- Runtime needs: none
- Technique: Summoned portal door with an animated enable/disable sequence; SI version.
- Notes: Small. VFX reuses vanilla mini-gate textures.

## True Necromancy — Nexus 56199
- Archive: `True Necromancy-56199-0-2-1780729369.zip`
- SHA-256: `1d2bd5c15d08a5ad5b995b97545e59fcb894777e340d73bb9ae2d00c14520556`
- Author: (see readme)
- Version: 0.2
- Runtime needs: none flagged
- Technique: Skeleton actor variants (0NecronACTSkeleton0-4), soul-gem driven raising, damage-type spells, ResurrectActor patterns.
- Notes: DIRTY: 2393 vanilla SCPT overrides, 2345 identical (ITM). Must be cleaned before any use.

## Weather Control Spells — Nexus 30346
- Archive: `Weather Control Spells-30346.rar`
- SHA-256: `f0a3a08c093cfb148d371c6ee9e28414628a8431394277cd2bd3a628b2ea7b6b`
- Author: NetEcho
- Version: n/a
- Runtime needs: none
- Technique: 18 spells calling ForceWeather/SetWeather with vanilla WTHR records.
- Notes: DIRTY: 1688 vanilla SCPT overrides, 1639 identical (ITM). Only 18 SPEL + 1 NPC are real content.

## TES4LL (tool) — Nexus 40549
- Archive: `Landscape LOD generator 5_15c-40549-5-15.7z`
- SHA-256: `e12439644e2e50d1912e95dae56f61e77f0e9a7f93eeff3bde064a30a210ad59`
- Author: (see docs)
- Version: 5.15c
- Runtime needs: Windows exe
- Technique: Landscape LOD mesh/colour/normal-map generator from heightmaps.
- Notes: Tool, not a mod. Useful after SoC/Elsweyr terrain edits.

## Cross-cutting findings
- **Projectile capability exists in OBSE today.** It needs no engine hooks. The calls are GetFirstRef/GetNextRef (type 34) plus GetProjectileSource/SetProjectileSource, SetVelocity, SetProjectileSpeed and SetMagicProjectileSpell. Fearsome Magicka and Projectile Magic both use this (escalation level 3: xOBSE).
- **Pocket dimensions** need a dedicated WRLD with its own CLMT/WTHR. The return point is stored with PositionWorld or PositionCell plus marker refs. PDPH also handles SI and other worldspaces.
- **Portals** are DOOR references moved at runtime with SetPos/SetAngle, each linked to a destination marker.
- **Weather:** ForceWeather plus SetWeather on vanilla WTHR records. Only PJ's ships its own WTHR copies.
- **Hygiene:** two specimens are massively dirty, with 1.6k–2.3k vanilla script ITMs. Run a cleaning pass first if a technique is ever reused.
- **Vortex boundary check:**
  - Supreme Magicka *Update* (12466) and its INI are deployed by the Rebirth+ collection; this predates the research task.
  - `ProjectileMagicUpdate3-28948-3-0.zip` is also in the Vortex **downloads** folder, but nothing from it is deployed. Leave it unless Yuri says otherwise.
- **Still missing:** Scripted Spells (3915), Spell Extension (51358), Supreme Magicka Update (12466) as a research archive, LAME (20371) and AOMS (31918).
