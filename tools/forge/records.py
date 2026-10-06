"""Schema-driven subrecord codec: decode any subrecord to named fields and encode it back.

Layouts come from the KB (kb/data/record_schemas.json, from xEdit) plus layout_overrides.json.
Unused/padding bytes are kept as raw hex when decoding: vanilla records carry CS garbage there
(e.g. cd cd cd), and a round trip must reproduce it byte for byte. New records get zeros.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

DATA = Path(__file__).resolve().parent / "kb" / "data"
PACK = {"itU8": "<B", "itS8": "<b", "itU16": "<H", "itS16": "<h", "itU32": "<I", "itS32": "<i",
        "itU64": "<Q", "itS64": "<q", "float": "<f", "formid": "<I"}


class CodecError(ValueError):
    pass


_SCHEMAS: dict | None = None


def schemas() -> dict:
    """{record sig: [subrecord schema, ...]} with overrides applied."""
    global _SCHEMAS
    if _SCHEMAS is None:
        over = json.loads((DATA / "layout_overrides.json").read_text(encoding="utf-8"))["enums"]
        out = {}
        for r in json.loads((DATA / "record_schemas.json").read_text(encoding="utf-8")):
            for s in r["subrecords"]:
                for f in s["fields"]:
                    o = over.get(f"{s['sig']}.{f['name']}")
                    if o and "enum" not in f:
                        f["enum"] = o["values"]
            out[r["sig"]] = r["subrecords"]
        _SCHEMAS = out
    return _SCHEMAS


def sub_schema(rec_sig: str, sub_sig: str, nth: int = 0) -> dict | None:
    """The schema entry for the nth definition of sub_sig in a record (FULL can appear twice)."""
    hits = [s for s in schemas().get(rec_sig, []) if s["sig"] == sub_sig]
    return hits[min(nth, len(hits) - 1)] if hits else None


def fixed_layout(sch: dict | None) -> list[dict] | None:
    """Fields with known offsets and sizes covering the subrecord, or None."""
    if not sch or not sch["fields"]:
        return None
    fl = sch["fields"]
    if any(f["size"] is None or f["offset"] is None or f["type"] not in PACK and f["type"] != "bytes" for f in fl):
        return None
    return fl


def _field_names(fl):
    """Unique names: repeated 'unused' fields become unused@<offset>."""
    seen, out = {}, []
    for f in fl:
        n = f["name"]
        if n in seen or n == "unused":
            n = f"{n}@{f['offset']}"
        seen[n] = 1
        out.append(n)
    return out


# --------------------------------------------------------------------------- decode
def decode(rec_sig: str, sub_sig: str, data: bytes, nth: int = 0) -> dict:
    """{"sig", "layout": "struct"|"array"|"string"|"raw", "fields"|"items"|"value"|"hex", ["tail"]}."""
    sch = sub_schema(rec_sig, sub_sig, nth)
    if sch and sch["kind"] == "string" and data.endswith(b"\0") and data.count(b"\0") == 1:
        return {"sig": sub_sig, "layout": "string", "value": data[:-1].decode("cp1252")}
    fl = fixed_layout(sch)
    if fl and sch["kind"] == "array":
        size = sum(f["size"] for f in fl)       # xEdit arrays repeat one fixed element to the end
        if size and len(data) % size == 0:
            items = [_decode_fields(fl, data[i:i + size]) for i in range(0, len(data), size)]
            return {"sig": sub_sig, "layout": "array", "items": items}
        return {"sig": sub_sig, "layout": "raw", "hex": data.hex()}
    if not fl or sum(f["size"] for f in fl) > len(data):
        return {"sig": sub_sig, "layout": "raw", "hex": data.hex()}
    used = sum(f["size"] for f in fl)
    out = {"sig": sub_sig, "layout": "struct", "fields": _decode_fields(fl, data[:used])}
    if used < len(data):
        out["tail"] = data[used:].hex()
    return out


def _decode_fields(fl, data: bytes) -> dict:
    fields = {}
    for name, f in zip(_field_names(fl), fl):
        chunk = data[f["offset"]:f["offset"] + f["size"]]
        if f["type"] == "bytes":
            fields[name] = chunk.hex()
            continue
        v = struct.unpack(PACK[f["type"]], chunk)[0]
        if f.get("char4"):
            v = chunk.decode("latin-1") if all(32 <= c < 127 for c in chunk) else v
        elif f.get("enum") and isinstance(v, int) and 0 <= v < len(f["enum"]) and f["enum"][v]:
            v = f["enum"][v]
        elif f.get("flags") and isinstance(v, int):
            names = [f["flags"][i] for i in range(len(f["flags"])) if v >> i & 1 and f["flags"][i]]
            if sum(1 << i for i in range(len(f["flags"])) if f["flags"][i] in names) == v:
                v = names
        elif f["type"] == "formid":
            v = f"{v:08X}"
        fields[name] = v
    return fields


# --------------------------------------------------------------------------- encode
def _value(f: dict, v) -> bytes:
    if f["type"] == "bytes":
        b = bytes.fromhex(v) if isinstance(v, str) else bytes(v or b"")
        return b.ljust(f["size"], b"\0")[:f["size"]]
    if v is None:
        v = 0
    if f.get("char4") and isinstance(v, str):
        if len(v) != 4:
            raise CodecError(f"{f['name']}: 4-character code expected, got {v!r}")
        return v.encode("latin-1")
    if f.get("enum") and isinstance(v, str):
        try:
            v = f["enum"].index(v)
        except ValueError:
            raise CodecError(f"{f['name']}: {v!r} is not one of {f['enum']}") from None
    if f.get("flags") and isinstance(v, (list, tuple)):
        bits = 0
        for n in v:
            if n not in f["flags"]:
                raise CodecError(f"{f['name']}: unknown flag {n!r}; flags are {f['flags']}")
            bits |= 1 << f["flags"].index(n)
        v = bits
    if f["type"] == "formid" and isinstance(v, str):
        v = int(v, 16)
    try:
        return struct.pack(PACK[f["type"]], v)
    except struct.error as e:
        raise CodecError(f"{f['name']}: {v!r} doesn't fit {f['type']} ({e})") from None


def encode(rec_sig: str, d: dict, nth: int = 0) -> bytes:
    """Inverse of decode(). For struct layouts, missing fields default to 0 / zero bytes."""
    sub_sig = d["sig"]
    if d.get("layout") == "string" or "value" in d and d.get("layout") != "struct":
        return str(d["value"]).encode("cp1252") + b"\0"
    if d.get("layout") == "raw" or "hex" in d:
        return bytes.fromhex(d["hex"])
    fl = fixed_layout(sub_schema(rec_sig, sub_sig, nth))
    if not fl:
        raise CodecError(f"{rec_sig}.{sub_sig}: no fixed layout known; give it as hex")
    if d.get("layout") == "array" or "items" in d:
        return b"".join(_encode_fields(rec_sig, sub_sig, fl, item if isinstance(item, dict) else
                                       {_field_names(fl)[0]: item}) for item in d.get("items", []))
    return _encode_fields(rec_sig, sub_sig, fl, dict(d.get("fields", {}))) + bytes.fromhex(d.get("tail", ""))


def _encode_fields(rec_sig: str, sub_sig: str, fl, given: dict) -> bytes:
    names = _field_names(fl)
    unknown = set(given) - set(names) - {n.split("@")[0] for n in names}
    if unknown:
        raise CodecError(f"{rec_sig}.{sub_sig}: unknown field(s) {sorted(unknown)}; fields are {names}")
    out = bytearray()
    for name, f in zip(names, fl):
        out += _value(f, given.get(name))
    return bytes(out)


# --------------------------------------------------------------------------- whole records
def decode_record(rec_sig: str, subs) -> list[dict]:
    """subs: [(sig, data)] -> decoded list, tracking repeated definitions (FULL #2 etc.)."""
    out, count = [], {}
    defs = [s["sig"] for s in schemas().get(rec_sig, [])]
    for sig, data in subs:
        # the nth time a sig appears *as a different schema slot*: SPEL FULL after SCIT is slot 2
        nth = 0
        if defs.count(sig) > 1:
            prev = [d["sig"] for d in out]
            nth = 1 if sig == "FULL" and any(p in ("EFID", "SCIT") for p in prev) else 0
        out.append(dict(decode(rec_sig, sig, data, nth), nth=nth))
        count[sig] = count.get(sig, 0) + 1
    return out


def encode_record(rec_sig: str, decoded: list[dict]) -> list[tuple[str, bytes]]:
    return [(d["sig"], encode(rec_sig, d, d.get("nth", 0))) for d in decoded]


def layout_check(path, sigs: set[str], limit_examples: int = 20) -> dict:
    """Decode and re-encode every subrecord of the given record types; report what round-trips."""
    import tes4_plugin as tp
    res = {"records": 0, "subrecords": 0, "identical": 0, "struct": 0, "array": 0, "raw": 0, "string": 0,
           "with_tail": 0, "mismatch": 0, "examples": []}
    for p, r in tp.iter_records(path, want=sigs):
        res["records"] += 1
        subs = [(s.sig, s.data) for s in r.subrecords()]
        dec = decode_record(r.sig, subs)
        for (sig, data), d in zip(subs, dec):
            res["subrecords"] += 1
            res[d["layout"]] += 1
            if d.get("tail"):
                res["with_tail"] += 1
            try:
                ok = encode(r.sig, d, d["nth"]) == data
            except CodecError as e:
                ok = False
                d["error"] = str(e)
            if ok:
                res["identical"] += 1
            else:
                res["mismatch"] += 1
            if (not ok or d.get("tail")) and len(res["examples"]) < limit_examples:
                res["examples"].append({"record": f"{r.sig} {r.editor_id} {r.form_id:08X}", "sub": sig,
                                        "size": len(data), "decoded": d, "ok": ok})
    return res
