"""Provider for `kind: plugin` (phase 3a): new records from the spec, written as a new plugin.

Spec records look like:

    records:
      - sig: SPEL
        edid: AKSearingBolt
        FULL: Searing Bolt
        SPIT: {Type: Spell, Cost: 40, Level: Apprentice, Flags: []}
        effects:
          - {effect: FIDG, magnitude: 30, area: 5, duration: 1, range: Target}

Keys are subrecord signatures of that record type (order comes from the schema, not the
spec). Strings become zero-terminated strings, mappings become structs (field names from
`forge kb record <SIG>`), lists become repeated subrecords. `effects` expands to
EFID + EFIT (+ SCIT + FULL for script effects).

FormIDs of new records come from an append-only map (`<spec>.ids.json`): an EditorID keeps
its object ID forever, and IDs are never reused, because renumbering breaks saves.
References: `Plugin.esm:00012345`, `Plugin.esm:EditorID`, or a bare EditorID (ours first,
then Oblivion.esm via the KB).
"""

from __future__ import annotations

import json
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
for _p in (str(TOOLS), str(TOOLS / "merge-patch")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from forge import records as R  # noqa: E402
from patchlib import NRec, Writer  # noqa: E402

FIRST_ID = 0x000800
EFFECT_RECORDS = {"SPEL", "ENCH", "ALCH", "INGR", "SGST"}
META_KEYS = {"sig", "edid", "flags", "effects", "comment", "note"}


class PluginError(ValueError):
    pass


@dataclass
class PluginResult:
    data: bytes
    ids: dict
    ids_changed: bool
    records: list[dict] = field(default_factory=list)
    masters: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- FormID map
def load_ids(path: Path, plugin: str) -> dict:
    if path.is_file():
        ids = json.loads(path.read_text(encoding="utf-8"))
        if ids.get("plugin", plugin).lower() != plugin.lower():
            raise PluginError(f"{path.name} belongs to {ids['plugin']}, not {plugin}")
        return ids
    return {"plugin": plugin, "next": f"{FIRST_ID:06X}", "ids": {}, "retired": {}}


def allocate(ids: dict, edids: list[str]) -> bool:
    """Give each new EditorID the next object ID. Existing ones never change."""
    changed = False
    nxt = int(ids["next"], 16)
    for e in edids:
        if e in ids["ids"]:
            continue
        if e in ids.get("retired", {}):
            raise PluginError(f"{e} was retired; IDs are never reused. Pick a new EditorID.")
        ids["ids"][e] = f"{nxt:06X}"
        nxt += 1
        changed = True
    ids["next"] = f"{nxt:06X}"
    return changed


# --------------------------------------------------------------------------- references
class Resolver:
    def __init__(self, plugin: str, ids: dict, kb_db: Path | None = None):
        self.plugin, self.ids, self.kb_db = plugin, ids, kb_db

    def __call__(self, ref: str) -> tuple[str, int]:
        ref = str(ref).strip()
        m = re.fullmatch(r"(.+\.es[mp]):(?:0x)?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})", ref)
        if m:
            return m.group(1).lower(), int(m.group(2), 16) & 0xFFFFFF
        plugin, _, edid = ref.rpartition(":") if ":" in ref else ("", "", ref)
        if (not plugin or plugin.lower() == self.plugin.lower()) and edid in self.ids["ids"]:
            return self.plugin.lower(), int(self.ids["ids"][edid], 16)
        return self._kb(plugin or "Oblivion.esm", edid, ref)

    def _kb(self, plugin: str, edid: str, ref: str) -> tuple[str, int]:
        if not self.kb_db or not Path(self.kb_db).is_file():
            raise PluginError(f"can't resolve {ref!r}: not one of this spec's EditorIDs, and no KB "
                              "(forge-kb.sqlite with the vanilla index) to look it up; use Plugin.esm:FORMID")
        from forge.kb import query as q
        try:
            found = q.form(edid, self.kb_db)
        except q.KBError as e:
            raise PluginError(f"can't resolve {ref!r}: {e}") from None
        rows = [r for r in found if r["plugin"].lower() == plugin.lower() and not r["override"]]
        if len(rows) != 1:
            raise PluginError(f"can't resolve {ref!r}: {len(rows)} matches in {plugin}")
        r = rows[0]
        return r["owner"].lower(), int(r["objid"], 16)


# --------------------------------------------------------------------------- record building
def _slot_order(sig: str) -> dict[str, int]:
    order = {}
    for i, s in enumerate(R.schemas().get(sig, [])):
        order.setdefault(s["sig"], i)
    return order


def _encode_with_refs(rec_sig: str, sub_sig: str, value, resolve, nth: int = 0):
    """-> (data with FormID slots zeroed, ((offset, key), ...)) ready for patchlib's NRec."""
    sch = R.sub_schema(rec_sig, sub_sig, nth)
    if sch is None:
        raise PluginError(f"{rec_sig} has no subrecord {sub_sig} (see `forge kb record {rec_sig}`)")
    keys = []
    if sch["kind"] == "array" and isinstance(value, list):
        fl = R.fixed_layout(sch)
        if not fl:
            raise PluginError(f"{rec_sig}.{sub_sig}: array without a fixed element layout; give it as hex")
        size = sum(f["size"] for f in fl)
        data = bytearray()
        for i, item in enumerate(value):
            el = item if isinstance(item, dict) else {fl[0]["name"]: item}
            el = dict(el)
            for f in fl:
                v = el.get(f["name"])
                if f["formid"] and isinstance(v, str) and not re.fullmatch(r"[0-9A-Fa-f]{8}", v):
                    keys.append((i * size + f["offset"], resolve(v)))
                    el[f["name"]] = 0
            data += R.encode(rec_sig, {"sig": sub_sig, "layout": "array", "items": [el]}, nth)
        return bytes(data), tuple(keys)
    if sch["kind"] == "formid" and isinstance(value, str):
        return b"\0\0\0\0", ((0, resolve(value)),)
    if isinstance(value, dict):
        fields = dict(value)
        for f in R.fixed_layout(sch) or []:
            if f["formid"] and isinstance(fields.get(f["name"]), str) and not re.fullmatch(r"[0-9A-Fa-f]{8}", fields[f["name"]]):
                keys.append((f["offset"], resolve(fields[f["name"]])))
                fields[f["name"]] = 0
        return R.encode(rec_sig, {"sig": sub_sig, "layout": "struct", "fields": fields}, nth), tuple(keys)
    if isinstance(value, (int, float)) and sch["kind"] in ("int", "float"):
        f = (R.fixed_layout(sch) or [{}])[0]
        return R.encode(rec_sig, {"sig": sub_sig, "layout": "struct", "fields": {f.get("name"): value}}, nth), ()
    if isinstance(value, str):
        if sch["kind"] == "string":
            return value.encode("cp1252") + b"\0", ()
        if (R.fixed_layout(sch) or [{}])[0].get("char4"):
            f = R.fixed_layout(sch)[0]
            return R.encode(rec_sig, {"sig": sub_sig, "layout": "struct", "fields": {f["name"]: value}}, nth), ()
    raise PluginError(f"{rec_sig}.{sub_sig}: can't encode {value!r} (kind {sch['kind']})")


def _effects(rec_sig: str, effects: list[dict], resolve) -> list[tuple]:
    out = []
    for i, e in enumerate(effects):
        code = e.get("effect")
        if not isinstance(code, str) or len(code) != 4:
            raise PluginError(f"{rec_sig} effects[{i}]: effect must be a 4-letter MGEF code like FIDG")
        out.append(("EFID", *_encode_with_refs(rec_sig, "EFID", code, resolve)))
        efit = {"Magic Effect Name": code, "Magnitude": e.get("magnitude", 0), "Area": e.get("area", 0),
                "Duration": e.get("duration", 0), "Type": e.get("range", "Self"),
                # xEdit's default (8 = Health); vanilla FIDG spells store 8 too (PC recon)
                "Actor Value": e.get("actor_value", "Health")}
        out.append(("EFIT", *_encode_with_refs(rec_sig, "EFIT", efit, resolve)))
        if e.get("script"):
            sc = e["script"]
            scit = {"Script effect": sc["script"], "Magic school": sc.get("school", "Alteration"),
                    "Visual effect name": sc.get("visual", 0), "Hostile": int(bool(sc.get("hostile", False)))}
            out.append(("SCIT", *_encode_with_refs(rec_sig, "SCIT", scit, resolve)))
            out.append(("FULL", *_encode_with_refs(rec_sig, "FULL", sc.get("name", "Script Effect"), resolve, 1)))
    return out


def build_record(entry: dict, plugin: str, ids: dict, resolve) -> NRec:
    sig = entry.get("sig", "")
    edid = entry.get("edid", "")
    if sig not in R.schemas():
        raise PluginError(f"unknown record type {sig!r}")
    order = _slot_order(sig)
    items = []    # (slot order, sequence, sig, data, keys)
    seq = 0

    def add(sub_sig, data, keys):
        nonlocal seq
        items.append((order.get(sub_sig, 999), seq, sub_sig, data, keys))
        seq += 1

    add("EDID", edid.encode("cp1252") + b"\0", ())
    for k, v in entry.items():
        if k in META_KEYS:
            continue
        if not re.fullmatch(r"[A-Z0-9_]{4}", k):
            raise PluginError(f"{sig} {edid}: {k!r} is not a subrecord signature")
        sch = R.sub_schema(sig, k)
        if sch is not None and sch["kind"] == "array" and isinstance(v, list):
            add(k, *_encode_with_refs(sig, k, v, resolve))          # one subrecord holding the list
            continue
        for one in (v if isinstance(v, list) else [v]):
            add(k, *_encode_with_refs(sig, k, one, resolve))
    if entry.get("effects"):
        if sig not in EFFECT_RECORDS:
            raise PluginError(f"{sig} records don't carry magic effects")
        base = order.get("EFID", 999)
        for sub_sig, data, keys in _effects(sig, entry["effects"], resolve):
            items.append((base, seq, sub_sig, data, keys))
            seq += 1
    items.sort(key=lambda t: (t[0], t[1]))
    rec = NRec.__new__(NRec)
    rec.src, rec.sig = plugin, sig
    rec.flags = _record_flags(entry.get("flags", 0))
    rec.key = (plugin.lower(), int(ids["ids"][edid], 16))
    rec.subs = [(s, d, k) for _, _, s, d, k in items]
    return rec


def _record_flags(v) -> int:
    names = {"Persistent": 0x400, "Quest Item": 0x400, "Initially Disabled": 0x800, "Deleted": 0x20,
             "Visible When Distant": 0x8000, "Dangerous": 0x20000}
    if isinstance(v, int):
        return v
    out = 0
    for n in v or []:
        if n not in names:
            raise PluginError(f"unknown record flag {n!r}; known: {sorted(names)}")
        out |= names[n]
    return out


def build(spec, ids_path: Path, kb_db: Path | None = None) -> PluginResult:
    plugin = spec.output_plugin
    entries = spec.raw.get("records") or []
    if not entries:
        raise PluginError("spec has no records yet (kind: plugin, phase 3a); add records:")
    edids = [e.get("edid", "") for e in entries]
    bad = [e for e in edids if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", e or "")]
    if bad:
        raise PluginError(f"every record needs an EditorID (letters, digits, _): {bad}")
    dup = {e for e in edids if edids.count(e) > 1}
    if dup:
        raise PluginError(f"duplicate EditorIDs: {sorted(dup)}")
    ids = load_ids(ids_path, plugin)
    changed = allocate(ids, edids)
    resolve = Resolver(plugin, ids, kb_db)
    recs = [build_record(e, plugin, ids, resolve) for e in entries]

    masters = list((spec.section("dependencies") or {}).get("masters") or ["Oblivion.esm"])
    w = Writer(plugin, masters + [plugin])
    for m in masters:
        w.used.add(m.lower())          # declared masters stay even if nothing references them
    for r in recs:
        w.add(r)
    data = bytearray(w.build(author=str(spec.section("output").get("author", "Claude for Yuri")),
                             desc=str(spec.raw.get("intent", "")).strip()))
    # HEDR next object ID (offset 34): past every ID we've handed out
    struct.pack_into("<I", data, 34, int(ids["next"], 16))
    summary = [{"sig": r.sig, "edid": e, "objid": ids["ids"][e]} for r, e in zip(recs, edids)]
    return PluginResult(bytes(data), ids, changed, summary, list(w.mast))
