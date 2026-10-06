# TES4Forge (`forge`)

One command line and Python library that turns a mod spec into a tested, installable Oblivion mod. It wraps the tools that already work (`tes4_plugin`, `merge-patch`, `modlint`, `xedit_run`, the CS bridge, `assetkit`) behind named **capabilities**, and every build leaves a log that lets anyone repeat it. Phase checklist: [`docs/forge-phase-checklist.md`](../../docs/forge-phase-checklist.md).

## Run it

```
forge <command>                     (repo root: forge.cmd on Windows, ./forge elsewhere)
python -m forge <command>           (from tools\)
python -m pip install -r tools\requirements-forge.txt     (PyYAML, for .yaml specs only)
```

| Command | What it does |
|---|---|
| `forge caps [--json]` | Capability registry: status, phase, confidence, and which provider works on this machine. |
| `forge spec check <spec>` | Validates the spec, lists the capabilities it needs, and checks that every input path exists. |
| `forge build <spec> [--set K=V] [--out DIR] [--package]` | Builds, round-trips, lints and checks expectations, then writes `build-log.json`. Exit 0 = ok, 2 = a check failed. |
| `forge package <spec>` | Zips the last passing build for Vortex: the plugin plus a readme, with byte-stable output. Refuses if the plugin changed after the build. |
| `forge compare A.esp B.esp` | Reports `byte-identical`, `record-identical` (same records and header, different order), or `different`. |
| `forge kb <command>` | Knowledge store: search, function/record/form/technique lookups (see below). |
| `forge new "<idea>"` | Writes a draft spec in `specs\` (kind `plugin`, which builds from phase 3). |
| `forge lint\|info\|records\|conflicts\|load-order\|find …` | → `tools\modlint.py`; arguments pass straight through. |
| `forge xedit …` / `forge cs …` / `forge asset …` | → `xedit_run.py` / the CS bridge client / `assetkit.build`. |

## New plugins from records (`kind: plugin`, phase 3a)

```yaml
kind: plugin
output: {plugin: AKSearingBolt.esp}
ids: ak-searing-bolt.ids.json          # EditorID -> FormID, append-only: commit it
dependencies: {masters: [Oblivion.esm]}
records:
  - sig: SPEL
    edid: AKSearingBolt
    FULL: Searing Bolt
    SPIT: {Type: Spell, Cost: 60, Level: Apprentice, Flags: []}
    effects: [{effect: FIDG, magnitude: 30, area: 5, range: Target}]
lint: {data: "C:/Users/Shadow/Desktop/Games/Oblivion/Data"}
```
- **Fields:** record keys are subrecord signatures. Field names and enum/flag values come from `forge kb record SPEL`. Subrecord order follows the schema, i.e. vanilla order.
- **References:** `Oblivion.esm:046EC0`, `Oblivion.esm:EditorID` (needs the KB vanilla index), or one of the spec's own EditorIDs.
- **FormIDs:** new records start at `000800`. An EditorID keeps its ID forever. Move a dropped one to `retired`; it's never reused, because renumbering breaks saves.
- **Checks:** every build re-reads the plugin and re-encodes each subrecord (round-trip), lints against `lint.data`, logs hashes, and can `--package`.
- **`forge dump <plugin> <EDID|FormID>`** decodes a record, with enum names and FormIDs as `Owner:OOOOOO`.
- **`forge layout-check <plugin> --sig SPEL`** re-encodes every record of a type and must report PASS: identical bytes, no undecoded leftovers. It proves a layout against vanilla.
- **Scripts** (`scripts:`) compile through the CS bridge from phase 3b.

## Scripts (`forge script-decode`, phase 3b, steps S0–S1)

Forge is getting its own script compiler; the plan is in `docs/forge-script-compiler-plan.md`. The first two steps are built:
- **`forge kb export-scripts --data <Data> --exe <Oblivion.exe>`** (PC only) writes `forge-script-corpus.jsonl.gz`. It holds every vanilla script (bytecode, source, variables, references), the EditorIDs, and the exe's command and block-type tables. It's Bethesda-derived and git-ignored.
- **`forge script-decode <plugin|corpus>`** decompiles SCDA bytecode.
  - The default output is a survey: the pass rate (gate: 100%), failures by kind, and what the jump fields count.
  - `--show EDID --source` prints one script's listing next to its source.

## Knowledge store (`forge kb`, phase 2)

`forge-kb.sqlite` answers a modding question in one call instead of a guess. Every row carries `source` and `confidence` (`CONFIRMED_MULTI_SOURCE`, `HIGH_CONFIDENCE`, `HYPOTHESIS`). Text output labels a HYPOTHESIS as unverified.

```
forge kb build                                 build the DB (adds the PC exports if present); prints counts
forge kb query "which function changes a projectile's owner?" [--kind function|record|technique|crash|form] [--json]
forge kb func IsKeyPressed3 | record INFO | form WeapDaedricLongsword | forms --sig WTHR
forge kb technique PositionWorld | crash persuasion | stats
```

| Table | From | Committed? |
|---|---|---|
| `record_types`, `subrecords`, `subrecord_fields` | xEdit `wbDefinitionsTES4.pas` (MPL-2.0): order, kind, required, repeating, FormID fields and targets, struct offsets. Cross-checked against `patchlib.F` → `CONFIRMED_MULTI_SOURCE`. | facts in `kb/data/record_schemas.json` |
| `functions`, `function_params` | OBSE: xOBSE source command tables (name, alias, params, return type, release that added it). Vanilla: Vim's `obse.vim` name list + xEdit's condition table, upgraded from `Oblivion.exe`'s own command table on the PC. Our short descriptions/examples are in `kb/data/curated.json`. | signatures only; no xOBSE/UESP text |
| `vanilla_forms` | `forge kb export-vanilla` on the PC (Oblivion.esm + official DLC: FormID, type, EDID, FULL). | **never** (Bethesda-derived, git-ignored) |
| `techniques` | `docs/14-research-mods-index.md`, with the functions each technique uses linked automatically. | our analysis |
| `crash_signatures`, `test_results` | `kb/data/curated.json` (seeded from agent-docs/docs). | yes |
| `engine_classes`, `engine_fields`, `engine_functions` | empty, for phase 2b (COEF, xOBSE headers). | — |

- **Ranking:** functions, records, techniques, crashes and tests share one index; our notes are a separate, higher-weighted column. Vanilla forms have their own index (`fts_forms`). They lead a `query` only when the question names one exactly (a CamelCase/digit EditorID such as `WeapDaedricLongsword`, or a FormID). Otherwise they fill at most a third of the results, after the knowledge rows. Use `--kind form` for forms only.
- **On the PC:** `scripts\kb\Build forge KB.bat ["<GOG Oblivion folder>"]` runs both exports, the build and the KB tests, and writes `kb_log.txt`.
- **Refreshing upstream facts:** `forge kb refresh-sources --xobse <clone> --xedit <wbDefinitionsTES4.pas> --vim <obse.vim>`, then commit `kb/data/*.json`. `provenance.json` records the commit/hash of each source.
- **OBSE versions:** `obse_version` follows xOBSE's own rule (release index + 8). `8` means "the first OBSE command table" (v0008 or earlier).
- **Not covered yet:** UESP pages are blocked from the cloud environment, so vanilla functions have no UESP-derived descriptions or parameter lists. Without the PC exe export, only names (and condition-function parameter types) are known; those rows are `HYPOTHESIS` unless a second source or our own note confirms them.

## The spec

A single YAML or JSON file is the only build input, and the same spec always gives the same bytes. Relative paths resolve from the spec's folder. Write `${NAME}` to use a value from `vars:`, `${env:NAME}` to read the environment, and pass `--set NAME=VALUE` on the command line to override. Required: `forge_spec: 1`, `name` (slug), `kind`, `intent`, `output.plugin`. Every external file goes in `inputs:` with a `permission`. Allowed values: `PROJECT_OWNED`, `CAN_DISTRIBUTE`, `PATCH_ONLY`, `REQUIRES_ORIGINAL_DOWNLOAD`, `PRIVATE_RESEARCH_ONLY`, `UNKNOWN_PERMISSION`. A `PRIVATE_RESEARCH_ONLY` input must have `role: reference`, so it can never be built into the output. Example: [`specs/rebirth-plus-merge-patch.yaml`](../../specs/rebirth-plus-merge-patch.yaml).

`expect:` turns a build into a test. Set `sha256:` for an exact file, or `same_records_as: old.esp` to require the same records and header.

## Kinds

- **`merge_patch`** (phase 1): the Rebirth+ Bash-style patch. The `merge_patch:` section names the `config` (`build_cfg.json` or inline), `vanilla`, `installed_dir`, `plugins_txt`, `new_mod_paths` / `new_mod_search` (`dir/**` searches subfolders, and two different copies of one name is an error), `extra_plugins`, `insert_after` and `workdir`. The merge is still `patchlib.py` + `world_edits.py`, unchanged.
- **`plugin`** (phase 3): records and scripts from the spec, compiled through the CS bridge. You can draft one with `forge new`, but it doesn't build yet.

## What a build guarantees

1. **Same bytes as the legacy script.** `tools\merge-patch\build_patch.py` walked the new plugins as a Python `set`, so its record order depended on the hash seed: on the test fixtures, 12 seeds gave 2 different files. Forge walks them in load order. The tests run the untouched legacy script (only its paths are swapped). With its loop put in load order, it matches forge byte for byte. Under any seed, its records match forge's.
2. **Round-trip check.** The written file is re-read, and every record must match what the merge produced.
3. **Lint with no errors.** `modlint` runs against `lint.data` (default: `installed_dir`). ITM warnings on world-edit container cells are expected.
4. **Safe output location.** Forge refuses to write into any folder that holds `Oblivion.esm`, or into a Vortex folder. Deploying only happens through a packaged zip installed by Vortex. Output goes to `forge-builds\<name>\` (git-ignored): the plugin, `load_order.json`, `patch_report.json` and `build-log.json`.
5. **Build log.** `build-log.json` holds the SHA-256 of every input plugin, the spec, the config, and the code that ran (`tes4_plugin`, `modlint`, `patchlib`, `world_edits`, forge). It also records the git commit, Python version, command line, parameters, output hashes, warnings and checks. Each build appends one line to `forge-builds\history.jsonl`.

## Tests

```
cd tools
python -m unittest discover -s forge/tests -t .
```
The fixtures (`forge/tests/fixtures.py`) are invented plugins with no Bethesda data. They cover NPC list/struct merges, quest stages, INFO/DIAL, interior cells, land restore + disable, borrowed terrain, and porting a patch onto another master.

## Adding a capability

Add a `Capability` to `capabilities.py` with its providers in fallback order, a test, and a confidence level. If a spec kind needs it, add its name to `spec.KIND_CAPS`. A provider declares its requirements (`file:`, `module:`, `exe:`, `windows`), and `forge caps` shows whether it can run on this machine.
