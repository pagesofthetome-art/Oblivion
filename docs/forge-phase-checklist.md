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

## Phase 3: records and scripts from the spec
- [ ] `kind: plugin` builds records; scripts compile through the CS bridge (`script.compile`).
- [ ] Test: a fire-bolt variant spell builds, compiles, lints clean and works in game.

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
