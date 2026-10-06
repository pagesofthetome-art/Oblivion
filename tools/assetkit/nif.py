"""Oblivion NIF (Gamebryo 20.0.0.5, user version 11) reader/writer for static and weapon meshes.

Pure Python. Supports the block types used by Oblivion statics, clutter and weapons:
  NiNode, NiTriShape, NiTriStrips, NiTriShapeData, NiTriStripsData, NiMaterialProperty,
  NiTexturingProperty, NiSourceTexture, NiAlphaProperty, NiSpecularProperty, NiStencilProperty,
  NiVertexColorProperty, BSXFlags, NiStringExtraData, NiBinaryExtraData,
  bhkCollisionObject, bhkRigidBody, bhkRigidBodyT, bhkConvexVerticesShape, bhkBoxShape,
  bhkSphereShape, bhkCapsuleShape, bhkListShape, bhkConvexTransformShape, bhkTransformShape.

Validation: `python -m assetkit.nif roundtrip <file.nif>` parses a file and re-serialises it;
identical bytes prove the block definitions match the real format. Unknown block types raise
NotImplementedError (the file is then outside what assetkit can safely rewrite).

Format references: niftools nif.xml (version-conditioned field list), checked against vanilla
Oblivion meshes from Knights.bsa / DLC BSAs.
"""

from __future__ import annotations

import io
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VERSION = 0x14000005
HEADER_LINE = b"Gamebryo File Format, Version 20.0.0.5\n"
USER_VERSION = 11
USER_VERSION_2 = 11


# --------------------------------------------------------------------------- primitive IO
class R:
    def __init__(self, data: bytes):
        self.b = data
        self.p = 0

    def take(self, fmt: str):
        v = struct.unpack_from("<" + fmt, self.b, self.p)
        self.p += struct.calcsize("<" + fmt)
        return v

    def u8(self): return self.take("B")[0]
    def u16(self): return self.take("H")[0]
    def u32(self): return self.take("I")[0]
    def i32(self): return self.take("i")[0]
    def f32(self): return self.take("f")[0]
    def floats(self, n): return list(self.take(f"{n}f"))
    def raw(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v
    def sstr(self):
        n = self.u32()
        return self.raw(n).decode("latin-1")


class W:
    def __init__(self):
        self.o = io.BytesIO()

    def put(self, fmt: str, *v): self.o.write(struct.pack("<" + fmt, *v))
    def u8(self, v): self.put("B", v)
    def u16(self, v): self.put("H", v)
    def u32(self, v): self.put("I", v)
    def i32(self, v): self.put("i", v)
    def f32(self, v): self.put("f", v)
    def floats(self, vs): self.put(f"{len(vs)}f", *vs)
    def raw(self, b): self.o.write(b)
    def sstr(self, s: str):
        b = s.encode("latin-1")
        self.u32(len(b)); self.o.write(b)
    def bytes(self): return self.o.getvalue()


# --------------------------------------------------------------------------- schema
# A schema is a list of steps. Each step is (name, type) or a callable for conditionals.
# Types: u8 u16 u32 i32 f32 str ref vec2 vec3 vec4 quat mat33 rgb rgba
#        ("list", count_type, item_type)   count read first, items follow
#        ("arr", count_key, item_type)     count taken from an already-read field (callable or key)
#        ("bytes", n)                       fixed raw bytes
#        ("if", predicate(d), [steps])

FIXED = {"u8": "B", "u16": "H", "u32": "I", "i32": "i", "f32": "f", "ref": "i",
         "vec2": "2f", "vec3": "3f", "vec4": "4f", "quat": "4f", "mat33": "9f", "rgb": "3f", "rgba": "4f",
         "tri": "3H", "mat34": "12f"}


def _read_type(r: R, t, d):
    if isinstance(t, str):
        if t == "str":
            return r.sstr()
        if t in ("u8", "u16", "u32", "i32", "f32", "ref"):
            return r.take(FIXED[t])[0]
        return list(r.take(FIXED[t]))
    kind = t[0]
    if kind == "bytes":
        return r.raw(t[1])
    if kind == "list":
        n = _read_type(r, t[1], d)
        return [_read_type(r, t[2], d) for _ in range(n)]
    if kind == "arr":
        n = t[1](d) if callable(t[1]) else d[t[1]]
        if t[2] in FIXED and t[2] in ("u16", "u8") and n > 64:
            return list(r.take(f"{n}{FIXED[t[2]]}"))
        return [_read_type(r, t[2], d) for _ in range(n)]
    if kind == "struct":
        sub: dict = {}
        _read_steps(r, t[1], sub)
        return sub
    raise TypeError(t)


def _write_type(w: W, t, v, d):
    if isinstance(t, str):
        if t == "str":
            return w.sstr(v)
        f = FIXED[t]
        if t in ("u8", "u16", "u32", "i32", "f32", "ref"):
            return w.put(f, v)
        return w.put(f, *v)
    kind = t[0]
    if kind == "bytes":
        assert len(v) == t[1], (t, len(v))
        return w.raw(v)
    if kind == "list":
        _write_type(w, t[1], len(v), d)
        for x in v:
            _write_type(w, t[2], x, d)
        return
    if kind == "arr":
        n = t[1](d) if callable(t[1]) else d[t[1]]
        if len(v) != n:
            raise ValueError(f"array length {len(v)} != declared {n}")
        for x in v:
            _write_type(w, t[2], x, d)
        return
    if kind == "struct":
        return _write_steps(w, t[1], v)
    raise TypeError(t)


def _read_steps(r: R, steps, d: dict):
    for s in steps:
        if s[0] == "if":
            if s[1](d):
                _read_steps(r, s[2], d)
            continue
        name, t = s
        d[name] = _read_type(r, t, d)


def _write_steps(w: W, steps, d: dict):
    for s in steps:
        if s[0] == "if":
            if s[1](d):
                _write_steps(w, s[2], d)
            continue
        name, t = s
        _write_type(w, t, d[name], d)


# --------------------------------------------------------------------------- block definitions
OBJECT_NET = [("name", "str"), ("extra_data", ("list", "u32", "ref")), ("controller", "ref")]
AV_OBJECT = OBJECT_NET + [("flags", "u16"), ("translation", "vec3"), ("rotation", "mat33"), ("scale", "f32"),
                          ("properties", ("list", "u32", "ref")), ("collision", "ref")]
EXTRA = [("name", "str")]
TEX_DESC = ("struct", [("source", "ref"), ("clamp_mode", "u32"), ("filter_mode", "u32"), ("uv_set", "u32"),
                       ("has_transform", "u8"),
                       ("if", lambda d: d["has_transform"], [("tx_translation", "vec2"), ("tx_tiling", "vec2"),
                                                             ("tx_rotation", "f32"), ("tx_method", "u32"),
                                                             ("tx_center", "vec2")])])
SHADER_TEX = ("struct", [("has_map", "u8"), ("if", lambda d: d["has_map"], [("map", TEX_DESC), ("map_id", "u32")])])


def _slot(name, extra=None):
    steps = [(f"has_{name}", "u8"), ("if", lambda d, n=name: d[f"has_{n}"], [(name, TEX_DESC)] + (extra or []))]
    return steps


GEOM_DATA = [
    ("group_id", "i32"), ("num_vertices", "u16"), ("keep_flags", "u8"), ("compress_flags", "u8"),
    ("has_vertices", "u8"),
    ("if", lambda d: d["has_vertices"], [("vertices", ("arr", "num_vertices", "vec3"))]),
    ("data_flags", "u16"),
    ("has_normals", "u8"),
    ("if", lambda d: d["has_normals"], [("normals", ("arr", "num_vertices", "vec3"))]),
    ("if", lambda d: d["has_normals"] and (d["data_flags"] & 0x1000),
     [("tangents", ("arr", "num_vertices", "vec3")), ("bitangents", ("arr", "num_vertices", "vec3"))]),
    ("center", "vec3"), ("radius", "f32"),
    ("has_vertex_colors", "u8"),
    ("if", lambda d: d["has_vertex_colors"], [("vertex_colors", ("arr", "num_vertices", "rgba"))]),
    ("uv_sets", ("arr", lambda d: d["data_flags"] & 0x3F, ("arr", "num_vertices", "vec2"))),
    ("consistency_flags", "u16"), ("additional_data", "ref"),
]

HAVOK_FILTER = [("layer", "u8"), ("filter_flags", "u8"), ("group", "u16")]
WORLD_OBJECT = [("shape", "ref")] + HAVOK_FILTER + [("world_unused1", ("bytes", 4)), ("broadphase", "u8"),
                                                    ("world_unused2", ("bytes", 3)), ("cinfo_property", ("bytes", 12))]
RIGID_BODY_INFO = [
    # bhkEntity response block
    ("collision_response", "u8"), ("entity_unused", "u8"), ("contact_callback_delay", "u16"),
    # bhkRigidBodyCInfo (Havok 5.5/6.6 layout used by Oblivion)
    ("rb_unknown_int", ("bytes", 4)), ("rb_layer", "u8"), ("rb_filter_flags", "u8"), ("rb_group", "u16"),
    ("rb_unused2", ("bytes", 4)), ("rb_collision_response", "u8"), ("rb_unused3", "u8"),
    ("rb_callback_delay", "u16"), ("rb_unknown", ("bytes", 4)),
    ("rb_translation", "vec4"), ("rb_rotation", "quat"), ("linear_velocity", "vec4"),
    ("angular_velocity", "vec4"), ("inertia", "mat34"), ("rb_center", "vec4"), ("mass", "f32"),
    ("linear_damping", "f32"), ("angular_damping", "f32"), ("friction", "f32"), ("restitution", "f32"),
    ("max_linear_velocity", "f32"), ("max_angular_velocity", "f32"), ("penetration_depth", "f32"),
    ("motion_system", "u8"), ("deactivator_type", "u8"), ("solver_deactivation", "u8"), ("quality_type", "u8"),
    ("rb_unknown2", ("bytes", 12)),
    ("constraints", ("list", "u32", "ref")), ("body_flags", "u32"),
]

BLOCKS: dict[str, list] = {
    "NiNode": AV_OBJECT + [("children", ("list", "u32", "ref")), ("effects", ("list", "u32", "ref"))],
    "NiTriShape": AV_OBJECT + [("data", "ref"), ("skin", "ref"), ("has_shader", "u8"),
                               ("if", lambda d: d["has_shader"], [("shader_name", "str"), ("shader_unknown", "i32")])],
    "NiTriShapeData": GEOM_DATA + [
        ("num_triangles", "u16"), ("num_triangle_points", "u32"), ("has_triangles", "u8"),
        ("if", lambda d: d["has_triangles"], [("triangles", ("arr", "num_triangles", "tri"))]),
        ("match_groups", ("list", "u16", ("list", "u16", "u16"))),
    ],
    "NiTriStripsData": GEOM_DATA + [
        ("num_triangles", "u16"), ("num_strips", "u16"), ("strip_lengths", ("arr", "num_strips", "u16")),
        ("has_points", "u8"),
        ("if", lambda d: d["has_points"],
         [("points", ("arr", "num_strips", ("arr_dyn", None)))]),
    ],
    "NiMaterialProperty": OBJECT_NET + [("ambient", "rgb"), ("diffuse", "rgb"), ("specular", "rgb"),
                                        ("emissive", "rgb"), ("glossiness", "f32"), ("alpha", "f32")],
    "NiTexturingProperty": OBJECT_NET + [("apply_mode", "u32"), ("texture_count", "u32")]
        + _slot("base") + _slot("dark") + _slot("detail") + _slot("gloss") + _slot("glow")
        + _slot("bump", [("bump_luma_scale", "f32"), ("bump_luma_offset", "f32"), ("bump_matrix", "vec4")])
        + [("if", lambda d: d["texture_count"] >= 7, _slot("decal0")),
           ("if", lambda d: d["texture_count"] >= 8, _slot("decal1")),
           ("if", lambda d: d["texture_count"] >= 9, _slot("decal2")),
           ("if", lambda d: d["texture_count"] >= 10, _slot("decal3")),
           ("shader_textures", ("list", "u32", SHADER_TEX))],
    "NiSourceTexture": OBJECT_NET + [
        ("use_external", "u8"),
        ("if", lambda d: d["use_external"], [("file_name", "str"), ("unknown_link", "ref")]),
        ("if", lambda d: not d["use_external"], [("original_file_name", "str"), ("pixel_data", "ref")]),
        ("pixel_layout", "u32"), ("use_mipmaps", "u32"), ("alpha_format", "u32"), ("is_static", "u8"),
        ("direct_render", "u8"),
    ],
    "NiAlphaProperty": OBJECT_NET + [("alpha_flags", "u16"), ("threshold", "u8")],
    "NiSpecularProperty": OBJECT_NET + [("spec_flags", "u16")],
    "NiStencilProperty": OBJECT_NET + [("stencil_enabled", "u8"), ("stencil_function", "u32"), ("stencil_ref", "u32"),
                                       ("stencil_mask", "u32"), ("fail_action", "u32"), ("zfail_action", "u32"),
                                       ("pass_action", "u32"), ("draw_mode", "u32")],
    "NiVertexColorProperty": OBJECT_NET + [("vc_flags", "u16"), ("vertex_mode", "u32"), ("lighting_mode", "u32")],
    "BSXFlags": EXTRA + [("integer", "u32")],
    "NiStringExtraData": EXTRA + [("string", "str")],
    "NiBinaryExtraData": EXTRA + [("binary", ("list", "u32", "u8"))],
    "bhkCollisionObject": [("target", "ref"), ("co_flags", "u16"), ("body", "ref")],
    "bhkRigidBody": WORLD_OBJECT + RIGID_BODY_INFO,
    "bhkConvexVerticesShape": [("material", "u32"), ("radius", "f32"), ("vertices_property", ("bytes", 12)),
                               ("normals_property", ("bytes", 12)),
                               ("cv_vertices", ("list", "u32", "vec4")), ("cv_normals", ("list", "u32", "vec4"))],
    "bhkBoxShape": [("material", "u32"), ("radius", "f32"), ("box_unused", ("bytes", 8)), ("dimensions", "vec3"),
                    ("box_unused2", "f32")],
    "bhkSphereShape": [("material", "u32"), ("radius", "f32")],
    "bhkCapsuleShape": [("material", "u32"), ("radius", "f32"), ("cap_unused", ("bytes", 8)),
                        ("first_point", "vec3"), ("radius1", "f32"), ("second_point", "vec3"), ("radius2", "f32")],
    "bhkListShape": [("sub_shapes", ("list", "u32", "ref")), ("material", "u32"),
                     ("child_shape_property", ("bytes", 12)), ("child_filter_property", ("bytes", 12)),
                     ("unknown_ints", ("list", "u32", "u32"))],
    "bhkConvexTransformShape": [("shape", "ref"), ("material", "u32"), ("radius", "f32"),
                                ("ct_unused", ("bytes", 8)), ("transform", ("arr", lambda d: 16, "f32"))],
}
BLOCKS["NiTriStrips"] = BLOCKS["NiTriShape"]
BLOCKS["bhkRigidBodyT"] = BLOCKS["bhkRigidBody"]
BLOCKS["bhkTransformShape"] = BLOCKS["bhkConvexTransformShape"]

# NiTriStripsData points need per-strip lengths: patch the reader with explicit code below.


@dataclass
class Block:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, k): return self.data[k]
    def __setitem__(self, k, v): self.data[k] = v


@dataclass
class Nif:
    blocks: list[Block] = field(default_factory=list)
    roots: list[int] = field(default_factory=lambda: [0])
    export_info: tuple[str, str, str] = ("assetkit", "assetkit", "assetkit")

    def index(self, blk: Block) -> int:
        return next(i for i, b in enumerate(self.blocks) if b is blk)

    def add(self, type_: str, **data) -> int:
        self.blocks.append(Block(type_, data))
        return len(self.blocks) - 1

    def of_type(self, t: str) -> list[Block]:
        return [b for b in self.blocks if b.type == t]


def _read_block(r: R, t: str) -> dict:
    if t not in BLOCKS:
        raise NotImplementedError(f"block type {t} is not supported by assetkit.nif")
    d: dict = {}
    if t == "NiTriStripsData":
        steps = BLOCKS[t]
        _read_steps(r, [s for s in steps if not (s[0] == "if" and len(s[2]) and s[2][0][0] == "points")], d)
        if d["has_points"]:
            d["points"] = [list(r.take(f"{n}H")) for n in d["strip_lengths"]]
        return d
    _read_steps(r, BLOCKS[t], d)
    return d


def _write_block(w: W, t: str, d: dict):
    if t == "NiTriStripsData":
        steps = BLOCKS[t]
        _write_steps(w, [s for s in steps if not (s[0] == "if" and len(s[2]) and s[2][0][0] == "points")], d)
        if d["has_points"]:
            for strip in d["points"]:
                w.put(f"{len(strip)}H", *strip)
        return
    _write_steps(w, BLOCKS[t], d)


def _sstr8(r: R) -> str:
    n = r.u8()
    return r.raw(n).rstrip(b"\0").decode("latin-1")


def read(path_or_bytes) -> Nif:
    data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else Path(path_or_bytes).read_bytes()
    nl = data.index(b"\n")
    if data[:nl + 1] != HEADER_LINE:
        raise ValueError(f"not a 20.0.0.5 NIF: {data[:nl]!r}")
    r = R(data)
    r.p = nl + 1
    ver, endian, uv, nblocks, uv2 = r.u32(), r.u8(), r.u32(), r.u32(), r.u32()
    if ver != VERSION or uv != USER_VERSION:
        raise ValueError(f"unsupported NIF version {ver:#x} user {uv}")
    info = (_sstr8(r), _sstr8(r), _sstr8(r))
    types = [r.sstr() for _ in range(r.u16())]
    idx = list(r.take(f"{nblocks}H"))
    r.u32()  # unknown int 2 (0)
    nif = Nif(export_info=info)
    for i in idx:
        t = types[i]
        nif.blocks.append(Block(t, _read_block(r, t)))
    nroots = r.u32()
    nif.roots = list(r.take(f"{nroots}i"))
    if r.p != len(data):
        raise ValueError(f"parsed {r.p} of {len(data)} bytes - trailing data")
    return nif


def write(nif: Nif) -> bytes:
    w = W()
    w.raw(HEADER_LINE)
    w.u32(VERSION); w.u8(1); w.u32(USER_VERSION); w.u32(len(nif.blocks)); w.u32(USER_VERSION_2)
    for s in nif.export_info:
        b = s.encode("latin-1") + b"\0"
        w.u8(len(b)); w.raw(b)
    types: list[str] = []
    for b in nif.blocks:
        if b.type not in types:
            types.append(b.type)
    w.u16(len(types))
    for t in types:
        w.sstr(t)
    for b in nif.blocks:
        w.u16(types.index(b.type))
    w.u32(0)
    for b in nif.blocks:
        _write_block(w, b.type, b.data)
    w.u32(len(nif.roots))
    for r_ in nif.roots:
        w.i32(r_)
    return w.bytes()


def summary(nif: Nif) -> list[str]:
    out = []
    for i, b in enumerate(nif.blocks):
        d = b.data
        extra = ""
        if "name" in d and d["name"]:
            extra += f" name={d['name']!r}"
        if b.type == "NiSourceTexture" and d.get("use_external"):
            extra += f" file={d['file_name']!r}"
        if b.type in ("NiTriShapeData", "NiTriStripsData"):
            extra += f" verts={d['num_vertices']} tris={d['num_triangles']} uvsets={d['data_flags'] & 0x3F}" \
                     f" tangents={'yes' if d['data_flags'] & 0x1000 else 'no'}"
        if b.type == "NiStringExtraData":
            extra += f" value={d['string']!r}"
        if b.type == "BSXFlags":
            extra += f" flags={d['integer']:#x}"
        if b.type == "bhkRigidBody" or b.type == "bhkRigidBodyT":
            extra += f" layer={d['layer']} mass={d['mass']:.2f} motion={d['motion_system']} quality={d['quality_type']}"
        if b.type.startswith("bhk") and "material" in d:
            extra += f" material={d['material']}"
        out.append(f"[{i}] {b.type}{extra}")
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="assetkit NIF tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info"); s.add_argument("files", nargs="+")
    s = sub.add_parser("roundtrip"); s.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    bad = 0
    for f in a.files:
        try:
            raw = Path(f).read_bytes()
            nif = read(raw)
            if a.cmd == "info":
                print(f"{f}:")
                print("\n".join("  " + x for x in summary(nif)))
            else:
                ok = write(nif) == raw
                bad += not ok
                print(f"{'OK  ' if ok else 'DIFF'} {f}")
        except NotImplementedError as exc:
            print(f"SKIP {f}: {exc}")
        except Exception as exc:
            bad += 1
            print(f"FAIL {f}: {type(exc).__name__}: {exc}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
