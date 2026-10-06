# Agent knowledge base: Oblivion modding

Read in this order the first time; afterwards jump to what the task needs.

| # | Doc | Read when |
|---|---|---|
| 01 | [Oblivion game primer](01-oblivion-game-primer.md) | Always first. What the game is, its systems, the mod ecosystem. |
| 02 | [Engine internals & "source code"](02-engine-and-source.md) | Designing anything scripted, persistent or save-sensitive. |
| 03 | [Data files & formats](03-data-files-and-formats.md) | Touching plugins, FormIDs, BSAs, NIF/DDS, INI. |
| 04 | [Construction Set](04-construction-set.md) | Scripts, placement, lip files, pathgrids; driving the CS bridge. |
| 05 | [TES4Edit](05-tes4edit.md) | Inspecting, cleaning, patching, batch edits, headless xEdit. |
| 06 | [Scripting (vanilla + xOBSE)](06-scripting.md) | Writing or reviewing any script. |
| 07 | [Conflicts, compatibility & crashes](07-conflicts-and-compatibility.md) | Before finishing **any** mod; whenever something breaks. |
| 08 | [Prompt → mod playbook](08-prompt-to-mod-playbook.md) | At the start of every user request. |
| 09 | [Assets pipeline](09-assets-pipeline.md) | Meshes, textures, sounds, UI. |
| 10 | [Testing & release](10-testing-and-release.md) | Verifying and handing over. |
| 11 | [Asset creation (assetkit)](11-asset-creation.md) | Any request for new meshes, textures or icons: recipes, generators, validation, install, records. |

Templates: [mod spec](templates/mod-spec.md) · [asset spec](templates/asset-spec.md) · [compatibility report](templates/compat-report.md) · [release checklist](templates/release-checklist.md)

Local primary references (grep these instead of recalling them):
- `script extender\obse_command_doc.html`: every xOBSE command, event and expression rule.
- `script extender\obse_whatsnew.txt`: xOBSE version history (this copy is 22.13).
- `TesIvedit\TES4Edit 4.1.5f\Edit Scripts\xEditAPI.pas`: xEdit scripting API declarations.
- `TesIvedit\TES4Edit 4.1.5f\whatsnew.md`: xEdit features and command-line switches.
- `Oblivion\CSReadme.txt`, `Oblivion\Readme.txt`: official notes.

Online references: UESP (en.uesp.net/wiki/Oblivion_Mod:...), CS Wiki mirror (cs.uesp.net), xOBSE GitHub (github.com/llde/xOBSE), xEdit GitHub (github.com/TES5Edit/TES5Edit, `wbDefinitionsTES4.pas`).
