"""Read global variable values out of an Oblivion save (.ess): the result channel that needs no log.

Run 5: `scof` / `con_SCOF` wrote nothing on the PC. But every console line is compiled as a small
script, so `set ForgeR01 to SomeBeggarRef.GetAV Health` stores a check's value in a global
from ForgeTestCells.esp, and the last batch saves the game. Globals are in every save, so forge
reads them back after the game has exited.

Save layout used (Oblivion .ess, UESP "Oblivion Mod:Save File Format"):
  "TES4SAVEGAME", u8 major, u8 minor, SYSTEMTIME exeTime (16), u32 headerVersion,
  u32 saveHeaderSize, <saveHeaderSize bytes of header: save number, name, level, location, time,
  screenshot>, u8 pluginCount, pluginCount x (u8 len + name), u32 formIdsOffset, u32 recordsNum,
  u32 nextObjectId, u32 worldId, u32 worldX, u32 worldY, u32 pcCell, f32 x, f32 y, f32 z,
  u16 globalsNum, globalsNum x (u32 iref, f32 value), ...
  at formIdsOffset: u32 count, count x u32 FormID (iref = index into this array; FormIDs use the
  save's plugin list as load order).
"""

from __future__ import annotations

import struct
from pathlib import Path

MAGIC = b"TES4SAVEGAME"


class SaveFormatError(ValueError):
    pass


def read_globals(path: Path) -> dict:
    """{'plugins': [...], 'globals': {FormID: value}} from a save."""
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise SaveFormatError(f"{path.name}: not an Oblivion save")
    p = len(MAGIC) + 2 + 16 + 4
    (header_size,) = struct.unpack_from("<I", data, p)
    p += 4 + header_size
    count = data[p]
    p += 1
    plugins = []
    for _ in range(count):
        n = data[p]
        plugins.append(data[p + 1:p + 1 + n].split(b"\0", 1)[0].decode("cp1252", "replace"))
        p += 1 + n
    formids_offset, = struct.unpack_from("<I", data, p)
    p += 4 + 4 + 4 + 4 + 4 + 4 + 4 + 12            # records, nextObjectId, worldId, x, y, cell, xyz
    (nglob,) = struct.unpack_from("<H", data, p)
    p += 2
    pairs = [struct.unpack_from("<If", data, p + 8 * i) for i in range(nglob)]
    if not 0 < formids_offset < len(data):
        raise SaveFormatError(f"{path.name}: FormID table offset {formids_offset} out of range")
    (nfid,) = struct.unpack_from("<I", data, formids_offset)
    if formids_offset + 4 + 4 * nfid > len(data):
        raise SaveFormatError(f"{path.name}: FormID table runs past the end")
    fids = struct.unpack_from(f"<{nfid}I", data, formids_offset + 4)
    out = {}
    for iref, value in pairs:
        if iref < len(fids):
            out[fids[iref]] = value
    return {"plugins": plugins, "globals": out}


def plugin_globals(path: Path, plugin: str, oids: dict[str, int]) -> dict[str, float]:
    """Values of `plugin`'s globals by EditorID ({EDID: object id within the plugin})."""
    info = read_globals(path)
    names = [p.lower() for p in info["plugins"]]
    if plugin.lower() not in names:
        raise SaveFormatError(f"{plugin} is not in the save's plugin list")
    idx = names.index(plugin.lower())
    out = {}
    for edid, oid in oids.items():
        fid = (idx << 24) | (oid & 0xFFFFFF)
        if fid in info["globals"]:
            out[edid] = info["globals"][fid]
    return out


def write_fake(path: Path, plugins: list[str], globals_: dict[int, float]) -> Path:
    """A minimal save in the same layout (for tests and the fake game only)."""
    header = struct.pack("<I", 1) + bytes([5]) + b"Test\0" + struct.pack("<H", 1) + bytes([6]) + b"Arena\0"
    header += struct.pack("<fI", 1.0, 0) + bytes(16) + struct.pack("<III", 8, 0, 0)
    body = bytes([len(plugins)]) + b"".join(bytes([len(n)]) + n.encode("cp1252") for n in plugins)
    fids = list(globals_)
    pre = MAGIC + bytes([0, 125]) + bytes(16) + struct.pack("<II", 1, len(header)) + header + body
    tail = struct.pack("<IIIIIIfff", 0, 0, 0, 0, 0, 0, 0, 0, 0)
    tail += struct.pack("<H", len(fids)) + b"".join(struct.pack("<If", i, globals_[f]) for i, f in enumerate(fids))
    offset = len(pre) + 4 + len(tail)
    blob = pre + struct.pack("<I", offset) + tail + struct.pack("<I", len(fids)) + struct.pack(f"<{len(fids)}I", *fids)
    path.write_bytes(blob)
    return path
