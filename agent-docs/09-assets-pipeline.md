# 09 · Assets: meshes, textures, sounds, UI

> **Generating new art?** Use the assetkit pipeline in [11-asset-creation.md](11-asset-creation.md). It produces files that follow every convention below and validates them. This doc covers conventions and hand-made or external assets.

## Folder conventions (inside `Data\`)

```
meshes\<ModPrefix>\...           new meshes in your own folder; never overwrite vanilla paths unless it's a replacer
textures\<ModPrefix>\...         mirror the mesh folder structure
textures\menus\icons\<ModPrefix>\...   inventory icons (.dds)
sound\fx\<ModPrefix>\...         sound effects referenced by SOUN
sound\voice\<Plugin.esp>\<race>\<m|f>\...   generated voice paths (plugin filename!)
menus\                           UI XML (file-level replacement, last install wins)
```
Records store paths **relative to the type root**: `MODL` = `<ModPrefix>\sword.nif` (under `meshes\`), `ICON` = `<ModPrefix>\sword.dds` (under `textures\menus\icons\` for items). An absolute path or a stray `Data\` prefix breaks the asset.

## Meshes

- Start from a vanilla mesh of the same kind (extract it with `python -m assetkit.bsa extract …`, run from `tools\`) so the node structure, collision and attach nodes are right.
- Validate in NifSkope: `Spells → Sanitize → Reorder Blocks`, `Spells → Batch → Update Tangent Space` for normal-mapped meshes, and check `bhkRigidBody` layer and material, texture paths, and that no `NiStencilProperty` or `NiAlphaProperty` is misused.
- Armor/clothing: weight-paint to the Oblivion skeleton (`Bip01 …`). Male and female variants (`MODL`/`MOD2`/`MOD3`/`MOD4` and their icons). Ground models.
- xEdit's `Edit Scripts\NIF - *.pas` scripts batch-edit texture paths and tangents across many meshes.

## Textures

- assetkit writes DXT1/DXT5 DDS with mipmaps itself (`assetkit.texture.encode_dds`). For converting external images you can also use `texconv.exe` (in the xEdit Edit Scripts folder): `Texconv.exe -f BC3_UNORM -m 0 -y -o out_dir src.png` (BC3 = DXT5). Use `BC1_UNORM` (DXT1) for opaque textures and `BC3` for alpha. Normal maps go in `name_n.dds` (the alpha channel holds specular strength).
- Powers of two; mipmaps required (`Edit Scripts\DDS - Find textures without mipmaps.pas` finds bad ones).
- Replacing vanilla textures needs ArchiveInvalidation (BSA redirection) on the user's side.

## Sound and voice

- SOUN: point to `.wav`, set min/max attenuation and flags (random frequency shift, loop).
- Dialogue: write responses in the CS → record or generate audio → place `.mp3` + `.lip` at the generated path → "Generate Lip File" in the CS. Without audio, subtitles display for roughly the text length only if a silent voice file exists, so provide silent mp3s for every response or use a silent-voice resource.

## UI

- Menus are XML in `menus\` (e.g. `menus\main\hud_main_menu.xml`). They conflict with UI overhauls (DarnifiedUI, NorthernUI) at the file level. Patch carefully, or avoid UI edits unless asked.

## Packaging assets

- A loose-file layout is simplest. A BSA named after the plugin (`MyMod.bsa` next to `MyMod.esp`) auto-loads in Oblivion and reduces file-conflict noise. Build it with a BSA tool, keeping sound files uncompressed.
- Include a file list in the readme so users can detect overwrites.
