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
- [ ] **On the PC:** `forge spec check specs\rebirth-plus-merge-patch.yaml` shows every path found, then `forge build` reports `OK` with `same_records_as` passing against the shipped patch.
  - Byte-identity with the shipped file is not reachable: the legacy builder's record order depended on Python's hash seed (12 seeds → 2 different files on the fixtures; with 39 new mods, far more orders are possible). The phase-1 test is therefore "record-identical to the shipped patch" plus "byte-identical between forge rebuilds". If that build passes, record its SHA-256 as `expect.sha256` in the spec, and every later rebuild must match it exactly.

## Phase 2: knowledge store
- [ ] SQLite: record schemas, OBSE functions (from `obse_command_doc.html`), vanilla FormIDs/EDIDs, research techniques (`docs/14-research-mods-index.md`), crash signatures, test results.
- [ ] `forge kb query` in one call. Test: 20 sample queries return correct answers.

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
