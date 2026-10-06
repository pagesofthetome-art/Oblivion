"""Read-only BSA v103 (Oblivion) archive reader: list, search and extract files.

  python -m assetkit.bsa list  <archive.bsa> [--filter weapons\\]
  python -m assetkit.bsa extract <archive.bsa> <inner\\path.nif> [<more>...] --out <dir>
  python -m assetkit.bsa find <Data dir> <substring>        search every BSA in Data

Never writes to the archive. Extracted files keep their inner path under --out.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

FLAG_DIR_NAMES = 0x1
FLAG_FILE_NAMES = 0x2
FLAG_COMPRESSED = 0x4
SIZE_TOGGLE_COMPRESS = 0x40000000


@dataclass
class BSAEntry:
    path: str          # lower-case, backslash separated, e.g. meshes\weapons\iron\dagger.nif
    size: int
    offset: int
    compressed: bool


class BSA:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: dict[str, BSAEntry] = {}
        with open(self.path, "rb") as f:
            hdr = f.read(36)
            magic, ver, off, aflags, nfold, nfile, lfold, lfile, fflags = struct.unpack("<4s8I", hdr)
            if magic != b"BSA\0" or ver != 103:
                raise ValueError(f"{self.path.name}: not an Oblivion BSA (magic {magic!r}, version {ver})")
            self.flags = aflags
            f.seek(off)
            folders = [struct.unpack("<QII", f.read(16)) for _ in range(nfold)]
            recs: list[tuple[str, int, int]] = []
            for _hash, count, _ofs in folders:
                name = ""
                if aflags & FLAG_DIR_NAMES:
                    ln = f.read(1)[0]
                    name = f.read(ln).rstrip(b"\0").decode("cp1252")
                for _ in range(count):
                    _h, size, fofs = struct.unpack("<QII", f.read(16))
                    recs.append((name, size, fofs))
            names: list[str] = []
            if aflags & FLAG_FILE_NAMES:
                blob = f.read(lfile)
                names = [n.decode("cp1252") for n in blob.split(b"\0")[:nfile]]
        default_comp = bool(aflags & FLAG_COMPRESSED)
        for i, (folder, size, fofs) in enumerate(recs):
            fname = names[i] if i < len(names) else f"file{i:06d}"
            comp = default_comp ^ bool(size & SIZE_TOGGLE_COMPRESS)
            p = (folder + "\\" + fname).lower() if folder else fname.lower()
            self.entries[p] = BSAEntry(p, size & ~SIZE_TOGGLE_COMPRESS & 0x3FFFFFFF, fofs, comp)

    def list(self, contains: str = "") -> list[str]:
        c = contains.lower().replace("/", "\\")
        return sorted(p for p in self.entries if c in p)

    def read(self, inner: str) -> bytes:
        e = self.entries.get(inner.lower().replace("/", "\\"))
        if e is None:
            raise KeyError(f"{inner} not in {self.path.name}")
        with open(self.path, "rb") as f:
            f.seek(e.offset)
            raw = f.read(e.size)
        if e.compressed:
            return zlib.decompress(raw[4:])
        return raw

    def extract(self, inner: str, out_dir: str | Path) -> Path:
        data = self.read(inner)
        dst = Path(out_dir) / Path(*inner.lower().replace("/", "\\").split("\\"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        return dst


def find_in_data(data_dir: str | Path, substring: str) -> list[tuple[str, str]]:
    hits = []
    for b in sorted(Path(data_dir).glob("*.bsa")):
        try:
            for p in BSA(b).list(substring):
                hits.append((b.name, p))
        except (ValueError, OSError):
            continue
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.add_argument("archive"); s.add_argument("--filter", default="")
    s = sub.add_parser("extract"); s.add_argument("archive"); s.add_argument("inner", nargs="+"); s.add_argument("--out", required=True)
    s = sub.add_parser("find"); s.add_argument("data"); s.add_argument("substring")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for p in BSA(a.archive).list(a.filter):
            print(p)
    elif a.cmd == "extract":
        b = BSA(a.archive)
        for inner in a.inner:
            print(b.extract(inner, a.out))
    elif a.cmd == "find":
        for arch, p in find_in_data(a.data, a.substring):
            print(f"{arch}\t{p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
