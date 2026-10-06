# Handoff: TES4Forge phase 1 → finish it on the PC

**From:** a Claude Code cloud session (2026-10-06). It had no game files and could not see the PC.
**To:** the local Claude that works on the Shadow PC in `C:\Users\Shadow\Desktop\Games`.
**Goal:** run the phase 1 acceptance build against the real Rebirth+ files and report the result.

## 1. What was built (in the cloud)

On GitHub `pagesofthetome-art/Oblivion`, branch **`claude/jolly-pasteur-hiurwl`**:

| Path | What |
|---|---|
| `tools\forge\` | The `forge` CLI and library: `caps`, `spec check`, `new`, `build`, `package`, `compare`. Also passes commands through to modlint / xedit_run / CS bridge / assetkit. |
| `forge.cmd` | Launcher at the repo root: `forge <command>`. |
| `specs\rebirth-plus-merge-patch.yaml` | Spec that rebuilds `Rebirth Plus - New Mods Patch.esp`. |
| `tools\forge\README.md` | One-page manual. Read it first. |
| `docs\forge-phase-checklist.md` | Phase 1–7 checklist with acceptance tests. |
| `tools\requirements-forge.txt` | PyYAML (needed for `.yaml` specs). |

- The merge itself is still `tools\merge-patch\patchlib.py` + `world_edits.py`, **unchanged**. Forge only replaced `build_patch.py`'s hard-coded cloud paths with spec fields.
- Every build reads the output back to check it, lints it with modlint, and writes `forge-builds\<name>\build-log.json` with hashes of the inputs, outputs and code.
- Forge refuses to write into any folder that holds `Oblivion.esm`, or into a Vortex folder.
- Tests: 24 pass, on invented fixture plugins with no Bethesda data.

### Important finding

The old `build_patch.py` walked the new mods as a Python `set`, so its record order depended on `PYTHONHASHSEED`: on the fixtures, 12 seeds gave 2 different files. Forge walks the new mods in load order, so its output is deterministic. Consequence:

- The shipped patch **cannot** be reproduced byte for byte. Its order came from a random seed.
- The phase 1 test is therefore **"record-identical to the shipped patch"**. The spec checks this with `expect.same_records_as`.
- Once that passes, record the new file's SHA-256 as `expect.sha256`. Every rebuild after that must match it exactly.

The prompt asked for "identical bytes", so tell the user about this change. Don't hide it.

## 2. Steps on the PC

Follow `AGENTS.md`. This task is **read-only on the game**: forge writes only to `forge-builds\`.

1. Get the branch into `C:\Users\Shadow\Desktop\Games`. That folder is not a git checkout yet (see `13-ai-downloads-and-research-handoff.md`). Either clone the branch into a new folder, or copy in only the new and changed files listed above, plus `AGENTS.md`, `.gitignore` and `tools\merge-patch\README.md`. Don't overwrite local files that are newer than the repo without asking.
2. `python -m pip install -r tools\requirements-forge.txt`
3. Run the tests: `cd tools` then `python -m unittest discover -s forge/tests -t .` → expect `OK` (24 tests).
4. From the repo root: `forge spec check specs\rebirth-plus-merge-patch.yaml`
   - Every `file` line must say `ok`. These paths are guesses taken from the audit scripts:
     - `STEAM_DATA` = `C:/Program Files (x86)/Steam/steamapps/common/Oblivion/Data`
     - `_audit\installed_plugins`: made by `Prepare mod audit.bat`. If it's missing or stale, run that script again (it copies the plugins read-only).
     - `_audit\inspect`: made by `prepare_new_mods.ps1`. It must hold the new-mod plugins, `MTCThievesGrotto.esp` and `LegionOutposts-ThievesGrotto Patch.esp`.
     - `Plugins.txt` = `%LOCALAPPDATA%\Oblivion\Plugins.txt`
   - Fix wrong paths with `--set NAME=VALUE` (for example `--set AUDIT=C:/somewhere/_audit`) or by editing the spec's `vars:`.
5. `forge build specs\rebirth-plus-merge-patch.yaml`
   - A good result is `OK`: round-trip shows 0 mismatches, lint shows 0 errors, and `same_records_as` passes against the patch in Steam Data.
   - ITM warnings on world-edit cells are expected. Those cells are only containers for the edited records.

## 3. Likely problems

| Message | Meaning / fix |
|---|---|
| `new plugins not active in Plugins.txt: ['ElsweyrAnequina.esp']` | Elsweyr's esp was missing in the audit. Remove `extra_plugins:` from the spec if it's not installed. Note this changes the result versus the shipped patch. |
| `new plugin X not found in merge_patch.new_mod_paths` | X isn't in `_audit\inspect`. Add its path under `new_mod_paths:`. |
| `N different copies under new_mod_search` | Two different files share a name. Pin the right one in `new_mod_paths:`. |
| `build_cfg extra_paths entry not found, ignored` | A leftover cloud path in `build_cfg.json`. Harmless if search finds the file. |
| `lint: Master X is not in Data` | A master isn't deployed in Steam Data. Check Vortex. |
| `differs from Rebirth Plus - New Mods Patch.esp` | Real difference. Run `forge compare "<Steam Data>\Rebirth Plus - New Mods Patch.esp" "forge-builds\rebirth-plus-new-mods-patch\Rebirth Plus - New Mods Patch.esp" --json` and report which records are only in each file. Common causes: Plugins.txt or the installed plugins changed since the patch was built. **Do not** "fix" this by editing the shipped patch. |

## 4. Rules (non-negotiable, from the forge prompt)

- Never modify Oblivion.esm, official DLC, other authors' plugins, or the shipped patch. Forge outputs go only to `forge-builds\`.
- Research mods are reference only: never put them in Vortex or a Data folder.
- Don't deploy the rebuilt patch. Deploy only if the user asks, and then only as a packaged zip (`forge build ... --package`) through Vortex.
- Don't drive the mouse or keyboard while the game is running.

## 5. Report back to the user

- Test result (24 OK?), the `spec check` output, and the `build` output: status, sha256, masters, records merged, warnings, failures.
- If it passed: put the sha256 into `expect.sha256` in the spec, tick the PC box in `docs\forge-phase-checklist.md`, and say phase 1 is done.
- If it failed: the exact message and the `forge compare` summary. Name the one thing you need from the user.
- Next phase: 2 (SQLite knowledge store). See the checklist.
