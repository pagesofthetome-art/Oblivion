"""Real Oblivion test locations: pick vanilla cells from the test game's own Oblivion.esm.

Yuri's rule: a playtest is the real game. Test locations are therefore existing vanilla cells,
reached the way a modder would: `coc <InteriorEditorID>`, or `cow <World> X Y` followed by
`player.moveto <map marker>` for an exterior spot. The test actors (dummy, caster, merchant,
townsfolk) live in ForgeTestCells.esp's empty holding cell and are moved next to the player.

Oblivion.esm is only read. The index (interior cells with their reference counts, worldspaces,
and named map markers with their cell and grid) is cached in forge-builds\\playtest\\vanilla-index.json,
keyed by the file's size and modification time.

Default picks (each can be overridden: `--cell <InteriorEditorID>`, `--cell marker:<Map marker name>`,
or `--cell cow:<World>:<x>:<y>`):
  arena   the Imperial City Arena's combat floor (an interior whose EditorID/name says Arena,
          most references wins)
  street  the Market District map marker (a real street with doors, shops, people)
  open    the Weye map marker (open shore road west of the Imperial City)
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

MAP_MARKER = 0x00000010
DEFAULTS = {
    "arena": {"interior_patterns": [r"^arena(arena|pit|combat)", r"^arena", r"arena"],
              "name_patterns": [r"\barena\b"], "label": "Arena combat floor"},
    "street": {"markers": ["Market District", "Talos Plaza District", "Elven Gardens District"],
               "label": "Imperial City street"},
    "open": {"markers": ["Weye", "Pell's Gate", "Aleswell"], "label": "open countryside"},
}
INDEX_VERSION = 1


class VanillaError(RuntimeError):
    pass


@dataclass
class Location:
    key: str                       # arena | street | open | custom
    label: str
    boot: str                      # console command that loads it: "coc X" or "cow W x y"
    moveto: str | None = None      # console FormID of a persistent ref to stand on, or None
    cell_edid: str | None = None   # interior EditorID (for the GetInCell probe)
    world_edid: str | None = None  # worldspace EditorID (for the GetInWorldspace probe)
    detail: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _z(b: bytes | None) -> str:
    return b.split(b"\0", 1)[0].decode("cp1252", "replace") if b else ""


def build_index(esm: Path) -> dict:
    """One pass over Oblivion.esm: interiors, worldspaces, exterior cells' grids, named map markers."""
    import tes4_plugin as tp
    cells: dict[int, dict] = {}
    worlds: dict[int, str] = {}
    markers: list[dict] = []
    refcount: dict[int, int] = {}
    for _, r in tp.iter_records(esm, {"CELL", "WRLD", "REFR", "ACHR"}):
        if r.sig in ("REFR", "ACHR"):
            refcount[r.parent] = refcount.get(r.parent, 0) + 1
            if r.sig == "REFR":
                d = r.data
                # cheap pre-check before parsing subrecords: only map markers carry XMRK
                if b"XMRK" in d:
                    subs = {s.sig: s.data for s in r.subrecords()}
                    if "NAME" in subs and struct.unpack("<I", subs["NAME"][:4])[0] == MAP_MARKER:
                        markers.append({"ref": r.form_id, "cell": r.parent, "name": _z(subs.get("FULL")),
                                        "pos": list(struct.unpack_from("<3f", subs["DATA"])) if "DATA" in subs else None})
            continue
        if r.sig == "WRLD":
            worlds[r.form_id] = r.editor_id
            continue
        subs = {s.sig: s.data for s in r.subrecords()}
        flags = subs.get("DATA", b"\0")[0]
        grid = struct.unpack_from("<ii", subs["XCLC"]) if "XCLC" in subs else None
        cells[r.form_id] = {"edid": r.editor_id, "name": _z(subs.get("FULL")), "interior": bool(flags & 1),
                            "world": r.parent if not (flags & 1) else None, "grid": list(grid) if grid else None}
    for m in markers:
        c = cells.get(m["cell"], {})
        m["world"] = worlds.get(c.get("world"), "") if c else ""
        m["grid"] = c.get("grid")
    interiors = [{"fid": fid, "edid": c["edid"], "name": c["name"], "refs": refcount.get(fid, 0)}
                 for fid, c in cells.items() if c["interior"] and c["edid"]]
    return {"version": INDEX_VERSION, "interiors": interiors, "markers": [m for m in markers if m["name"]],
            "worlds": sorted(w for w in worlds.values() if w)}


def load_index(esm: Path, cache: Path) -> dict:
    st = esm.stat()
    key = {"size": st.st_size, "mtime": int(st.st_mtime), "version": INDEX_VERSION}
    if cache.is_file():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("key") == key:
                return data
        except ValueError:
            pass
    data = build_index(esm)
    data["key"] = key
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def _cid(fid: int) -> str:
    return f"{fid & 0xFFFFFF:08X}"            # Oblivion.esm is always load-order index 00


def _marker_location(key: str, label: str, m: dict) -> Location:
    if not m.get("world") or not m.get("grid"):
        raise VanillaError(f"map marker {m['name']!r} is not in an exterior cell")
    x, y = m["grid"]
    return Location(key, label, f"cow {m['world']} {x} {y}", _cid(m["ref"]), None, m["world"],
                    f"map marker '{m['name']}' ({_cid(m['ref'])}) in {m['world']} {x},{y}")


def resolve(key_or_spec: str | None, index: dict) -> Location:
    """arena | street | open | <InteriorEditorID> | marker:<name> | cow:<World>:<x>:<y>."""
    spec = (key_or_spec or "arena").strip()
    low = spec.lower()
    aliases = {"combat": "arena", "spells": "arena", "town": "street", "city": "street", "merchant": "street",
               "doors": "street", "exterior": "open", "weather": "open", "projectiles": "open"}
    low = aliases.get(low, low)
    if low.startswith("marker:"):
        return _marker_location("custom", spec, _find_marker(spec.split(":", 1)[1], index))
    if low.startswith("cow:"):
        _, world, x, y = spec.split(":")
        return Location("custom", spec, f"cow {world} {int(x)} {int(y)}", None, None, world, spec)
    if low == "arena":
        d = DEFAULTS["arena"]
        for pat in d["interior_patterns"]:
            hits = [c for c in index["interiors"] if re.search(pat, c["edid"], re.I)]
            if hits:
                best = max(hits, key=lambda c: (c["refs"], c["edid"]))
                return Location("arena", d["label"], f"coc {best['edid']}", None, best["edid"], None,
                                f"interior {best['edid']} ('{best['name']}', {best['refs']} refs)")
        raise VanillaError("no Arena interior found in Oblivion.esm; pass --cell <InteriorEditorID>")
    if low in ("street", "open"):
        d = DEFAULTS[low]
        for name in d["markers"]:
            try:
                return _marker_location(low, d["label"], _find_marker(name, index))
            except VanillaError:
                continue
        raise VanillaError(f"none of the map markers {d['markers']} found; pass --cell marker:<name>")
    hit = next((c for c in index["interiors"] if c["edid"].lower() == low), None)
    if hit:
        return Location("custom", hit["name"] or hit["edid"], f"coc {hit['edid']}", None, hit["edid"], None,
                        f"interior {hit['edid']} ({hit['refs']} refs)")
    raise VanillaError(f"{spec!r} is not an interior EditorID in Oblivion.esm. Use `forge playtest find <text>` "
                       "to search cells and map markers")


def _find_marker(name: str, index: dict) -> dict:
    n = name.strip().lower()
    exact = [m for m in index["markers"] if m["name"].lower() == n]
    if exact:
        return exact[0]
    raise VanillaError(f"no map marker named {name!r}")


def search(text: str, index: dict, limit: int = 30) -> list[str]:
    t = text.lower()
    out = []
    for c in sorted(index["interiors"], key=lambda c: -c["refs"]):
        if t in c["edid"].lower() or t in (c["name"] or "").lower():
            out.append(f"interior  --cell {c['edid']:<32} '{c['name']}'  {c['refs']} refs")
    for m in index["markers"]:
        if t in m["name"].lower():
            out.append(f"marker    --cell \"marker:{m['name']}\"  {m.get('world')} {m.get('grid')}")
    return out[:limit]
