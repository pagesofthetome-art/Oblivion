"""Real Oblivion test locations: pick vanilla cells from the test game's own Oblivion.esm.

Yuri's rule: a playtest is the real game. Test locations are therefore existing vanilla cells,
reached the way a modder would: `coc <InteriorEditorID>`, or `cow <World> X Y` followed by
`player.moveto <map marker>` for an exterior spot. The test actors (dummy, caster, merchant,
townsfolk) live in ForgeTestCells.esp's empty holding cell and are moved next to the player.

Oblivion.esm is only read. The index (interior cells with their reference counts, worldspaces,
and named map markers with their cell and grid) is cached in forge-builds\\playtest\\vanilla-index.json,
keyed by the file's size and modification time.

Default picks (each can be overridden: `--cell <InteriorEditorID>`, `--cell marker:<Map marker name>`,
`--cell world:<Worldspace>` or `--cell cow:<World>:<x>:<y>`):
  arena   the Imperial City Arena's combat floor: interior ICArena, arriving through the
          Bloodworks gate (fallbacks: name 'Imperial City Arena', then an ICArena* EditorID)
  street  the Market District worldspace: the busiest cell, standing where a shop door lets you out
  open    the Weye map marker (open shore road west of the Imperial City)

The player stands on a door arrival spot (a load door's XTEL destination: always walkable floor)
when the location has one.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

MAP_MARKER = 0x00000010
DEFAULTS = {
    "arena": {"label": "Imperial City Arena, combat floor",
              # the fighting pit (verified on Yuri's Oblivion.esm, run 3): EditorID ICArena, name
              # 'Imperial City Arena'; the player arrives through the Bloodworks gate, as for a match
              "edid": "ICArena", "arrive_from": r"bloodworks",
              "name": "Imperial City Arena",
              "exclude": r"spectator|champion|holding|bloodwork|quarter|storage|hall|tunnel|basement|"
                         r"store|shop|room|gate|lobby|bet|test|sewer"},
    "street": {"label": "Imperial City street",
               "worlds": ["ICMarketDistrict", "ICTalosPlazaDistrict", "ICElvenGardensDistrict",
                          "ICArenaDistrict", "ICTempleDistrict"]},
    "open": {"markers": ["Weye", "Pell's Gate", "Aleswell"], "label": "open countryside"},
}
INDEX_VERSION = 3


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
    setpos: list | None = None     # [x, y, z, heading radians]: a door arrival spot to stand on

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _z(b: bytes | None) -> str:
    return b.split(b"\0", 1)[0].decode("cp1252", "replace") if b else ""


def build_index(esm: Path) -> dict:
    """One pass over Oblivion.esm: interiors, worldspaces, map markers, and door arrival spots.

    A door arrival spot is the XTEL destination of a load door: where the game puts the player
    after walking through it. It is always walkable floor, so it is where tests stand the player.
    """
    import tes4_plugin as tp
    cells: dict[int, dict] = {}
    worlds: dict[int, str] = {}
    markers: list[dict] = []
    doors: list[dict] = []
    ref_cell: dict[int, int] = {}
    refcount: dict[int, int] = {}
    for _, r in tp.iter_records(esm, {"CELL", "WRLD", "REFR", "ACHR"}):
        if r.sig in ("REFR", "ACHR"):
            refcount[r.parent] = refcount.get(r.parent, 0) + 1
            if r.sig == "REFR":
                d = r.data
                if b"XMRK" in d or b"XTEL" in d:
                    subs = {s.sig: s.data for s in r.subrecords()}
                    base = struct.unpack("<I", subs["NAME"][:4])[0] if "NAME" in subs else None
                    if "XTEL" in subs and len(subs["XTEL"]) >= 28:
                        dest, x, y, z, rx, ry, rz = struct.unpack_from("<I6f", subs["XTEL"])
                        doors.append({"ref": r.form_id, "dest": dest, "pos": [x, y, z], "rot": rz})
                        ref_cell[r.form_id] = r.parent
                    if base == MAP_MARKER:
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

    def where(cell_fid: int, pos) -> dict:
        c = cells.get(cell_fid, {})
        if c.get("interior"):
            return {"interior": c["edid"], "world": None, "grid": None}
        grid = [int(pos[0] // 4096), int(pos[1] // 4096)] if pos else c.get("grid")
        return {"interior": None, "world": worlds.get(c.get("world"), ""), "grid": grid}

    for m in markers:
        m.update(where(m["cell"], m["pos"]))
    spots = []
    for d in doors:                                   # the spot is in the cell of the destination door
        cell = ref_cell.get(d["dest"])
        if cell is None:
            continue
        w = where(cell, d["pos"])
        frm = cells.get(ref_cell.get(d["ref"]), {})
        spots.append({"door": d["dest"], "cell": cell, "pos": [round(v, 1) for v in d["pos"]],
                      "rot": round(d["rot"], 4), "cell_refs": refcount.get(cell, 0),
                      "from": frm.get("edid") or worlds.get(frm.get("world"), ""), **w})
    interiors = [{"fid": fid, "edid": c["edid"], "name": c["name"], "refs": refcount.get(fid, 0)}
                 for fid, c in cells.items() if c["interior"] and c["edid"]]
    ext_refs: dict[tuple, int] = {}
    for fid, c in cells.items():
        if not c["interior"] and c.get("grid") is not None:
            key = (worlds.get(c["world"], ""), tuple(c["grid"]))
            ext_refs[key] = refcount.get(fid, 0)
    for sp in spots:
        if sp["world"]:
            sp["cell_refs"] = ext_refs.get((sp["world"], tuple(sp["grid"])), sp["cell_refs"])
    return {"version": INDEX_VERSION, "interiors": interiors, "markers": [m for m in markers if m["name"]],
            "spots": spots, "worlds": sorted(w for w in worlds.values() if w)}


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
    if m.get("interior"):
        return Location(key, label, f"coc {m['interior']}", _cid(m["ref"]), m["interior"], None,
                        f"map marker '{m['name']}' ({_cid(m['ref'])}) in {m['interior']}")
    if not m.get("world") or not m.get("grid"):
        raise VanillaError(f"map marker {m['name']!r} is not in an exterior cell")
    x, y = m["grid"]
    return Location(key, label, f"cow {m['world']} {x} {y}", _cid(m["ref"]), None, m["world"],
                    f"map marker '{m['name']}' ({_cid(m['ref'])}) in {m['world']} {x},{y}")


def _spots(index: dict, interior: str | None = None, world: str | None = None) -> list[dict]:
    out = [sp for sp in index.get("spots", [])
           if (interior and (sp.get("interior") or "").lower() == interior.lower())
           or (world and (sp.get("world") or "").lower() == world.lower())]
    return sorted(out, key=lambda sp: (-sp["cell_refs"], sp["door"]))


def _interior_location(key: str, label: str, c: dict, index: dict, arrive_from: str | None = None) -> Location:
    spots = _spots(index, interior=c["edid"])
    if arrive_from:
        preferred = [sp for sp in spots if re.search(arrive_from, sp.get("from") or "", re.I)]
        spots = preferred + [sp for sp in spots if sp not in preferred]
    sp = spots[0] if spots else None
    return Location(key, label, f"coc {c['edid']}", None, c["edid"], None,
                    f"interior {c['edid']} ('{c['name']}', {c['refs']} refs)"
                    + (f", arriving from {sp.get('from') or '?'} (door {_cid(sp['door'])})" if sp else ""),
                    [*sp["pos"], sp["rot"]] if sp else None)


def _world_location(key: str, label: str, world: str, index: dict) -> Location:
    spots = _spots(index, world=world)
    if not spots:
        raise VanillaError(f"no door arrival spots in worldspace {world}")
    sp = spots[0]
    gx, gy = sp["grid"]
    return Location(key, label, f"cow {sp['world']} {gx} {gy}", None, None, sp["world"],
                    f"{sp['world']} {gx},{gy} ({sp['cell_refs']} refs), outside door {_cid(sp['door'])}",
                    [*sp["pos"], sp["rot"]])


def resolve(key_or_spec: str | None, index: dict) -> Location:
    """arena | street | open | <InteriorEditorID> | marker:<name> | world:<World> | cow:<World>:<x>:<y>."""
    spec = (key_or_spec or "arena").strip()
    low = spec.lower()
    aliases = {"combat": "arena", "spells": "arena", "town": "street", "city": "street", "merchant": "street",
               "doors": "street", "exterior": "open", "weather": "open", "projectiles": "open"}
    low = aliases.get(low, low)
    if low.startswith("marker:"):
        return _marker_location("custom", spec, _find_marker(spec.split(":", 1)[1], index))
    if low.startswith("world:"):
        return _world_location("custom", spec, spec.split(":", 1)[1], index)
    if low.startswith("cow:"):
        _, world, x, y = spec.split(":")
        return Location("custom", spec, f"cow {world} {int(x)} {int(y)}", None, None, world, spec)
    if low == "arena":
        d = DEFAULTS["arena"]
        best = next((c for c in index["interiors"] if c["edid"].lower() == d["edid"].lower()), None)
        if best is None:                                  # not the vanilla esm layout: name, then heuristic
            named = [c for c in index["interiors"] if (c["name"] or "").strip().lower() == d["name"].lower()
                     and not re.search(d["exclude"], c["edid"], re.I)]
            # never "anything with Arena in the name": that picked the ruin 'Cann, Arena' in run 3
            hits = named or [c for c in index["interiors"] if c["edid"].lower().startswith("icarena")
                             and not re.search(d["exclude"], c["edid"], re.I)]
            if not hits:
                raise VanillaError("no Arena interior found in Oblivion.esm; pass --cell <InteriorEditorID> "
                                   "(forge playtest find arena)")
            best = max(hits, key=lambda c: (c["refs"], c["edid"]))
        return _interior_location("arena", d["label"], best, index, d["arrive_from"])
    if low == "street":
        d = DEFAULTS["street"]
        for world in d["worlds"]:
            try:
                return _world_location("street", d["label"], world, index)
            except VanillaError:
                continue
        raise VanillaError(f"none of the worldspaces {d['worlds']} has door spots; pass --cell world:<World>")
    if low == "open":
        d = DEFAULTS["open"]
        for name in d["markers"]:
            try:
                return _marker_location("open", d["label"], _find_marker(name, index))
            except VanillaError:
                continue
        raise VanillaError(f"none of the map markers {d['markers']} found; pass --cell marker:<name>")
    hit = next((c for c in index["interiors"] if c["edid"].lower() == low), None)
    if hit:
        return _interior_location("custom", hit["name"] or hit["edid"], hit, index)
    raise VanillaError(f"{spec!r} is not an interior EditorID in Oblivion.esm. Use `forge playtest find <text>` "
                       "to search cells, worldspaces and map markers")


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
            out.append(f"marker    --cell \"marker:{m['name']}\"  {m.get('world') or m.get('interior')} {m.get('grid')}")
    for w in index.get("worlds", []):
        if t in w.lower():
            n = len(_spots(index, world=w))
            out.append(f"world     --cell world:{w:<26} {n} door arrival spots")
    return out[:limit]
