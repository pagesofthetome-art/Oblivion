"""Deterministic Vortex-installable zip: plugin at the archive root plus a readme."""

from __future__ import annotations

import zipfile
from pathlib import Path

FIXED_TIME = (2006, 3, 20, 0, 0, 0)   # Oblivion's release date: keeps the zip bytes stable


def readme_text(spec, log: dict) -> str:
    out = log.get("outputs", {}).get("plugin", {})
    lines = [
        f"{spec.output_plugin}",
        "=" * len(spec.output_plugin),
        "",
        str(spec.raw.get("intent", "")).strip(),
        "",
        f"Built by TES4Forge {log.get('tool_versions', {}).get('forge', '?')} from spec {spec.path.name} "
        f"(sha256 {spec.sha256[:16]}).",
        f"Plugin sha256: {out.get('sha256', '?')}",
        "",
        "Masters (must be installed and load before this plugin):",
        *[f"  - {m}" for m in log.get("masters", [])],
        "",
    ]
    notes = spec.section("output").get("install_notes") or []
    if notes:
        lines += ["Install notes:", *[f"  - {n}" for n in notes], ""]
    tp_ = spec.raw.get("test_plan") or []
    if tp_:
        lines += ["Test plan:", *[f"  {i + 1}. {t}" for i, t in enumerate(tp_)], ""]
    return "\r\n".join(lines) + "\r\n"


def make_zip(spec, out_dir: Path, plugin_path: Path, log: dict) -> Path:
    version = str(spec.section("output").get("version", "1.0"))
    z = out_dir / f"{spec.name}-{version}.zip"
    readme_name = Path(spec.output_plugin).stem + " - readme.txt"
    entries = [(spec.output_plugin, plugin_path.read_bytes()),
               (readme_name, readme_text(spec, log).encode("utf-8"))]
    with zipfile.ZipFile(z, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in sorted(entries):
            zi = zipfile.ZipInfo(name, FIXED_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, data)
    return z
