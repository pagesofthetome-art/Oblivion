# assets/

Source and output of the assetkit pipeline (see `agent-docs/11-asset-creation.md`).

| Folder / file | Contents | Edit by hand? |
|---|---|---|
| `recipes\<Id>.json` | Asset recipes (the source of truth for each generated asset) | Yes. This is what agents and users change. |
| `build\<Id>\` | Generated output: `Data\` mirror, `preview.png`, `icon_preview.png`, `texture_preview.png`, `manifest.json`, `report.md` | No. Regenerate with `python -m assetkit.build build`. |
| `registry.json` | Assets installed into `Oblivion\Data`, with their files, record hints and backups | No. Written by `install`. |

Run commands from `Games\tools`:
```
python -m assetkit.build build ..\assets\recipes\AKDuskfangDagger.json
```
