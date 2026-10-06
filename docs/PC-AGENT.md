# PC agent: start here

You are the local Claude on Yuri's PC. The repo clone is `C:\Users\Shadow\Desktop\Games\Oblivion-repo`; the GOG game is `C:\Users\Shadow\Desktop\Games\Oblivion`. A cloud Claude session builds TES4Forge in this repo but can't see the PC, so it hands PC work to you as Markdown files. Read this file first, then the **current handoff** below.

## Current handoff

Always also saved, self-contained, as [`docs/PC-HANDOFF-CURRENT.md`](PC-HANDOFF-CURRENT.md).

| | |
|---|---|
| **Do now** | [`docs/26-forge-phase3b-plain-cs-recon-pc-handoff.md`](26-forge-phase3b-plain-cs-recon-pc-handoff.md): CS script-editor recon with the **plain** `TESConstructionSet.exe` (no OBSE, no CSE, no admin), plus read-only facts for the later script-extender decision. CS launch approved by Yuri; nothing is saved. |
| **Branch** | `forge/phase3-plugin` (check it out yourself) |
| **Send back** | §8 of handoff 26 |

## How this works

1. Yuri passes you a handoff file (or points you at this table). Each handoff has the same parts: goal, steps, failure table, rules, and what to report.
2. Do exactly the steps. If something fails, **report it; don't work around it** by editing tests, curated data or ranking code, or by touching files the handoff doesn't name.
3. End with the "Report back" section. Yuri pastes your report into the cloud session, which answers with the next handoff and updates the table above.

## Standing rules (from `AGENTS.md` and the forge prompt)

- **Commits:** never commit Bethesda-derived data or local outputs: `vanilla_index.jsonl`, `vanilla_commands.jsonl`, `forge-kb.sqlite`, `kb_log.txt`, `forge-builds\`, `_audit\`.
- **The GOG copy** (`Oblivion\`) is the clean dev install. **The Steam copy** is the Rebirth+ play setup. Touch the Steam copy only to deploy a finished, packaged mod through Vortex, and only when a handoff says so.
- **Research mods** are reference only: never in Vortex or either Data folder.
- **Protected files:** never modify `Oblivion.esm`, official DLC, or other authors' plugins.
- **No game or CS launches** and no mouse/keyboard driving unless the handoff asks for it. Never while the game runs.
- **Bridge token:** never print or copy `Oblivion\.cs_bridge_token`.

## History

| # | Handoff | Result |
|---|---|---|
| 16 | `16-forge-phase1-handoff.md`: phase 1 merge patch on the PC | done: sha256 `c1e5a675…` |
| 17 | `17-forge-phase2-pc-handoff.md`: knowledge store, run 1 | 18/20; ranking fixed in the cloud |
| 18 | `18-forge-phase2-pc-run2-handoff.md`: knowledge store, run 2 | 20/20, phase 2 merged (PR #1) |
| 19 | `19-forge-phase3-pc-recon-handoff.md`: phase 3 recon | done: vanilla bytes, bridge path bug, shared Plugins.txt/INI/Saves |
| 20 | `20-forge-phase3a-pc-handoff.md`: phase 3a layout proof + Searing Bolt | ALCH/ENCH/INGR/SGST PASS; MGEF ESCE arrays fixed; sha256 matched; 3c decision A |
| 21 | `21-forge-phase3a-rerun-pc-handoff.md`: array fix + full layout survey | SPEL+MGEF PASS; --all 63 types, 0 mismatches, only REFR XSED tails (fixed) |
| 22 | `22-forge-phase3a-allpass-pc-handoff.md`: --all must PASS + raw list | PASS on Oblivion.esm (63 types) + Knights.esp (37); raw list received; Track E merge: not yet |
| 23 | `23-forge-layout-coverage-pc-handoff.md`: layout coverage (most raw now named) | all bytes identical; CLMT TNAM tail + 3 size variants (fixed); top raw down to 8,181 |
| 24 | `24-forge-layout-variants-pc-handoff.md`: layout variants | PASS Oblivion.esm (63) + Knights.esp (37); variants fixed; raw now scripts/model hashes/PGRR/PKDT |
| 25 | `25-forge-phase3b-cs-recon-pc-handoff.md`: CS script-editor recon (CS launch approved) | blocked: `obse_loader -editor` loads CSE v11, which needs admin |
| 26 | `26-forge-phase3b-plain-cs-recon-pc-handoff.md`: recon with the plain CS + facts for the OBSE decision | **pending** |
