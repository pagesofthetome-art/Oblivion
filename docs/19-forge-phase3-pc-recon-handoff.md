# Handoff: TES4Forge phase 3 recon on the PC (read-only)

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude in `C:\Users\Shadow\Desktop\Games`.
**Goal:** collect facts the phase 3 design depends on. **Read-only everywhere:** change no INI, plugin, Vortex setting or game file, and don't start the CS or the game.

Context:
- Phase 2 is merged: PR #1 → `claude/jolly-pasteur-hiurwl`.
- Phase 3 work is on **`forge/phase3-plugin`**. It adds `forge dump`, which decodes a record's subrecords.
- The plan is in `docs\forge-phase3-plan.md`.

## 0. Get the branch

```
git fetch origin
git checkout forge/phase3-plugin
git pull
```
Check that `forge dump --help` works.

Set `GOG=C:\Users\Shadow\Desktop\Games\Oblivion` for the commands below. Save every output under `_audit\forge-phase3\`. Don't commit any of it: the dumps contain Bethesda data.

## 1. Vanilla bytes for the encoder (the most important part)

```
forge kb query "fire bolt spell" --kind form --limit 15                 > _audit\forge-phase3\fire_spells.txt
forge dump Oblivion.esm --data "%GOG%\Data" --sig SPEL --match fire --limit 8 > _audit\forge-phase3\spel_fire.txt
forge dump Oblivion.esm --data "%GOG%\Data" FIDG                         > _audit\forge-phase3\mgef_fidg.txt
forge dump Oblivion.esm --data "%GOG%\Data" --sig SPEL --match "" --limit 3 --json > _audit\forge-phase3\spel_sample.json
forge dump Oblivion.esm --data "%GOG%\Data" --sig SCPT --limit 3         > _audit\forge-phase3\scpt_sample.txt
forge dump Oblivion.esm --data "%GOG%\Data" --sig ENCH --limit 2         > _audit\forge-phase3\ench_sample.txt
```
- From `fire_spells.txt`, pick the **plain vanilla fire bolt/flare spell(s)** (Target range, FIDG). Run `forge dump Oblivion.esm --data "%GOG%\Data" <EditorID>` on each into `spel_<EditorID>.txt`.
- Also find **one SPEL with a script effect** (`SEFF`, it has an `SCIT` subrecord), dump it, and dump the SCPT its `SCIT` points to.
- If MGEF's EditorID isn't literally `FIDG`, use `forge dump ... --sig MGEF --match fire` instead.

## 2. CS bridge readiness

1. Run `forge cs health`, and report the output or the error.
   - If the bridge isn't running, **don't start it**. Just report that.
   - Never print or copy `Oblivion\.cs_bridge_token`.
2. Check whether these files exist in `%GOG%`, and give their sizes:
   - `obse_loader.exe`
   - `obse_editor_1_2.dll`
   - `TESConstructionSet.exe`
   - `Data\OBSE\obse.ini`
3. Check whether `Oblivion\CSBackups\` exists, and how many files it holds.

## 3. Test-profile isolation (facts only)

Phase 3c must test in game without touching the Rebirth+ play setup. Report:
1. `%LOCALAPPDATA%\Oblivion\Plugins.txt`: its line count and last-modified time. Is any other `Plugins.txt` used by the GOG copy? Search `%LOCALAPPDATA%` for other `Oblivion*` folders.
2. `Documents\My Games\Oblivion\Oblivion.ini`: the values of `bUseMyGamesDirectory` and `SLocalSavePath`, and the `SLocalMasterPath` line if present.
3. In `%GOG%`: does a local `Oblivion.ini` exist? What does `Oblivion_default.ini` set for `bUseMyGamesDirectory`?
4. Is there a GOG Galaxy or other launcher setting that redirects Documents/AppData? Report only if obvious; don't dig into the registry.
5. Count the save files in `Documents\My Games\Oblivion\Saves`.
   - **Don't open, move or copy saves.**

## 4. Rules

- Read-only. Nothing in the game folders, Vortex, the INIs or saves changes.
- Don't commit anything from `_audit\`.
- No CS or game launches.

## 5. Report back to Yuri (for the cloud session)

1. Paste the contents of the `_audit\forge-phase3\` files. If they're long, send at least `mgef_fidg.txt`, the fire-bolt `spel_<EditorID>.txt` file(s), the SEFF spell and its script dump.
2. The answers to §2 and §3, as a short list.
3. Anything that failed, quoted exactly.

With this, the cloud session builds milestone 3a: the encoder and the fire-bolt spec. Its PC test re-encodes every vanilla SPEL/MGEF byte for byte. The test-profile facts decide how 3c is set up.
