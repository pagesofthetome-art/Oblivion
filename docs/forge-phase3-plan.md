# TES4Forge phase 3 plan: records and scripts from the spec

**Goal:** `forge build` turns a `kind: plugin` spec into a new plugin: records from the spec, scripts compiled through the CS bridge, lint clean, conflicts checked.
**Acceptance test:** a fire-bolt variant spell builds, compiles, lints clean, and works in game.

Branch: `forge/phase3-plugin` (off `claude/jolly-pasteur-hiurwl` after the phase 2 merge).

## 1. Spec shape (`kind: plugin`)

```yaml
forge_spec: 1
name: ak-searing-bolt
kind: plugin
intent: "A stronger fire bolt: 30 fire damage in a 5-foot burst, sold by Mages Guild vendors."
output: {plugin: AKSearingBolt.esp, version: "1.0"}
ids: ak-searing-bolt.ids.json        # EditorID -> object ID, committed, never reused
records:
  - sig: SPEL
    edid: AKSearingBolt
    FULL: Searing Bolt
    SPIT: {Type: Spell, Level: Apprentice, Cost: 0, Flags: [Auto-calc]}
    effects:
      - {effect: FIDG, magnitude: 30, area: 5, duration: 1, range: Target}
scripts: []                          # phase 3b: [{name, type, source: scripts/X.txt}]
test_plan:
  - "player.addspell <id>; cast at a target dummy: ~30 fire damage, 5-ft burst."
```

- **References** to other forms are written as `Oblivion.esm:EditorID`, `Oblivion.esm:00012FCD`, or our own EditorIDs. On the PC they resolve through `forge kb form`; tests use fixtures.
- **Enum names** (`Spell`, `Apprentice`, `Target`) come from the KB schema's enum tables, with raw numbers always accepted.

## 2. Building blocks

| Piece | Design | Reuses |
|---|---|---|
| **FormID allocation** | `<name>.ids.json` maps each new EditorID to an object ID from `0x000800` up. It's committed and append-only: an ID is never reused or renumbered, because changing FormIDs breaks saves. | — |
| **Record encoder** | Schema-driven: subrecord order, struct layout and FormID slots come from `kb/data/record_schemas.json`. Where xEdit's layout lives outside the parsed file (e.g. SPEL `EFIT`, `SCIT`), a small `layout_overrides.json` fills it in. Each override must be **verified by re-encoding vanilla records byte for byte** (PC test). | KB schemas, `forge dump` |
| **Writer** | Build `NRec` objects and hand them to `patchlib.Writer`. It already computes masters and rewrites FormIDs. | phase 1 writer |
| **Scripts (3b)** | forge writes `SCPT` records with source text (`SCTX`) and marks them uncompiled. Provider `script.compile` (CS bridge) then loads the plugin in the CS (via `obse_loader -editor`), recompiles each script and saves. forge re-reads the compiled `SCDA`/`SCRO` and stores them in a committed **compile cache** keyed by source hash. Rebuilds with unchanged sources then need no CS and stay deterministic. | CS bridge, modlint's uncompiled-script check |
| **Checks** | Round-trip, `modlint lint` (0 errors), `modlint conflicts` against the live Rebirth+ order, build log, package. | phases 1–2 |

## 3. Milestones

- **3a: records.** Encoder + `kind: plugin` + the fire-bolt spec, with no scripts. **Built in the cloud (`specs/ak-searing-bolt.yaml`).**
  - Cloud: fixture tests and deterministic bytes.
  - PC: **re-encode every vanilla SPEL and MGEF from its decoded fields and get identical bytes**. This proves the layouts.
- **3b: scripts.** `script.compile` through the CS bridge, plus the compile cache. Test: a magic-effect script (SEFF) spell compiles and its `SCDA` matches the cache on rebuild.
- **3c: in game.** Fire-bolt test in an isolated test profile, never the Rebirth+ play setup or the main save. It needs the profile question (§4) answered first.

## 4. PC recon results (handoff 19, 2026-10-06)

- **Vanilla bytes** (GOG Oblivion.esm):
  - Flare / Flash Bolt: `EDID FULL SPIT EFID EFIT`. EFIT = FIDG, magnitude, area, duration, range (2 = Target), actor value 8 (= Health; also xEdit's default).
  - Script-effect spells add `SCIT` + a second `FULL`. SCIT = script FormID, school, visual (char4), hostile u8, 3 pad bytes.
  - Pad bytes hold CS garbage (`cd cd cd`, `1b 56 00`), so the codec keeps them raw.
  - TestPetStay's SPIT type 3 is **Lesser Power** per xEdit's enum. The recon guessed "ability", which is 4.
- **Extractor bug found and fixed:** `wbStructSK(EFIT, [4, 5], '', [...])` hid the EFIT/SCIT layouts (sort-key list read as the field list). Re-extracted; enums and flags are now captured.
- **CS bridge:** the client looked for the token inside the repo clone (`Desktop\Games\Oblivion-repo\Oblivion`).
  - Fixed: `tools/gamepaths.py` resolves the game folder (env `OBLIVION_GAME_DIR` → `<repo>\Oblivion` → `<repo>\..\Oblivion` → `Desktop\Games\Oblivion`), for the bridge client, CS helper/server, xedit_run, modlint and capabilities.
  - The editor files are present (obse_loader, obse_editor_1_2.dll, TESConstructionSet.exe, OBSE\obse.ini). `CSBackups\` doesn't exist yet.
- **Test profile:** the GOG and Steam copies share **one** `Plugins.txt` (229 lines, the Rebirth+ list), **one** `Oblivion.ini` (`bUseMyGamesDirectory=1`, `SLocalSavePath=Saves\`) and **one** Saves folder (27 saves). There's no GOG-local INI.
  - So 3c can't just "use the GOG copy": activating a test plugin there changes the Rebirth+ setup.
  - **Decision (2026-10-06): option A, implemented once in Track E's `tools/playtest`** (branch `claude/serene-maxwell-03d2fh`; swap/restore already verified on the PC). Phase 3c will run `forge playtest specs/ak-searing-bolt.yaml`, with playtest building `kind: plugin` specs through `providers/plugin.py` instead of its stand-in `build_example`. Waiting on Yuri's go-ahead to merge that branch.
  - Options that were considered:
    - **A. Profile swap tool** (`forge testprofile enter/exit`):
      - Back up `Plugins.txt` and `Oblivion.ini` with hashes, then write a test `Plugins.txt` (vanilla + test plugin) and an INI copy with `SLocalSavePath=TestSaves\`.
      - `exit` restores both and verifies the hashes. It refuses to run while the game runs.
      - The main saves are never touched; test saves go in `TestSaves\`.
    - **B. Wrye Bash / mod-manager profile** for the GOG copy (if one is set up later).
    - **C. Test in the Rebirth+ setup itself** after packaging. This breaks the "never the play setup" rule, so it's not recommended.

## 5. Rules carried over

- Only new plugins; never modify Oblivion.esm, DLC or other authors' plugins.
- Research mods are reference only.
- Escalation order: records → vanilla script → xOBSE.
- Every new menu or prompt must work with a controller.
- No mouse or keyboard driving while the game runs.
- Every build is logged.
