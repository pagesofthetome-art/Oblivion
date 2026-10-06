"""Stand-in plugin builders for playtest examples, until Track B builds `kind: plugin` specs."""

from __future__ import annotations

import struct
from pathlib import Path

from playtest.esp import PluginWriter, zs


def firebolt(out: Path) -> Path:
    """ForgeExampleFirebolt.esp: one spell, 'Forge Firebolt' (Fire Damage 25 pts on target)."""
    w = PluginWriter(["Oblivion.esm"], author="TES4Forge playtest example",
                     desc="Example fire-bolt spell for forge playtest. Test only.")
    r = w.record("SPEL", "ForgeExampleFireboltSpell")
    r.add("FULL", zs("Forge Firebolt"))
    r.add("SPIT", struct.pack("<IIIB3x", 0, 18, 0, 0))            # spell, cost 18, novice, no flags
    r.add("EFID", b"FIDG")
    r.add("EFIT", struct.pack("<4sIIIIi", b"FIDG", 25, 0, 0, 2, -1))   # 25 pts, no area, instant, target
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(w.build())
    return out


BUILDERS = {"firebolt": firebolt}
