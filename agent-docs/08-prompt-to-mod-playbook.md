# 08 · From a user prompt to a finished mod

Users describe outcomes ("make Daedric armor rarer", "add a house in Chorrol with a mannequin", "make guards stop chasing me for 1-gold thefts"). Turn that into a precise, minimal, compatible change set.

## 1. Interpret

1. **Restate the goal** in one sentence of player-visible behaviour.
2. **Classify** the request (one or more):

| Class | Typical records | Primary tool | Notes |
|---|---|---|---|
| Value tweak / rebalance | WEAP/ARMO/ALCH stats, GMST | xEdit script (batch) | Copy winning overrides. |
| New item / spell / creature | new WEAP/ARMO/SPEL/CREA + assets | xEdit (records) + CS for scripts | Prefix EditorIDs. Inject into lists at runtime or via a Bashed-Patch-friendly LVLI override. |
| Loot / spawn distribution | LVLI/LVLC | xOBSE injection or LVLI override + `Delev/Relev` tags | Classic conflict hotspot. |
| New location (house, dungeon) | CELL, REFR, DOOR, PGRD, LAND (exterior) | CS (render window) | Interiors are low-conflict; exterior edits need landscape/pathgrid care. |
| Quest / dialogue | QUST, DIAL, INFO, SCPT, PACK, NPC_ | CS (compile, lip) + xEdit (inspection) | Voice/lip files keyed by plugin name. |
| AI / behaviour | PACK, CSTY, scripts | CS | Test with `tai`, `tcai`, packages. |
| Gameplay system / engine behaviour | Quest scripts, xOBSE event handlers, GMSTs | CS + xOBSE | Confirm xOBSE is acceptable. |
| Fix / compatibility patch for existing mods | Overrides only | xEdit | `07-conflicts-and-compatibility.md` §4–5 |
| Asset replacer (textures/meshes/UI) | no plugin, or MODL path edits | file ops, NifSkope, texconv | ArchiveInvalidation; file-level conflicts. |
| **New original art** (weapon, clutter, static) | new WEAP/MISC/STAT + new NIF/DDS/icon | **assetkit** recipe → build → preview → install → `Agent_CreateRecordsFromAssets` | `agent-docs/11`; spec with `templates/asset-spec.md`; new files in your own folders never conflict. |

3. **Inventory the environment**: `modlint load-order` (what's installed and active), whether xOBSE is installed (`Oblivion\obse_loader.exe` exists?), whether UOP/overhauls are present, and the user's mod manager (Wrye Bash/OBMM/MO2: check for `Oblivion Mods\`, `Bash Installers\`, or an MO2 profile).
4. **Decide the defaults instead of asking**, unless the choice changes everything:
   - Lore-friendly, vanilla-style, balanced to vanilla progression.
   - No xOBSE dependency unless needed. If needed, say so up front.
   - New plugin `<ShortName>.esp`, masters `Oblivion.esm` only (+ DLC if used), EditorID prefix from the plugin name (2–5 letters).
   - Compatible-first design (§4 of doc 07).
5. **Ask only blocking questions**, at most 1–3 and batched: e.g. *"Should rarer Daedric also mean stronger enemies, or just loot?"*, *"OK to require xOBSE?"*, *"Which existing mods should this be compatible with?"*

## 2. Spec (write it before touching files)

Use `templates/mod-spec.md`. Minimum:
- Goal, non-goals.
- Records to **create** (type, EditorID, key fields) and records to **override** (each with a justification and its conflict risk).
- Scripts (type, attach point, blocks, variables, persistence needs).
- Assets (paths, sources, licences).
- Dependencies (masters, xOBSE, OBSE plugins) and soft integrations.
- Test plan: console steps proving each behaviour (doc 10).
- Uninstall behaviour: what happens to a save when the mod is removed.

## 3. Build (tool choice)

```
Records & bulk data ──► TES4Edit (Pascal script or GUI)          precise, scriptable, no dirty edits
Scripts, lip, placement, pathgrid ──► Construction Set (bridge)   compile is CS-only
Assets ──► assetkit (generated: recipe → NIF/DDS/icon) · NifSkope / Blender / texconv (external) · assetkit.bsa (vanilla refs)
Verify ──► modlint lint/conflicts + Agent_PluginAudit + Agent_ConflictReport
```
Order that minimises rework:
1. Back up (`oblivion_bridge.py backup X.esp`).
2. Create the plugin and its static records in TES4Edit (or the CS).
3. Open in the CS (masters ticked, plugin active): write and compile scripts, attach them, place references, generate lip files, finalise pathgrids. Save.
4. Clean: `modlint lint` → `xedit_run.py qac --yes` (with consent) → `modlint lint` again.
5. Compatibility: `modlint conflicts` against the user's load order → resolve (doc 07) → patches as separate ESPs.
6. Test in game (doc 10).
7. Package (doc 10 §4).

## 4. Quality bar ("high quality" means all of these)

- [ ] Plugin lints clean: no UDR, no unintended ITM, no deleted records, no invalid FormIDs, every script compiled, no duplicate EditorIDs.
- [ ] Every override is intentional and listed in the readme.
- [ ] EditorIDs prefixed; names, descriptions and book text proofread and lore-consistent.
- [ ] Balanced against vanilla (compare with similar vanilla records: value, weight, damage, enchant charge, level).
- [ ] Icons, models and textures present and paths valid; no absolute paths.
- [ ] Persistent refs where scripts or packages need them; no per-frame heavy scripts.
- [ ] Works with no optional mods; adapts when they're present (soft dependencies).
- [ ] Clean-save-safe: says what happens on uninstall; updates don't break saves.
- [ ] Conflict report attached for the user's load order (`templates/compat-report.md`).

## 5. Worked interpretation examples

**"Make Daedric armor rarer."** → Loot/spawn distribution. Find the LVLI records listing Daedric pieces (`modlint find`, or an xEdit script listing LVLI entries referencing `ARMO` with "Daedric" in the EditorID). Raise their level entries or chance-none in the winning overrides. Tag the plugin `Delev, Relev`. Optionally also raise `ARMO` value. Don't touch NPC_ records. Report what the change does to bandit/marauder loot. Conflict risk: overhauls (OOO, MMM, Francesco's) override the same lists, so a Bashed Patch is required.

**"Add a player house in Chorrol."** → New location. Interior CELL (new) + door pair (new REFR in the Chorrol worldspace cell + interior). Pick a lot that UL/Better Cities/Open Cities don't use; verify with `modlint conflicts` once the user's mods are known. Add a new `DOOR` ref only (no LAND edits); pathgrid edits only in the interior. Containers marked non-respawning (CONT flag). Deed/key via a merchant script that adds the key (`AddItem`) rather than editing a vanilla merchant. Test with `coc <interior EditorID>`.

**"Guards ignore 1-gold thefts."** → Gameplay system. GMSTs can't express "under N gold". The options are a crime-gold GMST rebalance (`iCrimeGold*`, coarse but dependency-free), or an xOBSE script (an `OnAlarm Steal` event handler, which receives the alarmed actor and the criminal, plus custom logic to undo small bounties). The xOBSE route needs a prototype first, because the event doesn't hand you the stolen item. Explain the trade-off, and ask whether xOBSE is acceptable before building.
