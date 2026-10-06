# 03 · Data files and formats

## 1. Plugin files (.esm / .esp), format "TES4"

| Property | Meaning |
|---|---|
| `.esm` extension + ESM flag (`0x1` on the `TES4` header record) | Master. Loads before all ESPs. The vanilla CS only accepts ESM-flagged files as masters. |
| `.esp` | Plugin. Can be a master of another plugin (the game allows it; the vanilla CS doesn't). |
| ESM-flagged `.esp` | Loads in the master block. Used by "ESMify" workflows and by some frameworks. |

### Binary layout (little-endian). Implemented in `tools\tes4_plugin.py`.

```
Record header 20 bytes : Type[4]  DataSize u32  Flags u32  FormID u32  VersionControl u32
GRUP header   20 bytes : "GRUP"   GroupSize u32 (includes header)  Label[4]  GroupType i32  Stamp u32
Subrecord              : Type[4]  Size u16  Data[Size]
                         "XXXX" (size 4, u32 N) means the next subrecord's real size is N
Compressed record      : Flags & 0x00040000 -> Data = DecompressedSize u32 + zlib stream
```
Oblivion headers are **20 bytes**. Skyrim and Fallout 3 use 24, so don't reuse their parsers.

**File header `TES4`:** `HEDR` (float version: 1.0 for Oblivion.esm, 0.8 for some old plugins; i32 numRecords; u32 nextObjectID), `CNAM` author, `SNAM` description, then `MAST` (master filename) + `DATA` (u64, ignored) pairs.

**Group types:** 0 Top (label = record type), 1 World children (label = WRLD FormID), 2/3 interior cell block/sub-block, 4/5 exterior block/sub-block (label = grid), 6 cell children, 7 topic children (INFOs of a DIAL), 8 persistent, 9 temporary, 10 visible-distant children.

**Common record flags:** `0x20` Deleted · `0x400` Persistent (refs) / Quest item (base) · `0x800` Initially disabled · `0x1000` Ignored · `0x8000` Visible when distant · `0x20000` Dangerous / Off-limits (cells) · `0x40000` Compressed · `0x80000` Can't wait.

### FormIDs

- In a file: `MM OOOOOO`, where `MM` indexes that file's own `MAST` list. `MM == number of masters` means a new record defined by this file. `MM > number of masters` is invalid and corrupt (xEdit calls it "unclamped").
- In game/console: `LL OOOOOO`, where `LL` is the load-order index. `modlint find 0211B9FB` resolves a console FormID with the current load order.
- Load-order-independent identity (used in all agent output): `Owner.esp:OOOOOO`, e.g. `Oblivion.esm:02319B` (LeatherBoots).
- **Never hard-code load-order FormIDs** in scripts or docs meant for others. In scripts, use EditorIDs (resolved at compile time) or xOBSE `GetFormFromMod "Mod.esp" "OOOOOO"` for soft dependencies.

### Record types an agent handles most

| Group | Types |
|---|---|
| Items | `WEAP ARMO CLOT AMMO MISC KEYM BOOK ALCH INGR APPA SLGM SGST LIGH` |
| World objects | `STAT ACTI CONT DOOR FURN FLOR TREE GRAS SBSP ANIO` |
| Actors | `NPC_ CREA RACE CLAS FACT HAIR EYES CSTY PACK IDLE` |
| Magic | `SPEL ENCH MGEF` (MGEF is hard-coded; don't add new effects without OBSE tricks) |
| Leveled | `LVLI LVLC LVSP` |
| Quests/dialogue | `QUST DIAL INFO SCPT GLOB` |
| World | `WRLD CELL LAND PGRD ROAD REGN WTHR CLMT WATR LTEX` + placed `REFR ACHR ACRE` |
| Settings | `GMST` (setting name in EDID; the type comes from the first letter: f float, i int, s string) |

Full per-field definitions: xEdit's `wbDefinitionsTES4.pas`, or open a record in TES4Edit, where every field is labelled.

## 2. Archives (.bsa, version 103)

- Contain `meshes\`, `textures\`, `sounds\`, `music\`, `menus\`, `trees\`, `distantlod\`, `lsdata\`, `fonts\`. Vanilla archives load via `SArchiveList` in `Oblivion.ini`. DLC BSAs load when they share the plugin's base name (`Knights.esp` loads `Knights.bsa`; `DLCShiveringIsles - *.bsa` are listed in the INI).
- **ArchiveInvalidation**: by default, a loose file only replaces a BSA file in some cases (textures often fail). The standard fix is "BSA redirection" (Wrye Bash or OBMM sets it up). Tell users when a mod ships loose textures or meshes that replace vanilla ones.
- Packing: use **BSA Browser / BSA Commander / Wrye Bash**. Vanilla `Oblivion - Meshes.bsa`-style compression flags must match: some sound files must stay uncompressed.

## 3. Meshes (.nif), Gamebryo NIF 20.0.0.4/20.0.0.5

- Edit with **NifSkope** (2.0 dev builds read and write Oblivion NIFs). Export from Blender with the **Blender NIF plugin** (pyffi-based; Blender 2.4x-era tools or the newer io_scene_niftools for 2.8+, which has an Oblivion profile).
- The engine needs: a root `NiNode`; `bhkCollisionObject` → `bhkRigidBody` (Havok layer and material) for anything solid; `NiTriStrips`/`NiTriShape` with `NiTexturingProperty` → `NiSourceTexture` paths **relative to `textures\`**; `BSXFlags` for animated/havok objects.
- Weapons and armor need specific node names (`Bip01` skeleton weighting for armor; `Scb` for scabbards; `Weapon` attach). Copying a vanilla NIF of the same type and editing it is the safest route.
- Crash causes: invalid collision, missing or extra controllers, too many bones per partition, absolute texture paths (pink or missing, not a crash), NiStringExtraData typos.

## 4. Textures (.dds)

- DXT1 (no alpha or 1-bit alpha), DXT3 (sharp alpha), DXT5 (smooth alpha). Normal maps go in `*_n.dds` (alpha = specular); glow maps in `*_g.dds`. Always generate **mipmaps**. Dimensions must be powers of 2.
- `texconv.exe` ships with xEdit in `TesIvedit\TES4Edit 4.1.5f\Edit Scripts\Texconv.exe` (`Texconvx64.exe`), and you can script it, e.g. `texconv -f DXT5 -m 0 -y -o out in.png`.
- Icons: `textures\menus\icons\...` (DDS, typically 64×64 or 128×128 with alpha).

## 5. Sounds, voice, lip

- Sound effects: `.wav` (PCM 16-bit, 44.1/22.05 kHz) referenced by `SOUN` records. Music: `.mp3` in `Data\Music\{Explore,Public,Dungeon,Battle,Special}`.
- Voice: `sound\voice\<plugin.esp>\<race>\<sex>\<quest>_<topic>_<INFOformid>_<response#>.mp3` plus `.lip`. The path uses the **plugin filename**, so renaming the plugin breaks all voice paths. Generate `.lip` files in the CS (Dialogue → response → "Generate Lip File"; needs the wav present). Silent mods without voice files need a long-enough silent mp3 or the text flashes by; the "Elys Silent Voice" style plugins exist for that.

## 6. Other data

- `menus\*.xml`: UI (Oblivion's custom XML dialect). Conflicts are file-level, so the last-installed file wins. DarnifiedUI/NorthernUI replace many of these.
- `distantlod\`, `trees\`, `textures\landscapelod\`: LOD generated by TES4LODGen (via xEdit `-O:`) or the CS's "Generate LOD". Mods that add exterior objects should mention regenerating LOD.
- `Data\OBSE\Plugins\*.dll`: OBSE plugins. `Data\OBSE\obse.ini`: xOBSE settings.
- Saves: `Documents\My Games\Oblivion\Saves\*.ess` plus `.obse` co-saves.

## 7. INI files

- `Documents\My Games\Oblivion\Oblivion.ini` is the live INI, created from `Oblivion_default.ini` on first launch. Important keys: `[Archive] SArchiveList`, `bInvalidateOlderFiles`; `[General] uGridsToLoad` (leave at 5), `bUseHardDriveCache`; `[Display]` resolution and shaders.
- The CS reads the same `Oblivion.ini`. To make an ESP depend on another ESP, use CSE or flag the master ESM temporarily in TES4Edit (see `04-construction-set.md` §5). Don't use INI hacks.
