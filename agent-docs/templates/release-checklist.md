# Release checklist

- [ ] Backups of every modified user file exist in `Oblivion\CSBackups\` (and xEdit's `Data\TES4Edit Backups\`).
- [ ] `modlint lint <plugin>` exits 0; ITMs are only the intentional ones (listed in the readme).
- [ ] `Agent_PluginAudit` has no `ERROR` rows for the plugin.
- [ ] Every script compiled (`SCRIPT_NOT_COMPILED` absent) under the right editor (`obse_loader -editor` when xOBSE syntax is used).
- [ ] EditorIDs prefixed; no duplicates (`DUPLICATE_EDID` absent).
- [ ] Masters minimal and correct; ESP masters only where unavoidable.
- [ ] `modlint conflicts` against the user's load order reviewed; every critical/merge/patch item resolved or documented.
- [ ] Asset paths are relative and every file exists; textures have mipmaps.
- [ ] Every generated asset: `assetkit.build validate` PASS, preview looked at, and the first asset from each new generator passed the in-game test (agent-docs/11 §6).
- [ ] In-game test plan executed (or handed to the user with exact console steps).
- [ ] Readme: requirements, install/uninstall, load order, Bash tags, overridden vanilla records, conflicts, save safety, changelog, credits.
- [ ] The user was told plainly what changed on their machine (files created, modified, moved).
