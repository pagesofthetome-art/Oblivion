# 11 · Creating original art: the assetkit framework

Agents can't sculpt by hand, but they can **describe an asset as data, generate it in code, look at renders, and iterate**. `tools\assetkit\` is that loop for Oblivion: pure Python (numpy + Pillow; scipy optional), no Blender required.

```
 recipe (assets\recipes\<Id>.json)
    │  generator (tools\assetkit\generators.py)  ── parametric geometry, per-part UV atlas
    │  materials (texture.py)                    ── procedural diffuse + height + spec → DDS (+ _n normal map)
    │  nifbuild.py                               ── NIF 20.0.0.5: NiTriShape, tangents, Havok collision
    │  render.py                                 ── 4-view preview sheet + inventory icon
    ▼
 assets\build\<Id>\Data\...   + preview.png + manifest.json + report.md   (validate: PASS/FAIL)
    │  install (consent)  → Oblivion\Data\  + assets\registry.json
    │  records → TES4Edit Agent_CreateRecordsFromAssets.pas → WEAP/MISC/STAT record in your plugin
    ▼
 in-game test (§6) → adjust recipe → rebuild
```

## 1. What's verified and what isn't

| Part | Status |
|---|---|
| NIF reader/writer (`assetkit.nif`) | Every block type assetkit writes was **round-tripped byte-for-byte** on 48 vanilla meshes from Knights.bsa and DLC BSAs (0 failures). Unsupported block types (skinning, animation controllers, MOPP/packed collision, furniture markers) are refused, not guessed. |
| Weapon NIF layout | Copied from vanilla weapons: BSX `0x3`, `Prn`=`SideWeapon`, Havok layer 5, motion 4, quality 3, Havok scale 1/7, grip at origin with the blade along +Y. Tangent data order (binormals first, then tangents) matched against vanilla. |
| DDS writer | DXT1/DXT5/RGBA with full mip chains; Pillow decodes the output with ~1.4/255 mean colour error. |
| **In-game result** | **Not yet tested in Oblivion.** The first asset must be checked in game (§6) before building more. Unknowns: the normal-map green-channel convention (recipe key `normal_green`: `"dx"` default, or `"gl"`) and whether the collision feels right. |
| Preview renderer | Matches vanilla meshes well (tested on `ndmace.nif`). It shades with vertex normals and the diffuse/spec maps only, so it doesn't show normal-map detail. |

## 2. Commands (run from `Games\tools`)

```
python -m assetkit.build build    ..\assets\recipes\AKDuskfangDagger.json     build + validate + previews
python -m assetkit.build validate ..\assets\build\AKDuskfangDagger             re-run checks
python -m assetkit.build install  ..\assets\build\AKDuskfangDagger --yes       copy into Oblivion\Data (consent!)
python -m assetkit.build records  ..\assets\build\AKDuskfangDagger --plugin MyMod.esp
python -m assetkit.build list                                                    installed assets (registry)
python -m assetkit.nif info|roundtrip <file.nif>                                 inspect / verify any NIF
python -m assetkit.bsa list <archive.bsa> --filter weapons\                      browse vanilla archives
python -m assetkit.bsa extract <archive.bsa> <inner\path.nif> --out <dir>        get a vanilla reference
python -m assetkit.bsa find ..\Oblivion\Data dagger                               search all BSAs
```
On the user's PC the first run needs `python -m pip install numpy` (and optionally `scipy` for tight convex-hull collision; without it the collision is the bounding box). See `tools\requirements-assetkit.txt`.

## 3. Recipes (the agent's main lever)

A recipe is JSON in `assets\recipes\<Id>.json`; `AKDuskfangDagger.json` is the reference example.

| Key | Meaning |
|---|---|
| `id` | Asset id = build folder name. Use the mod's EditorID prefix (`AK…` in the example). |
| `generator` + `params` | Which generator in `generators.py` and its parameters (see the function's docstring). |
| `materials` | One entry per part the generator reports (`blade`, `guard`, `grip`, `pommel` …) or a `default`. `kind`: `metal`, `blade`, `gold`, `leather`, `wood`, `cloth`, `stone`, `gem`; plus `color` (hex), `seed`, and kind options (`wear`, `fuller`, `edge`, `wraps`, `brushed`). |
| `texture_size` | Power of two. 256 for small clutter, 512 for weapons, 1024 only for large hero items. |
| `nif` | `profile` (`weapon`, `clutter`, `static`), `prn` (weapons: `SideWeapon`, `BackWeapon`), `mass`, `havok_material`, `glossiness`. |
| `paths` | Data-relative output paths: always inside your own prefix folder (`meshes\AK\…`, `textures\AK\…`, `textures\menus\icons\AK\…`). Never vanilla paths, unless it's an intentional replacer. |
| `record` | What the plugin record needs: `type`, `editor_id`, `name`, `template` (vanilla EditorID whose stats are the balance baseline). |

**Translating a prompt into a recipe:** "a curved elven-looking dagger, dark blade, silver fittings" → `blade_weapon` with `curve: 0.06`, `taper: 0.4`, `tip_length` longer, `guard_style: curved`, blade `color` dark (`#3a3f48`), fittings `metal` `#d8dce2`, `template: WeapElvenDagger`. Then **look at `preview.png`** and adjust. Iterate until the silhouette reads well from the front and three-quarter views at icon size.

## 4. Quality rules for generated art

1. **Scale against vanilla.** Extract a comparable vanilla mesh (`assetkit.bsa find … dagger`) and compare `nif info` bounds with your manifest `stats`. Measured vanilla bounds (Y, grip at 0): Crusader's longsword −13…+67.5 (1,370 tris), Knights shortsword −11…+41 (870), Mace of Zenithar −18…+38.5 (1,021). The example dagger is −6.5…+29 (516).
2. **Triangle budgets:** weapons ≤ 2,500 (the vanilla weapons measured above use 870–1,370), clutter ≤ 1,500, statics ≤ 6,000 per shape. `validate` enforces these.
3. **Own folders only.** New files never overwrite vanilla or other mods' paths. `install` refuses to overwrite unless `--force`, and backs up first.
4. **One texture atlas per asset**, with power-of-two sizes and full mipmaps, plus an `_n.dds` next to every diffuse texture.
5. **Look before you ship.** Open `preview.png` and `icon_preview.png` every iteration. If the silhouette is unclear at 64 px, change the geometry, not the texture.
6. **Lore fit.** Match the palette and shapes of the material tier you claim (iron: dark, worn; elven: gold-green, curved; glass: green translucent; daedric: black and red). Name and price it like vanilla.

## 5. Extending the framework

- **New generator:** add a function to `generators.py` returning `(Mesh, atlas)` and register it in `GENERATORS`. Build with the primitives in `mesh.py` (`box`, `cylinder`, `lathe`, `extrude`, `loft`, `merge`, `atlas_rect`, `split_sharp`). Follow the axis conventions in `mesh.py`. Good next candidates: `axe`, `mace`, `staff`, `bow` (needs an animated NIF, so not yet), `ring` (needs a ground model and inventory icon only), `bottle`/`goblet`/`crate` (clutter), `pillar`/`statue` (static).
- **New material:** add a `kind` to `texture.material()`. It must return a color, height and spec layer in 0..1.
- **Kitbashing vanilla:** `mesh_from_nif()` loads vanilla geometry (NiTriShape/NiTriStrips) as a `Mesh`. Combine it with generated parts, then build normally. Respect that vanilla assets are Bethesda's: kitbashed meshes can ship in mods for Oblivion (common practice), but third-party mod assets need their author's permission.
- **External art (AI generators, artists, Blender):** export OBJ, then convert to a `Mesh` (an OBJ loader is a small, welcome addition to `mesh.py`), reduce polygons, scale to vanilla, and run it through `nifbuild.build`. The same validation applies.
- **Not supported yet:** skinned armor/clothing (needs NiSkinInstance/NiSkinData/NiSkinPartition and body weighting), animated objects and creatures, bows, MOPP collision for big architecture. The NIF module refuses these block types instead of writing broken files.

## 6. In-game acceptance test (required for the first asset of each new generator)

1. `install` the build and create the record (`records` → TES4Edit `Agent_CreateRecordsFromAssets.pas` → save plugin → activate it).
2. Start the game via `obse_loader.exe`, then in the console: `player.additem <LO-FormID> 1` (`tools\modlint.py find AKDuskfangDagger` gives the ID).
3. Check: inventory icon shows; equip it (in hand, on the hip when sheathed); drop it (falls, doesn't jitter or fall through the floor); the blade shines with light; the normal map bumps the right way (fuller looks recessed, not raised; if inverted, set `"normal_green": "gl"` and rebuild); no red "!" (missing mesh) and no purple (missing texture).
4. Record the result in the asset's `report.md` under a "## In-game test" heading, and in `assets\registry.json` (`"in_game_verified": true`).
