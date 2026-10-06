"""Capability registry: named building blocks with swappable providers.

Each capability says what it takes and gives, which providers can do it (tried in
order), the test that proves it, and how much we trust it. `forge caps` prints
the table with live availability for this machine.

Confidence levels (from OBLIVION_AI_MOD_DEVELOPER_BRAIN.md §6):
CONFIRMED_RUNTIME, CONFIRMED_MULTI_SOURCE, HIGH_CONFIDENCE, HYPOTHESIS, CONFLICTED, REJECTED.
Status: implemented (forge's own code), wrapped (existing tool behind forge), planned.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]     # repo root (Desktop\Games on the PC)
TOOLS = ROOT / "tools"
import sys as _sys
if str(TOOLS) not in _sys.path:
    _sys.path.insert(0, str(TOOLS))
from gamepaths import game_dir, workspace_dir  # noqa: E402

XEDIT_EXE = workspace_dir() / "TesIvedit" / "TES4Edit 4.1.5f" / "TES4Edit.exe"
CS_TOKEN = game_dir() / ".cs_bridge_token"
OBSE_LOADER = game_dir() / "obse_loader.exe"


@dataclass
class Provider:
    name: str
    entry: str                       # module/function or command that does the work
    requires: list[str] = field(default_factory=list)   # "file:<path>", "module:<name>", "windows", "exe:<name>"

    def missing(self) -> list[str]:
        out = []
        for req in self.requires:
            kind, _, val = req.partition(":")
            if kind == "file" and not Path(val).exists():
                out.append(f"missing {val}")
            elif kind == "module":
                try:
                    __import__(val)
                except Exception:
                    out.append(f"python module {val}")
            elif kind == "windows" and os.name != "nt":
                out.append("needs Windows")
            elif kind == "exe" and not shutil.which(val):
                out.append(f"{val} not on PATH")
        return out


@dataclass
class Capability:
    name: str
    summary: str
    inputs: str
    outputs: str
    providers: list[Provider]
    test: str
    confidence: str
    status: str
    phase: int = 1

    def provider(self) -> Provider | None:
        """First provider whose requirements are met on this machine."""
        for p in self.providers:
            if not p.missing():
                return p
        return None


def _p(name, entry, *req):
    return Provider(name, entry, list(req))


_ASSETKIT = ("module:numpy", "module:PIL")
REGISTRY: list[Capability] = [
    Capability("record.read", "Parse TES4 plugins (records, groups, compressed data).",
               "plugin path", "Plugin/Record objects",
               [_p("tes4_plugin", "tools/tes4_plugin.py:iter_records")],
               "forge.tests.test_merge_patch", "CONFIRMED_MULTI_SOURCE", "wrapped"),
    Capability("record.merge", "Bash-style merge of overridden records (lists, structs, quests, cells, INFO).",
               "load order + merge config", "merged records",
               [_p("patchlib", "tools/merge-patch/patchlib.py + forge/providers/merge_patch.py")],
               "forge.tests.test_merge_patch", "HIGH_CONFIDENCE", "implemented"),
    Capability("record.write", "Write a new plugin with a computed master list.",
               "records", ".esp bytes",
               [_p("patchlib.Writer", "tools/merge-patch/patchlib.py:Writer"),
                _p("TES4Edit", "tools/xedit_run.py", f"file:{XEDIT_EXE}", "windows")],
               "forge.tests.test_merge_patch (round-trip)", "HIGH_CONFIDENCE", "implemented"),
    Capability("record.encode", "Encode subrecords from named fields (schema-driven, pad bytes preserved).",
               "spec records / decoded fields", "subrecord bytes",
               [_p("forge.records", "tools/forge/records.py + kb/data/record_schemas.json")],
               "forge.tests.test_plugin_build; PC: forge layout-check (re-encode vanilla SPEL/MGEF)",
               "HIGH_CONFIDENCE", "implemented", 3),
    Capability("record.lint", "UDR, deleted, ITM, bad FormIDs, masters, uncompiled scripts.",
               "plugin + Data folder", "issue list",
               [_p("modlint", "tools/modlint.py:lint_plugin")],
               "verified against official DLC cleaning stats (AGENTS.md)", "CONFIRMED_RUNTIME", "wrapped"),
    Capability("conflict.check", "Overrides across a load order, lost edits, severity.",
               "load order", "conflict report",
               [_p("modlint", "tools/modlint.py:collect_conflicts"),
                _p("TES4Edit", "Agent_ConflictReport.pas", f"file:{XEDIT_EXE}", "windows")],
               "manual (Rebirth+ audit 2026-10-06)", "HIGH_CONFIDENCE", "wrapped"),
    Capability("land.edit", "Restore/borrow exterior LAND, disable placed refs, port patches to other masters.",
               "world_edits jobs", "WRLD/CELL/LAND/REFR records",
               [_p("world_edits", "tools/merge-patch/world_edits.py")],
               "forge.tests.test_merge_patch", "HIGH_CONFIDENCE", "implemented"),
    Capability("script.compile", "Compile OBScript with forge's own compiler (no Construction Set).",
               "script source", "compiled SCPT", [_p("forge-compiler", "tools/forge/script/compiler.py "
                                                     "(+ vanilla_commands.jsonl, or the spec's commands:)")],
               "forge script-check: 99.86% of vanilla scripts byte-identical (PC 2026-10-06)",
               "CONFIRMED_RUNTIME", "implemented", 3),
    Capability("script.lint", "Static checks on script text (OBSE use, variable order).",
               "script source", "issue list", [_p("modlint", "tools/modlint.py:uses_obse")],
               "phase 3", "HYPOTHESIS", "planned", 3),
    Capability("nif.inspect", "Read NIF block trees and bounds.", "nif path", "block summary",
               [_p("assetkit.nif", "tools/assetkit/nif.py", *_ASSETKIT)],
               "assetkit build reports", "HIGH_CONFIDENCE", "wrapped", 5),
    Capability("nif.build", "Generate original meshes (procedural) as Oblivion NIFs.", "recipe json", "nif",
               [_p("assetkit", "tools/assetkit/build.py", *_ASSETKIT),
                _p("blender-niftools", "Blender 3.6 + NifTools (headless)", "exe:blender")],
               "phase 5: recoloured portal mesh in game", "HYPOTHESIS", "wrapped", 5),
    Capability("skeleton.compare", "Diff two skeleton NIFs (added/removed/moved bones).", "2 nif", "diff",
               [], "phase 5", "HYPOTHESIS", "planned", 5),
    Capability("texture.convert", "Generate/convert DDS textures and icons.", "image/recipe", "dds",
               [_p("assetkit.texture", "tools/assetkit/texture.py", *_ASSETKIT)],
               "assetkit build reports", "HIGH_CONFIDENCE", "wrapped", 5),
    Capability("audio.convert", "Transcode to Oblivion wav/mp3.", "audio", "wav/mp3",
               [_p("ffmpeg", "ffmpeg", "exe:ffmpeg")], "phase 5", "HYPOTHESIS", "planned", 5),
    Capability("cell.place", "Place references in cells.", "placements", "REFR/ACHR/ACRE",
               [_p("cs-bridge", "oblivion_cs_bridge_client.py", f"file:{CS_TOKEN}", "windows")],
               "phase 3", "HYPOTHESIS", "planned", 3),
    Capability("worldspace.create", "New worldspace (pocket dimension).", "spec", "WRLD/CELL/LAND",
               [], "phase 4: pocket dimension survives save/reload", "HYPOTHESIS", "planned", 4),
    Capability("lod.generate", "Distant LOD for new exterior objects.", "load order", "lod files",
               [_p("TES4LODGen", "TES4Edit -lodgen", f"file:{XEDIT_EXE}", "windows")],
               "phase 5", "HYPOTHESIS", "planned", 5),
    Capability("projectile.scan", "Find live projectiles near a ref (xOBSE).", "radius", "refs",
               [], "phase 4: freeze and fire back", "HYPOTHESIS", "planned", 4),
    Capability("projectile.redirect", "Re-aim / re-own projectiles (xOBSE).", "refs + target", "-",
               [], "phase 4: freeze and fire back", "HYPOTHESIS", "planned", 4),
    Capability("portal.create", "Linked portal pair.", "two anchors", "door/activator refs",
               [], "phase 4: linked portal pair", "HYPOTHESIS", "planned", 4),
    Capability("pocket.enter", "Enter pocket dimension, remember return point.", "-", "-",
               [], "phase 4", "HYPOTHESIS", "planned", 4),
    Capability("pocket.return", "Return to the saved point across worldspaces.", "-", "-",
               [], "phase 4", "HYPOTHESIS", "planned", 4),
    Capability("weather.force", "Force/override weather.", "WTHR", "-", [], "phase 4", "HYPOTHESIS", "planned", 4),
    Capability("kb.query", "Answer modding questions in one call: functions, record layouts, vanilla forms, "
               "research techniques, crash signatures.", "question / name / SIG / EditorID", "ranked rows with source + confidence",
               [_p("forge.kb", "tools/forge/kb (forge-kb.sqlite, SQLite FTS5)")],
               "forge.tests.test_kb_queries (20 questions)", "HIGH_CONFIDENCE", "implemented", 2),
    Capability("build.log", "Hashes, tool versions and commands for every build.", "build", "build-log.json",
               [_p("forge.buildlog", "tools/forge/buildlog.py")],
               "forge.tests.test_cli", "HIGH_CONFIDENCE", "implemented"),
    Capability("package.vortex", "Deterministic Vortex-installable zip + readme.", "build folder", "zip",
               [_p("forge.package", "tools/forge/package.py")],
               "forge.tests.test_cli", "HIGH_CONFIDENCE", "implemented"),
    Capability("deploy.verify", "Confirm Vortex deployed the files and the game loads them.", "zip", "report",
               [], "phase 5 (deploy_check.py is referenced in the plan but not in the repo yet)",
               "HYPOTHESIS", "planned", 5),
    Capability("runtime.diagnose", "Freeze probe and logs while the game runs.", "-", "report",
               [_p("oblivion_freeze", "Controller/oblivion_freeze.py", "windows")],
               "manual", "HIGH_CONFIDENCE", "wrapped", 6),
]

BY_NAME = {c.name: c for c in REGISTRY}


def check(names: list[str]) -> list[dict]:
    """Availability rows for the given capability names."""
    rows = []
    for n in names:
        c = BY_NAME.get(n)
        if c is None:
            rows.append({"capability": n, "ok": False, "why": "unknown capability"})
            continue
        prov = c.provider() if c.status != "planned" else None
        why = ""
        if c.status == "planned":
            why = f"planned for phase {c.phase}"
        elif prov is None:
            why = "; ".join(m for p in c.providers for m in p.missing()) or "no provider"
        rows.append({"capability": n, "ok": prov is not None, "provider": prov.name if prov else None,
                     "status": c.status, "confidence": c.confidence, "why": why})
    return rows


def table() -> list[dict]:
    return [dict(capability=c.name, status=c.status, phase=c.phase, confidence=c.confidence,
                 providers=[p.name for p in c.providers],
                 available=(c.provider().name if c.status != "planned" and c.provider() else None),
                 test=c.test, summary=c.summary, inputs=c.inputs, outputs=c.outputs)
            for c in REGISTRY]
