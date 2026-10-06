"""assetkit build pipeline: recipe JSON -> game-ready files + previews + manifest + validation.

  python -m assetkit.build build   <recipe.json> [--out <assets\\build>]
  python -m assetkit.build validate <build dir>
  python -m assetkit.build install <build dir> [--data <Oblivion\\Data>] [--force] --yes
  python -m assetkit.build list                                  registry of built/installed assets

A build directory mirrors Data\\ so it can be copied (or zipped for a mod release) as-is:
  assets\\build\\<AssetId>\\
      Data\\meshes\\<Prefix>\\...nif
      Data\\textures\\<Prefix>\\...dds, ..._n.dds
      Data\\textures\\menus\\icons\\<Prefix>\\...dds
      preview.png            4-view render sheet (look at it before installing)
      icon_preview.png
      manifest.json          paths, stats, record hints for the plugin (MODL / ICON / EditorID ...)
      report.md              validation results
`install` copies Data\\ files into the game and records them in assets\\registry.json.
It refuses to overwrite existing files unless --force (and then backs them up first).
"""

from __future__ import annotations

import argparse
import hashlib
import zlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from . import generators as G
from . import nif as N
from . import nifbuild as NB
from . import render as RN
from . import texture as T

TOOLS = Path(__file__).resolve().parent.parent
GAMES = TOOLS.parent
ASSETS = GAMES / "assets"
DEFAULT_OUT = ASSETS / "build"
DEFAULT_DATA = GAMES / "Oblivion" / "Data"
REGISTRY = ASSETS / "registry.json"

BUDGETS = {"weapon": 2500, "clutter": 1500, "static": 6000}


def _win(p: str) -> str:
    return p.replace("/", "\\")


def _fs(root: Path, data_rel: str) -> Path:
    return root / "Data" / Path(*_win(data_rel).split("\\"))


def _rel(p: Path) -> str:
    p = p.resolve()
    try:
        return str(p.relative_to(GAMES)).replace("/", "\\")
    except ValueError:
        return str(p)


def build(recipe_path: Path, out_root: Path = DEFAULT_OUT) -> Path:
    r = json.loads(Path(recipe_path).read_text(encoding="utf-8"))
    aid = r["id"]
    out = out_root / aid
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    gen = G.GENERATORS[r["generator"]]
    mesh, atlas = gen(**r.get("params", {}))

    # textures
    tsize = r.get("texture_size", 512)
    regions = []
    for part, rect in atlas.items():
        spec = r["materials"].get(part) or r["materials"].get("default")
        if spec is None:
            raise ValueError(f"recipe has no material for part '{part}' (or 'default')")
        w = max(16, int((rect[2] - rect[0]) * tsize)); h = max(16, int((rect[3] - rect[1]) * tsize))
        kw = {k: v for k, v in spec.items() if k not in ("kind", "color", "seed")}
        regions.append((rect, T.material(spec["kind"], (h, w), spec.get("color", "#a0a0a0"),
                                         spec.get("seed", zlib.crc32(part.encode()) % 1000), **kw)))
    layer = T.atlas(regions, (tsize, tsize))
    paths = r["paths"]
    tex_base = _fs(out, paths["texture"]).with_suffix("")
    T.save_textures(layer, tex_base, r.get("normal_strength", 4.0), normal_green=r.get("normal_green", "dx"))
    (out / "texture_preview.png").write_bytes((tex_base.parent / (tex_base.name + "_preview.png")).read_bytes())
    for junk in tex_base.parent.glob("*_preview.png"):
        junk.unlink()                                     # previews never ship inside Data

    # nif
    n = r.get("nif", {})
    profile = n.get("profile", "weapon")
    nifobj = NB.build(mesh, _win(paths["texture"]), name=r.get("node_name", aid), profile=profile,
                      prn=n.get("prn", "SideWeapon" if profile == "weapon" else None), mass=n.get("mass", 5.0),
                      havok_material=n.get("havok_material", "metal"), glossiness=n.get("glossiness", 50.0))
    nif_path = _fs(out, paths["mesh"])
    nif_path.parent.mkdir(parents=True, exist_ok=True)
    nif_path.write_bytes(N.write(nifobj))

    # previews and icon
    up = "y" if profile == "weapon" else "z"
    RN.render_views(mesh, layer.color, layer.spec, up=up, size=320, title=f"{aid}  ({len(mesh.f)} tris)").save(out / "preview.png")
    if paths.get("icon"):
        icon = RN.render_icon(mesh, layer.color, layer.spec, up=up, size=r.get("icon_size", 64),
                              rotate=-45 if profile == "weapon" else 0)
        icon.save(out / "icon_preview.png")
        ip = _fs(out, paths["icon"]); ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_bytes(T.encode_dds(np.asarray(icon.convert("RGBA")), "DXT5"))

    lo, hi = mesh.bounds
    manifest = {
        "id": aid, "recipe": _rel(Path(recipe_path)), "built": datetime.now().isoformat(timespec="seconds"),
        "generator": r["generator"], "profile": profile,
        "files": sorted(str(p.relative_to(out / "Data")).replace("/", "\\") for p in (out / "Data").rglob("*") if p.is_file()),
        "stats": {"vertices": int(len(mesh.v)), "triangles": int(len(mesh.f)),
                  "bounds_min": [round(float(x), 2) for x in lo], "bounds_max": [round(float(x), 2) for x in hi],
                  "texture_size": tsize,
                  "bound_radius": round(float(np.linalg.norm(mesh.v - (lo + hi) / 2, axis=1).max()), 3)},
        # Values to put on the plugin record (record-relative paths, as the CS/xEdit expect)
        "record_hints": {
            "MODL": _win(paths["mesh"]).split("\\", 1)[1] if _win(paths["mesh"]).lower().startswith("meshes\\") else _win(paths["mesh"]),
            "ICON": _win(paths["icon"]).split("icons\\", 1)[1] if paths.get("icon") and "icons\\" in _win(paths["icon"]).lower() else None,
            **r.get("record", {}),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    validate(out)
    return out


def validate(out: Path) -> dict:
    out = Path(out)
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    checks = []

    def ck(ok, what, detail=""):
        checks.append({"ok": bool(ok), "check": what, "detail": detail})

    data = out / "Data"
    for rel in man["files"]:
        p = data / Path(*rel.split("\\"))
        if rel.lower().endswith(".nif"):
            raw = p.read_bytes()
            try:
                nifobj = N.read(raw)
                ck(N.write(nifobj) == raw, f"{rel}: NIF parses and re-serialises identically")
                types = [b.type for b in nifobj.blocks]
                ck("bhkCollisionObject" in types, f"{rel}: has Havok collision")
                ck("NiBinaryExtraData" in types, f"{rel}: has tangent space data (normal maps)")
                for s in nifobj.of_type("NiSourceTexture"):
                    fn = s["file_name"]
                    ck(not (":" in fn or fn.startswith("\\")), f"{rel}: texture path relative ({fn})")
                    ck(fn.lower().startswith("textures\\"), f"{rel}: texture path under textures\\", fn)
                    exists = (data / Path(*fn.split("\\"))).is_file() or (DEFAULT_DATA / Path(*fn.split("\\"))).is_file()
                    ck(exists, f"{rel}: referenced texture exists in build or game Data", fn)
                tris = sum(d["num_triangles"] for d in nifobj.of_type("NiTriShapeData"))
                budget = BUDGETS.get(man["profile"], 3000)
                ck(tris <= budget, f"{rel}: triangle budget", f"{tris} / {budget}")
            except Exception as exc:
                ck(False, f"{rel}: NIF readable", f"{type(exc).__name__}: {exc}")
        elif rel.lower().endswith(".dds"):
            res = T.check_dds(p)
            ck(res["ok"], f"{rel}: DDS valid ({res.get('format')} {res.get('width')}x{res.get('height')}, "
               f"{res.get('mipmaps')} mips)", "; ".join(res["problems"]))
    if man["profile"] == "weapon":
        lo, hi = man["stats"]["bounds_min"], man["stats"]["bounds_max"]
        ck(lo[1] < 0 < hi[1], "weapon: grip origin inside the weapon (y spans 0)", f"y {lo[1]}..{hi[1]}")
        ck(hi[1] > abs(lo[1]), "weapon: blade/head points along +Y")
    ok = all(c["ok"] for c in checks)
    lines = [f"# Validation: {man['id']}", "", f"Result: **{'PASS' if ok else 'FAIL'}**  ({datetime.now():%Y-%m-%d %H:%M})", "",
             "| | Check | Detail |", "|---|---|---|"]
    lines += [f"| {'✅' if c['ok'] else '❌'} | {c['check']} | {c['detail']} |" for c in checks]
    lines += ["", "Previews: `preview.png`, `icon_preview.png`, `texture_preview.png`. "
              "Static checks cannot prove the asset looks right in game - test it (agent-docs/11 §6)."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": ok, "checks": checks}


def _registry() -> dict:
    if REGISTRY.is_file():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {"assets": {}}


def install(out: Path, data_dir: Path = DEFAULT_DATA, force=False, yes=False) -> list[str]:
    out = Path(out)
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    res = validate(out)
    if not res["ok"]:
        raise SystemExit(f"refusing to install {man['id']}: validation failed (see {out / 'report.md'})")
    if not yes:
        raise SystemExit("refusing: install writes into the game's Data folder. Re-run with --yes after the user agreed.")
    written, backups = [], []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for rel in man["files"]:
        src = out / "Data" / Path(*rel.split("\\")); dst = data_dir / Path(*rel.split("\\"))
        if dst.exists():
            if hashlib.sha1(dst.read_bytes()).digest() == hashlib.sha1(src.read_bytes()).digest():
                continue
            if not force:
                raise SystemExit(f"refusing to overwrite existing {dst} (use --force; it will be backed up)")
            bak = data_dir.parent / "CSBackups" / "assets" / stamp / Path(*rel.split("\\"))
            bak.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(dst, bak); backups.append(str(bak))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst); written.append(str(dst))
    reg = _registry()
    reg["assets"][man["id"]] = {"installed": datetime.now().isoformat(timespec="seconds"), "files": man["files"],
                                "record_hints": man["record_hints"], "build_dir": str(out), "backups": backups}
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, indent=2), encoding="utf-8")
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build"); s.add_argument("recipe", type=Path); s.add_argument("--out", type=Path, default=DEFAULT_OUT)
    s = sub.add_parser("validate"); s.add_argument("build_dir", type=Path)
    s = sub.add_parser("install"); s.add_argument("build_dir", type=Path); s.add_argument("--data", type=Path, default=DEFAULT_DATA)
    s.add_argument("--force", action="store_true"); s.add_argument("--yes", action="store_true")
    sub.add_parser("list")
    s = sub.add_parser("records", help="write TES4Edit Agent-Reports\\asset-records.txt for Agent_CreateRecordsFromAssets.pas")
    s.add_argument("build_dirs", nargs="+", type=Path); s.add_argument("--plugin", required=True)
    s.add_argument("--xedit", type=Path, default=GAMES / "TesIvedit" / "TES4Edit 4.1.5f")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        out = build(a.recipe, a.out)
        print(f"built {out}")
        print((out / "report.md").read_text(encoding="utf-8"))
    elif a.cmd == "validate":
        res = validate(a.build_dir)
        print((Path(a.build_dir) / "report.md").read_text(encoding="utf-8"))
        return 0 if res["ok"] else 2
    elif a.cmd == "install":
        for w in install(a.build_dir, a.data, a.force, a.yes):
            print("installed", w)
    elif a.cmd == "records":
        lines = ["# TargetPlugin|Signature|NewEditorID|Name|TemplateEditorID|MODL|ICON|MODB"]
        for d in a.build_dirs:
            man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            h = man["record_hints"]
            if not h.get("template"):
                raise SystemExit(f"{d}: recipe 'record' has no 'template' EditorID to copy stats from")
            lines.append("|".join([a.plugin, h.get("type", "WEAP"), h["editor_id"], h.get("name", h["editor_id"]),
                                   h["template"], h["MODL"], h.get("ICON") or "", str(man["stats"]["bound_radius"])]))
        dst = a.xedit / "Agent-Reports" / "asset-records.txt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("\n".join(lines) + "\n", encoding="cp1252")
        print(f"wrote {dst}:"); print("\n".join(lines))
    elif a.cmd == "list":
        for k, v in _registry()["assets"].items():
            print(f"{k}: installed {v['installed']}  MODL={v['record_hints'].get('MODL')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
