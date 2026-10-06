# Mod spec: <Mod name>

- **Plugin:** `<ShortName>.esp`   **EditorID prefix:** `<PFX>`   **Version:** 1.0
- **User request (verbatim):** "<...>"
- **Goal (player-visible):** <one sentence>
- **Non-goals:** <what this deliberately does not change>

## Environment (from `modlint load-order`)
- Active plugins relevant to this mod: <list>
- xOBSE installed: yes/no · Unofficial patches: <UOP/USIP/UOMP?> · Mod manager: <Wrye Bash/OBMM/MO2/none>

## Dependencies
| Kind | Name | Hard (master) / soft (IsModLoaded) | Why |
|---|---|---|---|
| master | Oblivion.esm | hard | |

## New records
| Type | EditorID | Key fields | Notes |
|---|---|---|---|

## Overridden records (each is a future conflict, so justify it)
| Type | Owner:FormID | EditorID | Fields changed | Why unavoidable | Known conflicting mods |
|---|---|---|---|---|---|

## Scripts
| Name | Type | Attached to | Blocks | Variables (append-only order) | Needs xOBSE |
|---|---|---|---|---|---|

## Assets
(Generated assets: one `assets\recipes\<Id>.json` + `templates/asset-spec.md` each.)

| Path (relative to Data) | Source / licence (generated / vanilla kitbash / third-party) | Recipe / build | Status |
|---|---|---|---|

## Test plan (console steps → expected result)
1. `coc ...` → ...

## Save safety
- Install mid-game: ...
- Uninstall: ...
- Update from previous version: ...
