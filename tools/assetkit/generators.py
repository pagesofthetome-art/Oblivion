"""Parametric asset generators. Each returns (Mesh, atlas) where atlas maps part name -> UV rect.

Add new generators here and register them in GENERATORS. A generator must:
  * follow the axis conventions in mesh.py (weapons: grip at origin, blade along +Y),
  * give every part its own atlas rectangle so materials can be painted per part,
  * keep triangle counts in vanilla budgets (dagger ~300-800, sword ~500-1500, clutter ~100-800).

Vanilla size references (measured from Knights.bsa meshes, grip at y=0):
  longsword (ndlongsword)  y -13..+67.5, guard width 18, 1370 tris
  shortsword (ndshortsword) y -11..+41,  guard width 10.5, 870 tris
  mace (ndmace)            y -18..+38.5, head width 9.7,   1021 tris
"""

from __future__ import annotations

import numpy as np

from . import mesh as M

# Atlas layout shared by bladed weapons: blade gets the left half, fittings the right half.
BLADE_ATLAS = {
    "blade": (0.0, 0.0, 0.5, 1.0),
    "guard": (0.5, 0.0, 1.0, 0.25),
    "grip": (0.5, 0.25, 1.0, 0.75),
    "pommel": (0.5, 0.75, 1.0, 1.0),
}


def _planar_uv(m: M.Mesh, axes=(0, 1)) -> M.Mesh:
    lo, hi = m.v.min(0), m.v.max(0)
    span = np.where(hi - lo == 0, 1, hi - lo)
    u = (m.v[:, axes[0]] - lo[axes[0]]) / span[axes[0]]
    v = 1 - (m.v[:, axes[1]] - lo[axes[1]]) / span[axes[1]]
    m.uv = np.column_stack([u, v]); return m


def blade_sections(length, width, thickness, tip_length, taper=0.25, fuller=0.0, steps=10, curve=0.0):
    """Cross-sections for a straight (or slightly curved) double-edged blade from y=0 to y=length.

    Section = hexagon-ish diamond: edge points at +-x, spine points at +-z. `fuller` (0..0.8)
    flattens the centre into a groove-like plateau (6-point section).
    """
    secs = []
    body = length - tip_length
    ys = list(np.linspace(0, body, max(2, steps - 3))) + list(np.linspace(body, length, 4)[1:])
    for y in ys:
        if y <= body:
            k = 1 - taper * (y / max(body, 1e-6))
        else:
            t = (y - body) / max(tip_length, 1e-6)
            k = (1 - taper) * (1 - t) ** 1.15
        w = max(width / 2 * k, 0.02); th = max(thickness / 2 * max(k, 0.25 if y < length else 0.05), 0.02)
        xoff = curve * (y / length) ** 2 * length
        if fuller > 0:
            f = w * fuller
            pts = [(w, 0), (f, th), (-f, th), (-w, 0), (-f, -th), (f, -th)]
        else:
            pts = [(w, 0), (0, th), (-w, 0), (0, -th)]
        secs.append(np.array([(x + xoff, y, z) for x, z in pts]))
    return secs


def blade_weapon(blade_length=40.0, blade_width=4.4, blade_thickness=0.8, tip_length=7.0, taper=0.3,
                 fuller=0.0, curve=0.0, guard_width=10.0, guard_height=1.4, guard_depth=2.0,
                 guard_style="bar", grip_length=9.0, grip_radius=0.95, pommel_radius=1.5,
                 pommel_style="disc", segments=12, **_):
    """Daggers, short/long swords, sabres. Hand at the origin; guard above, pommel below."""
    gl = grip_length
    # blade
    secs = blade_sections(blade_length, blade_width, blade_thickness, tip_length, taper, fuller, 12, curve)
    blade = M.loft([s + np.array([0, gl / 2 + guard_height, 0]) for s in secs], "blade")
    blade = _planar_uv(blade, (0, 1))
    # guard
    if guard_style == "bar":
        guard = M.box(guard_width, guard_height, guard_depth, "guard").translate(0, gl / 2 + guard_height / 2, 0)
    elif guard_style == "curved":
        rings = []
        for x in np.linspace(-guard_width / 2, guard_width / 2, 9):
            yy = gl / 2 + guard_height / 2 + 0.06 * (x ** 2) / max(guard_width / 10, 1)
            sc = 1 - 0.4 * abs(x) / (guard_width / 2)
            rings.append(np.array([(x, yy + dy * sc, dz * sc) for dy, dz in
                                   [(guard_height / 2, 0), (0, guard_depth / 2), (-guard_height / 2, 0), (0, -guard_depth / 2)]]))
        guard = M.loft(rings, "guard"); guard = _planar_uv(guard, (0, 1))
    else:
        raise ValueError("guard_style must be 'bar' or 'curved'")
    # grip (slight swell in the middle)
    prof = [(grip_radius * s, gl / 2 - gl * t) for t, s in [(0, 0.92), (0.15, 1.0), (0.5, 1.06), (0.85, 1.0), (1, 0.92)]]
    grip = M.lathe(prof, segments, "y", "grip")
    # pommel
    pr = pommel_radius
    if pommel_style == "disc":
        pprof = [(0.6 * grip_radius, -gl / 2), (pr, -gl / 2 - 0.4 * pr), (pr, -gl / 2 - 0.9 * pr),
                 (0.5 * pr, -gl / 2 - 1.3 * pr), (0.001, -gl / 2 - 1.4 * pr)]
    elif pommel_style == "ball":
        pprof = [(0.6 * grip_radius, -gl / 2)] + [(pr * np.sin(a), -gl / 2 - pr + pr * np.cos(a) - 0.2)
                                                  for a in np.linspace(0.35, np.pi - 0.01, 7)]
    else:
        raise ValueError("pommel_style must be 'disc' or 'ball'")
    pommel = M.lathe(pprof, segments, "y", "pommel", cap_end=False)
    parts = {"blade": blade, "guard": guard, "grip": grip, "pommel": pommel}
    for k, p in parts.items():
        p.atlas_rect(*BLADE_ATLAS[k])
    m = M.merge(*parts.values())
    m.names = list(parts.keys())
    return m.split_sharp(35), dict(BLADE_ATLAS)


def column(height=96.0, radius=8.0, segments=16, base_height=8.0, **_):
    """Simple static column (clutter/architecture test generator). Z up, origin at base centre."""
    prof = [(radius * 1.35, 0), (radius * 1.35, base_height * 0.5), (radius * 1.1, base_height),
            (radius, base_height * 1.2), (radius * 0.92, height - base_height * 1.2), (radius * 1.1, height - base_height),
            (radius * 1.35, height - base_height * 0.5), (radius * 1.35, height)]
    m = M.lathe(prof, segments, "z", "shaft")
    m.atlas_rect(0, 0, 1, 1)
    m.names = ["shaft"]
    return m.split_sharp(50), {"shaft": (0, 0, 1, 1)}


GENERATORS = {"blade_weapon": blade_weapon, "column": column}
