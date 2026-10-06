"""Turn assetkit Meshes into Oblivion-ready NIFs (and read NIF geometry back into Meshes).

Profiles (values copied from vanilla meshes):
  weapon  : BSXFlags 0x3, Prn extra data (SideWeapon / BackWeapon / ...), Havok layer 5 (WEAPON),
            motion 4, quality 3, mass from recipe, NiTriShape along +Y, grip at origin
  clutter : BSXFlags 0x3, layer 4 (CLUTTER), motion 4, quality 3, dynamic havok object you can pick up/knock
  static  : BSXFlags 0x2, layer 1 (STATIC), motion 7 (fixed), quality 1, mass 0
Collision: bhkConvexVerticesShape (convex hull, Havok units = game units / 7). The hull uses
scipy when available, otherwise the axis-aligned bounding box.
"""

from __future__ import annotations

import numpy as np

from . import nif as N
from .mesh import Mesh

HAVOK_SCALE = 7.0
HAVOK_MATERIALS = {"stone": 0, "cloth": 1, "dirt": 2, "glass": 3, "grass": 4, "metal": 5, "organic": 6,
                   "skin": 7, "water": 8, "wood": 9, "heavy_stone": 10, "heavy_metal": 11, "heavy_wood": 12,
                   "chain": 13, "snow": 14}
PROFILES = {
    "weapon": dict(bsx=0x3, layer=5, motion=4, deact=2, solver=2, quality=3, dynamic=True),
    "clutter": dict(bsx=0x3, layer=4, motion=4, deact=2, solver=2, quality=3, dynamic=True),
    "static": dict(bsx=0x2, layer=1, motion=7, deact=1, solver=1, quality=1, dynamic=False),
}
UPB = ("Collision_Groups = 0\r\nMass = {mass:.6f}\r\nEllasticity = 0.300000\r\nFriction = 0.300000\r\n"
       "Unyielding = 0\r\nSimulation_Geometry = 2\r\nProxy_Geometry = <None>\r\nUse_Display_Proxy = 0\r\n"
       "Display_Children = 1\r\nDisable_Collisions = 0\r\nInactive = 0\r\nDisplay_Proxy = <None>\r\n")
IDENT = [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0]


def _hull(points: np.ndarray):
    """Return (vertices, planes) of the convex hull; planes are (nx, ny, nz, -d) outward."""
    try:
        from scipy.spatial import ConvexHull
        h = ConvexHull(points)
        verts = points[h.vertices]
        eq = np.unique(np.round(h.equations, 5), axis=0)       # merge coplanar facets
        return verts, eq
    except Exception:
        lo, hi = points.min(0), points.max(0)
        verts = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        eq = np.array([[-1, 0, 0, lo[0]], [1, 0, 0, -hi[0]], [0, -1, 0, lo[1]], [0, 1, 0, -hi[1]],
                       [0, 0, -1, lo[2]], [0, 0, 1, -hi[2]]], float)
        return verts, eq


def _box_inertia(mass, size):
    x, y, z = size
    return [mass / 12 * (y * y + z * z), 0, 0, 0, 0, mass / 12 * (x * x + z * z), 0, 0, 0, 0,
            mass / 12 * (x * x + y * y), 0]


def build(mesh: Mesh, texture_path: str, name: str = "Asset", profile: str = "weapon",
          prn: str | None = "SideWeapon", mass: float = 5.0, havok_material: str = "metal",
          collision: Mesh | None = None, glossiness: float = 50.0, specular=(0.9, 0.9, 0.9)) -> N.Nif:
    """texture_path is relative to Data, e.g. 'textures\\\\MyMod\\\\dagger.dds' (vanilla stores 'textures\\\\...')."""
    p = PROFILES[profile]
    if profile == "static":
        mass = 0.0
    m = mesh
    normals = m.vertex_normals()
    tan, bit = m.tangents(normals)
    nif = N.Nif(export_info=("assetkit", "assetkit build", "assetkit"))
    root = nif.add("NiNode", name=name, extra_data=[], controller=-1, flags=14, translation=[0.0, 0.0, 0.0],
                   rotation=IDENT, scale=1.0, properties=[], collision=-1, children=[], effects=[])
    bsx = nif.add("BSXFlags", name="BSX", integer=p["bsx"])
    extras = [bsx]
    if prn:
        extras.append(nif.add("NiStringExtraData", name="Prn", string=prn))
    extras.append(nif.add("NiStringExtraData", name="UPB", string=UPB.format(mass=0.0)))
    nif.blocks[root]["extra_data"] = extras

    # collision
    pts = (collision.v if collision is not None else m.v) / HAVOK_SCALE
    hv, planes = _hull(pts)
    shape = nif.add("bhkConvexVerticesShape", material=HAVOK_MATERIALS[havok_material], radius=0.1,
                    vertices_property=bytes(12), normals_property=bytes(12),
                    cv_vertices=[[*map(float, v), 0.0] for v in hv], cv_normals=[[*map(float, q)] for q in planes])
    lo, hi = pts.min(0), pts.max(0)
    center = (lo + hi) / 2
    body = nif.add("bhkRigidBody", shape=shape, layer=p["layer"], filter_flags=0, group=0,
                   world_unused1=bytes(4), broadphase=1, world_unused2=bytes(3),
                   cinfo_property=bytes(11) + b"\x80",
                   collision_response=1, entity_unused=0, contact_callback_delay=0xFFFF,
                   rb_unknown_int=bytes(4), rb_layer=p["layer"], rb_filter_flags=0, rb_group=0,
                   rb_unused2=bytes(4), rb_collision_response=1, rb_unused3=0, rb_callback_delay=0xFFFF,
                   rb_unknown=bytes(4), rb_translation=[0.0, 0.0, 0.0, 0.0], rb_rotation=[0.0, 0.0, 0.0, 1.0],
                   linear_velocity=[0.0] * 4, angular_velocity=[0.0] * 4,
                   inertia=_box_inertia(mass, hi - lo) if p["dynamic"] else [0.0] * 12,
                   rb_center=[*map(float, center), 0.0] if p["dynamic"] else [0.0] * 4,
                   mass=float(mass), linear_damping=0.1, angular_damping=0.05, friction=0.3, restitution=0.3,
                   max_linear_velocity=250.0, max_angular_velocity=31.4159, penetration_depth=0.15,
                   motion_system=p["motion"], deactivator_type=p["deact"], solver_deactivation=p["solver"],
                   quality_type=p["quality"], rb_unknown2=bytes(12), constraints=[], body_flags=0)
    coll = nif.add("bhkCollisionObject", target=root, co_flags=1, body=body)
    nif.blocks[root]["collision"] = coll

    # geometry
    tri_shape = nif.add("NiTriShape", name=f"{name}:0", extra_data=[], controller=-1, flags=14,
                        translation=[0.0, 0.0, 0.0], rotation=IDENT, scale=1.0, properties=[], collision=-1,
                        data=-1, skin=-1, has_shader=0)
    # vanilla layout (verified against Knights.bsa meshes): all binormals first, then all tangents
    tbin = np.concatenate([bit.astype("<f4").ravel(), tan.astype("<f4").ravel()]).tobytes()
    tsx = nif.add("NiBinaryExtraData", name="Tangent space (binormal & tangent vectors)", binary=list(tbin))
    mat = nif.add("NiMaterialProperty", name="Material", extra_data=[], controller=-1,
                  ambient=[0.588, 0.588, 0.588], diffuse=[1.0, 1.0, 1.0], specular=list(specular),
                  emissive=[0.0, 0.0, 0.0], glossiness=float(glossiness), alpha=1.0)
    # block order matches vanilla: texturing property before its source texture
    tex = nif.add("NiTexturingProperty", name="", extra_data=[], controller=-1, apply_mode=2, texture_count=7,
                  has_base=1, base={"source": -1, "clamp_mode": 3, "filter_mode": 2, "uv_set": 0,
                                    "has_transform": 0},
                  has_dark=0, has_detail=0, has_gloss=0, has_glow=0, has_bump=0, has_decal0=0, shader_textures=[])
    src = nif.add("NiSourceTexture", name="", extra_data=[], controller=-1, use_external=1,
                  file_name=texture_path, unknown_link=-1, pixel_layout=6, use_mipmaps=1, alpha_format=3,
                  is_static=1, direct_render=1)
    nif.blocks[tex]["base"]["source"] = src
    c = (m.v.min(0) + m.v.max(0)) / 2
    radius = float(np.linalg.norm(m.v - c, axis=1).max())
    data = nif.add("NiTriShapeData", group_id=0, num_vertices=len(m.v), keep_flags=0, compress_flags=0,
                   has_vertices=1, vertices=m.v.astype(float).tolist(), data_flags=1, has_normals=1,
                   normals=normals.tolist(), center=c.tolist(), radius=radius, has_vertex_colors=0,
                   uv_sets=[m.uv.tolist()], consistency_flags=0, additional_data=-1,
                   num_triangles=len(m.f), num_triangle_points=len(m.f) * 3, has_triangles=1,
                   triangles=m.f.tolist(), match_groups=[])
    ts = nif.blocks[tri_shape]
    ts["extra_data"] = [tsx]; ts["properties"] = [tex, mat]; ts["data"] = data
    nif.blocks[root]["children"] = [tri_shape]
    if len(m.v) > 65535 or len(m.f) > 65535:
        raise ValueError("mesh exceeds 65535 vertices/triangles - split it into several NiTriShapes")
    return nif


def mesh_from_nif(nif: N.Nif) -> list[tuple[Mesh, str | None]]:
    """Extract every NiTriShape/NiTriStrips (with node transforms) as (Mesh, texture path)."""
    out = []

    def tex_of(geom):
        for pi in geom["properties"]:
            b = nif.blocks[pi]
            if b.type == "NiTexturingProperty" and b["has_base"]:
                s = nif.blocks[b["base"]["source"]]
                return s.data.get("file_name")
        return None

    def walk(i, M, t):
        b = nif.blocks[i]
        R = np.array(b["rotation"]).reshape(3, 3)
        M2 = M @ (R * b["scale"]); t2 = t + M @ np.array(b["translation"])
        if b.type == "NiNode":
            for c in b["children"]:
                if c >= 0:
                    walk(c, M2, t2)
        elif b.type in ("NiTriShape", "NiTriStrips"):
            d = nif.blocks[b["data"]]
            v = np.array(d["vertices"]) @ M2.T + t2
            uv = np.array(d["uv_sets"][0]) if d["uv_sets"] else np.zeros((len(v), 2))
            if d.type == "NiTriShapeData":
                f = np.array(d["triangles"])
            else:
                f = []
                for strip in d["points"]:
                    for k in range(len(strip) - 2):
                        a, b_, c = strip[k], strip[k + 1], strip[k + 2]
                        if a == b_ or b_ == c or a == c:
                            continue
                        f.append((a, b_, c) if k % 2 == 0 else (a, c, b_))
                f = np.array(f)
            out.append((Mesh(v, f, uv, names=[b["name"]]), tex_of(b)))

    for r in nif.roots:
        walk(r, np.eye(3), np.zeros(3))
    return out
