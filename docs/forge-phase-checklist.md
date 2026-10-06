# TES4Forge phase checklist

Source: `15-forge-prompt.md`. A phase ships only when its tests pass. Tick a box only with evidence: a test name, a build-log hash, or an in-game note.

## Phase 1: unified CLI and spec format (in progress)
- [x] `forge` CLI + library (`tools/forge`, `forge.cmd`): `caps`, `spec check`, `new`, `build`, `package`, `compare`, plus pass-through to modlint / xedit_run / CS bridge / assetkit.
- [x] Spec format (YAML/JSON, vars, `--set`, a permission on each input, `expect:`). README: `tools/forge/README.md`.
- [x] Capability registry with providers, tests, confidence and live availability (`forge caps`).
- [x] Merge patch as a spec kind; `patchlib.py` and `world_edits.py` reused unchanged.
- [x] Build log: input/output/code hashes, tool versions, git commit, command (`build-log.json`, `history.jsonl`).
- [x] Deterministic Vortex zip (`forge package`).
- [x] Guards: never writes into a Data or Vortex folder; refuses to package a tampered build.
- [x] Fixture tests (24): forge output is byte-identical to the legacy `build_patch.py` once that script's set-ordered loop is put in load order. Under any hash seed the records are the same.
- [x] **Real-data build (2026-10-06):** run on mirrored copies of the PC plugins and live Plugins.txt.
  - Spec check: all paths found. 24 tests OK. Round-trip 0 mismatches. Lint 0 errors.
  - Output differs from shipped v2 in only 3 INFO records. v2 kept LTD Vampire Overhaul's deletions; forge now neutralises them (undelete + never-true condition).
  - Deterministic: sha256 `c1e5a675...` across hash seeds.
  - Still to do on the PC: one `forge build` against the real paths.
  - Byte-identity with the shipped file is not reachable: the legacy builder's record order depended on Python's hash seed (12 seeds → 2 different files on the fixtures; with 39 new mods, far more orders are possible). The phase-1 test is therefore "record-identical to the shipped patch" plus "byte-identical between forge rebuilds". If that build passes, record its SHA-256 as `expect.sha256` in the spec, and every later rebuild must match it exactly.

## Phase 2: knowledge store (done 2026-10-06)
- [x] `forge-kb.sqlite` + `forge kb` (build, query, func, record, form, forms, technique, crash, stats). SQLite FTS5 ranked search; every row has `source` + `confidence`.
- [x] Record schemas for 65 TES4 record types (574 subrecords, 692 struct fields) from xEdit's TES4 definitions. FormID subrecords cross-checked against `patchlib.F`.
- [x] Functions: 1528 OBSE commands (params, return type, release added) from the xOBSE source; 380 vanilla names (Vim list + xEdit's 200-entry condition table). Our own notes for 38 core functions.
- [x] Techniques: 19 rows from `docs/14` (13 specimens + 6 cross-cutting findings), each linked to the functions it uses.
- [x] Crash signatures seeded (Persuasion trap, Elys USV folder, ORC FPS-limiter hang as HYPOTHESIS); phase-1 results in `test_results`; empty engine tables for 2b.
- [x] PC exporters: `export-vanilla` (Oblivion.esm + DLC → `vanilla_index.jsonl`) and `export-commands` (Oblivion.exe's own command table → `vanilla_commands.jsonl`). Both outputs and the DB are git-ignored.
- [x] `scripts\kb\Build forge KB.bat`: exports, build, PC tests, `kb_log.txt`.
- [x] Cloud tests: 14/14 cloud questions, 2 integrity checks and 3 exporter tests pass. The 6 PC questions skip without the export.
- [x] **PC run 1 (2026-10-06):** 18/20. The PC questions passed 6/6; exporter and integrity tests passed. Exports: 58,845 vanilla forms, plus 369 script and 131 console commands from Oblivion.exe.
  - q03 and q13 regressed: 58k form rows shared the FTS index and outranked functions on "how do I..." questions.
  - Fixed without touching the tests:
    - Forms now have their own index (`fts_forms`). They lead only when the question names one exactly (a CamelCase/digit EditorID or a FormID); otherwise they take at most a third of the slots, after the knowledge results.
    - Our notes are a separate, higher-weighted column.
    - New `test_kb_ranking_noise.py` re-runs the 14 cloud questions against ~59k synthetic forms. It fails on the old ranking (6 failures, including q03/q13) and passes now.
  - Also fixed: the `export-vanilla` summary showed `Oblivion.esm: 0` (the record-less SI stub overwrote the count). `Build forge KB.bat` now takes the game folder as an argument, or finds it.
- [x] **PC run 2 (2026-10-06, `41b5923`, GOG copy `C:\Users\Shadow\Desktop\Games\Oblivion`):** TESTS OK, **20/20, no skips**.
  - Ran 41 tests: 22 KB queries, 16 noise-regression and 3 exporter tests.
  - Export: `Oblivion.esm: 54207`, `DLCShiveringIsles.esp: 0`, 58,845 vanilla forms in total, plus 369 script and 131 console commands.
  - KB: 1,898 functions, 58,845 vanilla forms. q03 → `IsKeyPressed3`; q13 passes.
- [ ] Phase 2b: fill `engine_*` from COEF and the xOBSE headers.
- Gaps: UESP is unreachable from the cloud, so vanilla functions have no UESP descriptions. Their parameters come from the PC exe export. The ORC hang needs a real write-up.

## Phase 3: records and scripts from the spec (in progress; plan: `docs/forge-phase3-plan.md`)
- [x] `forge dump <plugin> <EDID|FormID>`: decodes subrecords with the KB schemas (read-only); the ground-truth tool for the encoder.
- [x] PC recon (handoff 19): vanilla SPEL/SCIT/SCPT bytes, CS bridge readiness, test-profile facts (shared Plugins.txt/INI/Saves; see plan §4).
- [x] Fixes from the recon: the xEdit extractor missed the `wbStructSK` layouts (EFIT/SCIT) and is re-extracted with enums/flags; `tools/gamepaths.py` finds the game beside a repo clone (CS bridge token path).
- [x] 3a in the cloud: `forge/records.py` (schema-driven codec, pad bytes kept), `kind: plugin` builder (`providers/plugin.py`), append-only FormID map, `forge layout-check`, `specs/ak-searing-bolt.yaml` (sha256 `95418054…`). The built SPEL matches vanilla Flash Bolt's layout byte for byte (SPIT/EFIT).
- [x] 3a on the PC (handoff 20, `70dd7c2`): 82 tests OK (no skips).
  - ALCH/ENCH/INGR/SGST **PASS** (2,118 records, 14,998 subrecords, all identical).
  - SPEL+MGEF: all 8,320 subrecords identical, but 33 MGEF `ESCE` left undecoded bytes. Fixed: xEdit arrays (ESCE and 20 other array subrecords) now decode as element lists.
  - Searing Bolt built with the same sha256 `95418054…`, lint clean; the dump matches Flash Bolt's layout. `forge cs health` OK (token path fixed).
- [x] 3a PC rerun (handoff 21, `083659b`): 84 tests OK.
  - SPEL+MGEF **PASS** (1,282 records, 8,320 subrecords, 41 arrays).
  - `--all` over 63 record types: every subrecord identical, 0 mismatches. The only gap was 573 REFR `XSED` tails: xEdit's `wbUnused(0)` means "padding to the end" (XSED is 1 or 4 bytes). Fixed (open-ended trailing padding).
  - Searing Bolt same sha256.
- [x] Handoff 22 (`06ad4fd`): 85 tests OK.
  - `--all` **PASS** on Oblivion.esm (63 types) and Knights.esp (37 types).
  - Top raw subrecords: REFR DATA 1.03M, LAND ATXT/VTXT/BTXT/VNML/VHGT/VCLR, INFO CTDA/DATA, NPC_/CONT CNTO, LVLI LVLO, SCPT SLSD, PACK PKDT/PLDT, STAT MODL/MODB, NPC_ SNAM, REFR XLOD/XTEL.
- [x] Layout coverage, cloud. The xEdit extractor now handles:
  - case-insensitive Pascal names (`wbCNTOS`/`wbCNTOs`);
  - list variables (`wbConditionMembers`);
  - helper functions from `wbDefinitionsCommon.pas` (`wbVec3PosRot`, `wbNextSpeaker`, `wbLand*`), with arguments and defaults bound;
  - fixed-count nested arrays;
  - unsized trailing byte arrays.

  Unions become sized raw bytes. Overrides: CTDA parameter sizes (from patchlib's offsets 12/16) and the `wbTexturedModel` Oblivion branch. Floats whose bytes don't survive (signaling NaN) are kept as hex. Every top-25 raw subrecord now has a layout, except PGRD PGRR (variable per point) and PACK PKDT (a union of 4 or 8 bytes).
- [x] Handoff 23 (`fd08081`): 87 tests OK.
  - Knights.esp **PASS**. Oblivion.esm: every byte identical, one FAIL (19 CLMT TNAM with a 1-byte tail).
  - The top raw count dropped from 1.03M to 8,181 (PGRD PGRR). Size mismatches: REFR XLOC, FACT XNAM, LIGH DATA.
- [x] Fixes, cloud:
  - xEdit `IfThen(Assigned(cb), a, nil)` → CLMT TNAM's 6th byte (Moons / Phase Length).
  - `IsTES4(<Oblivion>, <later games>)` game selector → FACT XNAM is 8 bytes in Oblivion.
  - `SetOptionalFrom(n)` → shorter vanilla variants decode (LIGH DATA 24/32, CTDA 20/24, INFO DATA 2/3).
  - Unions with 0/4-byte alternatives chosen by size → REFR XLOC 12/16.
  - `forge dump --has SIG`.
  - The fixture INFO TRDT is now 16 bytes, like vanilla.
- [x] Handoff 24 (`36cef6e`): 88 tests OK.
  - `--all` **PASS** on Oblivion.esm (63) and Knights.esp (37); the XLOC/XNAM/LIGH variants decode, and CLMT TNAM has its Moons byte.
  - Still raw: script source/bytecode, model texture hashes, PGRD PGRR/PGRL, PACK PKDT.
  - `forge dump` now uses the codec (open tails, variants) and names the CTDA operator (160 = Less Than Or Equal To).
- [x] **3c decision (Yuri): option A**, reusing Track E's verified `tools/playtest` swap/restore (Plugins.txt and Oblivion.ini hashes identical before/after on the PC). One shared implementation. **Blocked:** merging `claude/serene-maxwell-03d2fh` into this branch needs Yuri's go-ahead (the merge was refused by the session's permission check).
- [x] 3b recon take 1 (handoff 25): blocked. `obse_loader -editor` loads the Construction Set Extender v11, which refuses to run without admin rights. Nothing was saved.
- [x] 3b recon take 2 (handoff 26): the plain CS starts cleanly (no CSE). Script Edit's text box (#4 RichEdit20A) stays disabled until a New script exists; the bridge couldn't list or press toolbar buttons. Data unchanged. CSE needs admin and has no skip option; the bridge task isn't elevated.
- [x] Bridge: `toolbar`, `toolbar-press` (WM_COMMAND, no mouse), `menus`, `menu-command`; `FORGE_CS_BRIDGE_PORT` for a temporary repo-run bridge.
- [x] **Direction change (Yuri, 2026-10-06):** forge gets its **own script compiler**, validated against every vanilla script; the CS becomes an optional cross-check. Plan `docs/forge-script-compiler-plan.md` **approved**. The corpus may be uploaded to the cloud. OBSE validation against research-mod scripts happens on the PC only.
- [x] S0 code: `forge kb export-scripts` (corpus bundle) + the exe's block-type table in `export-commands`.
- [x] S1 code: the `forge script-decode` decompiler + survey (8 fixture tests).
- [x] S0+S1 PC run (handoff 28): 26,624 scripts (10,720 with bytecode), 58,408 forms, 31 block types; corpus 2.3 MB, uploaded. The first survey decoded 89.6%.
- [x] **S1 gate: 100%** of the vanilla corpus decodes with no leftover bytes (cloud, on the uploaded corpus). Expressions are postfix; jump fields, Z refs, `~`, Message/MessageBox layouts and the SCHR high-water mark are all confirmed. See plan §3c.
- [x] Confirmation of the 100% on the PC (handoff 29): corpus, Oblivion.esm and Knights.esp all decode 100%. S1 signed off.
- [x] **S2–S6: the compiler.** `forge script-check` gives 99.86% byte-identical SCDA on the vanilla corpus (10,705/10,720); the other 15 are stale data or rare aliases (plan §3d). The reference-list ordering rule matches every identical script.
- [x] Confirmation of `script-check` on the PC (handoff 30): corpus 99.86%, Oblivion.esm read directly 99.95%, same failures. S6 signed off.
- [ ] `scripts:` in `kind: plugin` specs: write SCPT records (and attach them) with forge's compiler.
- [ ] S7: OBSE syntax (validated on the PC only).
- [ ] Optional: CS recon take 3 (handoff 27), the cross-check oracle.
- [ ] ~~3b: `script.compile` through the CS bridge~~ replaced by forge's own compiler (above); the CS is an optional cross-check only.
- [ ] 3c: fire-bolt variant builds, compiles, lints clean and works in game, in an isolated test profile.

## Phase 4: primitives
- [ ] Pocket dimension with a return point that survives save and reload.
- [ ] Linked portal pair.
- [ ] Freeze nearby projectiles and fire them back.
- [ ] In-game test harness: an OBSE test script reads a manifest and writes pass/fail to a log; `forge test` reads it. Uses a test profile, never the play setup.

## Phase 5: asset pipeline
- [ ] Headless Blender + NifTools; texture and audio conversion.
- [ ] Test: a recoloured portal mesh renders in game and appears in the Vortex deployment record (`deploy.verify`; `deploy_check.py` is named in the plan but isn't in the repo yet).

## Phase 6: speed
- [ ] Caching, incremental builds, parallel lint. Target: a spell-sized mod from prompt to zip in under 10 minutes.

## Phase 7: showcase
- [ ] "Stop time during a storm, pull nearby projectiles into orbit, then fire them at chosen enemies."
