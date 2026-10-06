# Rebirth Plus merge patch builder
Bash-style merge patch for Oblivion. Run `build_patch.py` after editing `build_cfg.json`.
- Plugins are read with `tes4_plugin.py` (in `tools/`).
- The paths at the top of `build_patch.py` point at local copies of the plugins. Change them for your machine.
- Output: `Rebirth Plus - New Mods Patch.esp`, built from `patchlib.py` (merge and write) and `world_edits.py` (terrain, disable and port jobs).
- **Prefer `forge build specs\rebirth-plus-merge-patch.yaml`.** It runs this same merge with paths from the spec, writes deterministic output (this script's record order depends on Python's hash seed), and logs hashes. `build_patch.py` stays as the reference that the forge tests compare against.
