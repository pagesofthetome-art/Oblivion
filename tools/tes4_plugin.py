"""Read-only parser for Oblivion (TES4) plugin files (.esm / .esp).

Pure standard library (Python 3.10+). Never writes to plugin files.

Binary layout (Oblivion, all little-endian):
  Record header (20 bytes): sig[4] dataSize:u32 flags:u32 formID:u32 vcInfo:u32
  GRUP header  (20 bytes): 'GRUP' groupSize:u32 (includes header) label[4] groupType:i32 stamp:u32
  Subrecord:               sig[4] size:u16 data[size]
                           'XXXX' (size 4) carries a u32 length for the NEXT subrecord,
                           whose own u16 size field is then 0.
  Compressed records (flag 0x00040000): data = decompressedSize:u32 + zlib stream.

FormIDs inside a plugin are file-relative: the top byte is an index into that
plugin's own MAST list; index == len(masters) means "new record from this file".
"""

from __future__ import annotations

import mmap
import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

REC_HDR = struct.Struct("<4sIIII")
GRP_HDR = struct.Struct("<4sI4siI")
SUB_HDR = struct.Struct("<4sH")

# Record flags (Oblivion)
FLAG_ESM = 0x00000001
FLAG_DELETED = 0x00000020
FLAG_CASTS_SHADOWS = 0x00000200
FLAG_PERSISTENT = 0x00000400  # "Quest item" on base forms
FLAG_INITIALLY_DISABLED = 0x00000800
FLAG_IGNORED = 0x00001000
FLAG_VISIBLE_DISTANT = 0x00008000
FLAG_DANGEROUS = 0x00020000
FLAG_COMPRESSED = 0x00040000
FLAG_CANT_WAIT = 0x00080000

GROUP_TYPES = {
    0: "Top",
    1: "World Children",
    2: "Interior Cell Block",
    3: "Interior Cell Sub-Block",
    4: "Exterior Cell Block",
    5: "Exterior Cell Sub-Block",
    6: "Cell Children",
    7: "Topic Children",
    8: "Cell Persistent Children",
    9: "Cell Temporary Children",
    10: "Cell Visible Distant Children",
}

# Human names for the record types an Oblivion modder meets most often.
RECORD_NAMES = {
    "TES4": "File header", "GMST": "Game setting", "GLOB": "Global variable",
    "CLAS": "Class", "FACT": "Faction", "HAIR": "Hair", "EYES": "Eyes", "RACE": "Race",
    "SOUN": "Sound", "SKIL": "Skill", "MGEF": "Magic effect", "SCPT": "Script",
    "LTEX": "Landscape texture", "ENCH": "Enchantment", "SPEL": "Spell", "BSGN": "Birthsign",
    "ACTI": "Activator", "APPA": "Apparatus", "ARMO": "Armor", "BOOK": "Book",
    "CLOT": "Clothing", "CONT": "Container", "DOOR": "Door", "INGR": "Ingredient",
    "LIGH": "Light", "MISC": "Misc item", "STAT": "Static", "GRAS": "Grass", "TREE": "Tree",
    "FLOR": "Flora", "FURN": "Furniture", "WEAP": "Weapon", "AMMO": "Ammo",
    "NPC_": "NPC", "CREA": "Creature", "LVLC": "Leveled creature", "SLGM": "Soul gem",
    "KEYM": "Key", "ALCH": "Potion", "SBSP": "Subspace", "SGST": "Sigil stone",
    "LVLI": "Leveled item", "WTHR": "Weather", "CLMT": "Climate", "REGN": "Region",
    "CELL": "Cell", "REFR": "Placed object", "ACHR": "Placed NPC", "ACRE": "Placed creature",
    "PGRD": "Path grid", "WRLD": "Worldspace", "LAND": "Landscape", "ROAD": "Road",
    "DIAL": "Dialogue topic", "INFO": "Dialogue response", "QUST": "Quest",
    "IDLE": "Idle animation", "PACK": "AI package", "CSTY": "Combat style",
    "LSCR": "Load screen", "LVSP": "Leveled spell", "ANIO": "Animated object",
    "WATR": "Water", "EFSH": "Effect shader",
}

PLACED_TYPES = {"REFR", "ACHR", "ACRE"}
LEVELED_TYPES = {"LVLI", "LVLC", "LVSP"}


@dataclass
class Subrecord:
    sig: str
    data: bytes


@dataclass
class Record:
    sig: str
    flags: int
    form_id: int          # raw, file-relative FormID as stored
    vc_info: int
    offset: int           # file offset of the record header
    raw: bytes            # raw (possibly compressed) data bytes
    parent: int | None = None   # file-relative FormID of the owning CELL / WRLD / DIAL, if any
    group_path: tuple = ()

    @property
    def is_compressed(self) -> bool:
        return bool(self.flags & FLAG_COMPRESSED)

    @property
    def is_deleted(self) -> bool:
        return bool(self.flags & FLAG_DELETED)

    @property
    def data(self) -> bytes:
        if not self.is_compressed:
            return self.raw
        if len(self.raw) < 4:
            raise ValueError(f"{self.sig} {self.form_id:08X}: truncated compressed record")
        return zlib.decompress(self.raw[4:])

    def subrecords(self) -> list[Subrecord]:
        return parse_subrecords(self.data)

    def first(self, sig: str) -> bytes | None:
        for s in self.subrecords():
            if s.sig == sig:
                return s.data
        return None

    @property
    def editor_id(self) -> str:
        d = self.first("EDID")
        return zstring(d) if d else ""

    @property
    def full_name(self) -> str:
        d = self.first("FULL")
        return zstring(d) if d else ""


def zstring(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("cp1252", "replace")


def parse_subrecords(data: bytes) -> list[Subrecord]:
    out: list[Subrecord] = []
    pos, n, big = 0, len(data), None
    while pos + 6 <= n:
        sig_b, size = SUB_HDR.unpack_from(data, pos)
        pos += 6
        if big is not None:
            size, big = big, None
        sig = sig_b.decode("latin-1")
        if sig == "XXXX":
            big = struct.unpack_from("<I", data, pos)[0]
            pos += size
            continue
        out.append(Subrecord(sig, data[pos:pos + size]))
        pos += size
    return out


@dataclass
class Plugin:
    path: Path
    is_esm_flag: bool
    version: float
    num_records: int
    next_object_id: int
    author: str
    description: str
    masters: list[str]
    records: list[Record] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    # ---- FormID helpers -------------------------------------------------
    def owner_of(self, form_id: int) -> str | None:
        """Filename that defines this file-relative FormID (None if index is invalid)."""
        idx = form_id >> 24
        if idx < len(self.masters):
            return self.masters[idx]
        if idx == len(self.masters):
            return self.name
        return None

    def global_key(self, form_id: int) -> tuple[str, int] | None:
        """Load-order-independent identity: (defining file lower-case, 24-bit object id)."""
        owner = self.owner_of(form_id)
        if owner is None:
            return None
        return owner.casefold(), form_id & 0x00FFFFFF

    def is_override(self, rec: Record) -> bool:
        return (rec.form_id >> 24) < len(self.masters)


def _read_header(buf, path: Path) -> tuple[Plugin, int]:
    sig, size, flags, fid, vc = REC_HDR.unpack_from(buf, 0)
    if sig != b"TES4":
        raise ValueError(f"{path.name}: not an Oblivion plugin (first record is {sig!r}, expected TES4)")
    data = bytes(buf[20:20 + size])
    if flags & FLAG_COMPRESSED:
        data = zlib.decompress(data[4:])
    version, num_records, next_id = 0.0, 0, 0
    author = desc = ""
    masters: list[str] = []
    for s in parse_subrecords(data):
        if s.sig == "HEDR" and len(s.data) >= 12:
            version, num_records, next_id = struct.unpack_from("<fiI", s.data, 0)
        elif s.sig == "CNAM":
            author = zstring(s.data)
        elif s.sig == "SNAM":
            desc = zstring(s.data)
        elif s.sig == "MAST":
            masters.append(zstring(s.data))
    p = Plugin(path, bool(flags & FLAG_ESM), round(version, 2), num_records, next_id, author, desc, masters)
    return p, 20 + size


def read_header(path: str | os.PathLike) -> Plugin:
    path = Path(path)
    with open(path, "rb") as fh:
        head = fh.read(65536)
    p, _ = _read_header(head, path)
    return p


def iter_records(path: str | os.PathLike, want: set[str] | None = None,
                 want_ids: set[int] | None = None) -> Iterator[tuple[Plugin, Record]]:
    """Stream records. `want` filters signatures, `want_ids` filters file-relative FormIDs.

    GRUPs are walked recursively so CELL/WRLD/DIAL children get a `parent`.
    Filtering skips copying record bytes, so scanning a 270 MB Oblivion.esm for a
    few hundred FormIDs is fast enough on a normal PC.
    """
    path = Path(path)
    with open(path, "rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        if size < 20:
            raise ValueError(f"{path.name}: file too small")
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            plugin, pos = _read_header(mm, path)
            yield from _walk(mm, pos, size, plugin, want, want_ids, None, ())
        finally:
            mm.close()


def _walk(mm, pos, end, plugin, want, want_ids, parent, gpath):
    last_container: int | None = parent
    while pos + 20 <= end:
        sig_b = mm[pos:pos + 4]
        if sig_b == b"GRUP":
            _, gsize, label, gtype, _stamp = GRP_HDR.unpack_from(mm, pos)
            if gsize < 20 or pos + gsize > end:
                plugin.errors.append(f"Corrupt GRUP at offset {pos:#x} (size {gsize})")
                return
            if gtype in (1, 6, 7, 8, 9, 10):
                child_parent = struct.unpack("<I", label)[0]
            else:
                child_parent = parent
            glabel = label.decode("latin-1") if gtype == 0 else f"{GROUP_TYPES.get(gtype, gtype)}"
            yield from _walk(mm, pos + 20, pos + gsize, plugin, want, want_ids,
                             child_parent, gpath + (glabel,))
            pos += gsize
            continue
        sig_b, dsize, flags, fid, vc = REC_HDR.unpack_from(mm, pos)
        if pos + 20 + dsize > end:
            plugin.errors.append(f"Record {sig_b!r} {fid:08X} at {pos:#x} overruns its group")
            return
        sig = sig_b.decode("latin-1")
        if (want is None or sig in want) and (want_ids is None or fid in want_ids):
            yield plugin, Record(sig, flags, fid, vc, pos, bytes(mm[pos + 20:pos + 20 + dsize]),
                                 parent, gpath)
        pos += 20 + dsize


def load(path: str | os.PathLike, want: set[str] | None = None) -> Plugin:
    plugin = None
    recs = []
    for plugin, rec in iter_records(path, want):
        recs.append(rec)
    if plugin is None:
        plugin = read_header(path)
    plugin.records = recs
    return plugin


def fmt_fid(fid: int) -> str:
    return f"{fid:08X}"
