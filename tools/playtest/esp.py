"""Minimal, deterministic TES4 (Oblivion) plugin writer for generated test content.

Writes new records only (no overrides): top-level groups in the vanilla order, interior cells in
their block/sub-block groups with persistent (8) and temporary (9) children. The same input always
gives the same bytes: no timestamps, no dict-order dependence.

Record header: sig, data size, flags, FormID, version-control (4 bytes) = 20 bytes.
Group header : 'GRUP', total size (incl. header), label, type, stamp = 20 bytes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# Top-level group order as Oblivion.esm / the CS write it
GROUP_ORDER = [
    "GMST", "GLOB", "CLAS", "FACT", "HAIR", "EYES", "RACE", "SOUN", "SKIL", "MGEF", "SCPT", "LTEX", "ENCH",
    "SPEL", "BSGN", "ACTI", "APPA", "ARMO", "BOOK", "CLOT", "CONT", "DOOR", "INGR", "LIGH", "MISC", "STAT",
    "GRAS", "TREE", "FLOR", "FURN", "WEAP", "AMMO", "NPC_", "CREA", "LVLC", "SLGM", "KEYM", "ALCH", "SBSP",
    "SGST", "LVLI", "WTHR", "CLMT", "REGN", "CELL", "WRLD", "DIAL", "QUST", "IDLE", "PACK", "CSTY", "LSCR",
    "LVSP", "ANIO", "WATR", "EFSH",
]
FLAG_PERSISTENT = 0x400


def zs(text: str) -> bytes:
    """Zero-terminated cp1252 string (what EDID/FULL/MODL hold)."""
    return text.encode("cp1252") + b"\0"


def sub(sig: str, data: bytes) -> bytes:
    if len(sig) != 4:
        raise ValueError(f"subrecord signature must be 4 chars: {sig!r}")
    if len(data) > 0xFFFF:
        return b"XXXX" + struct.pack("<HI", 4, len(data)) + sig.encode() + struct.pack("<H", 0) + data
    return sig.encode() + struct.pack("<H", len(data)) + data


@dataclass
class Rec:
    sig: str
    fid: int
    subs: list[tuple[str, bytes]] = field(default_factory=list)
    flags: int = 0

    def add(self, sig: str, data: bytes) -> "Rec":
        self.subs.append((sig, data))
        return self

    @property
    def edid(self) -> str:
        for s, d in self.subs:
            if s == "EDID":
                return d.rstrip(b"\0").decode("cp1252")
        return ""

    def to_bytes(self) -> bytes:
        body = b"".join(sub(s, d) for s, d in self.subs)
        return self.sig.encode() + struct.pack("<IIII", len(body), self.flags, self.fid, 0) + body


def grup(label: bytes, gtype: int, content: bytes) -> bytes:
    return b"GRUP" + struct.pack("<I", 20 + len(content)) + label + struct.pack("<iI", gtype, 0) + content


@dataclass
class InteriorCell:
    rec: Rec
    persistent: list[Rec] = field(default_factory=list)
    temporary: list[Rec] = field(default_factory=list)


class PluginWriter:
    """Collects new records and writes a plugin. FormIDs: (len(masters) << 24) | object index."""

    def __init__(self, masters: list[str], author: str = "TES4Forge", desc: str = "", first_object: int = 0x800):
        self.masters = list(masters)
        self.author, self.desc = author, desc
        self.top: dict[str, list[Rec]] = {}
        self.cells: list[InteriorCell] = []
        self._next = first_object
        self.by_edid: dict[str, Rec] = {}

    @property
    def own_index(self) -> int:
        return len(self.masters)

    def new_fid(self) -> int:
        fid = (self.own_index << 24) | self._next
        self._next += 1
        return fid

    def _register(self, r: Rec) -> Rec:
        if r.edid:
            if r.edid.lower() in {k.lower() for k in self.by_edid}:
                raise ValueError(f"duplicate EditorID {r.edid}")
            self.by_edid[r.edid] = r
        return r

    def record(self, sig: str, edid: str | None = None, flags: int = 0) -> Rec:
        if sig not in GROUP_ORDER or sig == "CELL":
            raise ValueError(f"unsupported top-level record type {sig}")
        r = Rec(sig, self.new_fid(), [], flags)
        if edid:
            r.add("EDID", zs(edid))
        self.top.setdefault(sig, []).append(r)
        return self._register(r)

    def cell(self, edid: str) -> InteriorCell:
        r = Rec("CELL", self.new_fid(), [("EDID", zs(edid))])
        c = InteriorCell(r)
        self.cells.append(c)
        self._register(r)
        return c

    def ref(self, cell: InteriorCell, sig: str, edid: str | None = None, persistent: bool = False) -> Rec:
        if sig not in ("REFR", "ACHR", "ACRE", "PGRD"):
            raise ValueError(f"unsupported cell child {sig}")
        r = Rec(sig, self.new_fid(), [], FLAG_PERSISTENT if persistent else 0)
        if edid:
            r.add("EDID", zs(edid))
            self._register(r)
        (cell.persistent if persistent else cell.temporary).append(r)
        return r

    def fid(self, edid: str) -> int:
        return self.by_edid[edid].fid

    def build(self) -> bytes:
        out = bytearray()
        count = 0
        for sig in GROUP_ORDER:
            if sig == "CELL":
                if self.cells:
                    body, n = self._cells()
                    out += grup(b"CELL", 0, body)
                    count += n
                continue
            recs = self.top.get(sig)
            if recs:
                out += grup(sig.encode(), 0, b"".join(r.to_bytes() for r in recs))
                count += len(recs)
        hdr = bytearray()
        hdr += sub("HEDR", struct.pack("<fiI", 1.0, count, self._next))
        hdr += sub("CNAM", zs(self.author))
        if self.desc:
            hdr += sub("SNAM", zs(self.desc[:500]))
        for m in self.masters:
            hdr += sub("MAST", zs(m)) + sub("DATA", b"\0" * 8)
        return b"TES4" + struct.pack("<IIII", len(hdr), 0, 0, 0) + bytes(hdr) + bytes(out)

    def _cells(self) -> tuple[bytes, int]:
        blocks: dict[int, dict[int, list[InteriorCell]]] = {}
        for c in self.cells:
            oid = c.rec.fid & 0xFFFFFF
            blocks.setdefault(oid % 10, {}).setdefault((oid // 10) % 10, []).append(c)
        body = bytearray()
        n = 0
        for b in sorted(blocks):
            bb = bytearray()
            for sb in sorted(blocks[b]):
                sbb = bytearray()
                for c in blocks[b][sb]:
                    sbb += c.rec.to_bytes()
                    n += 1
                    label = struct.pack("<I", c.rec.fid)
                    kids = bytearray()
                    for gtype, lst in ((8, c.persistent), (9, c.temporary)):
                        if lst:
                            kids += grup(label, gtype, b"".join(r.to_bytes() for r in lst))
                            n += len(lst)
                    if kids:
                        sbb += grup(label, 6, bytes(kids))
                bb += grup(struct.pack("<i", sb), 3, bytes(sbb))
            body += grup(struct.pack("<i", b), 2, bytes(bb))
        return bytes(body), n


# ---------------------------------------------------------------- subrecord payload helpers
def pos(x=0.0, y=0.0, z=0.0, rx=0.0, ry=0.0, rz=0.0) -> bytes:
    """REFR/ACHR DATA: position then rotation (radians)."""
    return struct.pack("<6f", x, y, z, rx, ry, rz)


def u8(v: int) -> bytes:
    return struct.pack("<B", v)


def u32(v: int) -> bytes:
    return struct.pack("<I", v)


def f32(v: float) -> bytes:
    return struct.pack("<f", v)
