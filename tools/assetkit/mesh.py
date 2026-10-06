"""Triangle meshes for procedural Oblivion assets (numpy).

Conventions (match vanilla Oblivion meshes):
  * Units: game units (1 unit ~ 1.4 cm; a human is ~128 units tall, a longsword ~ 50-55 long).
  * Weapons: grip at the origin, blade/head along +Y, flat of the blade facing +/-Z.
  * Statics/clutter: origin at the base centre, +Z up, front faces -Y.
  * Faces are counter-clockwise when seen from outside (outward normals).

Every Mesh carries per-vertex UVs. Parts are combined with `merge`; each part can be given its
own UV atlas rectangle (`atlas_rect`) so one texture serves the whole asset.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Mesh:
    v: np.ndarray                      # (N,3) float32 positions
    f: np.ndarray                      # (M,3) int32 triangle indices
    uv: np.ndarray                     # (N,2) float32 texture coords (0..1, v down like DirectX)
    part: np.ndarray = field(default=None)  # (M,) int part id per face (for material/atlas bookkeeping)
    names: list = field(default_factory=list)

    def __post_init__(self):
        self.v = np.asarray(self.v, np.float64)
        self.f = np.asarray(self.f, np.int64).reshape(-1, 3)
        self.uv = np.asarray(self.uv, np.float64).reshape(-1, 2)
        if self.part is None:
            self.part = np.zeros(len(self.f), np.int64)
        if len(self.uv) != len(self.v):
            raise ValueError("uv count must equal vertex count")

    # ---------------------------------------------------------------- transforms
    def copy(self) -> "Mesh":
        return Mesh(self.v.copy(), self.f.copy(), self.uv.copy(), self.part.copy(), list(self.names))

    def translate(self, x=0.0, y=0.0, z=0.0) -> "Mesh":
        self.v = self.v + np.array([x, y, z]); return self

    def scale(self, sx, sy=None, sz=None) -> "Mesh":
        sy = sx if sy is None else sy; sz = sx if sz is None else sz
        self.v = self.v * np.array([sx, sy, sz])
        if sx * sy * sz < 0:
            self.f = self.f[:, ::-1].copy()
        return self

    def rotate(self, axis: str, degrees: float) -> "Mesh":
        a = np.radians(degrees); c, s = np.cos(a), np.sin(a)
        R = {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
             "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
             "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]
        self.v = self.v @ np.array(R).T; return self

    def atlas_rect(self, u0, v0, u1, v1) -> "Mesh":
        """Remap this part's 0..1 UVs into a sub-rectangle of the texture atlas."""
        self.uv = np.column_stack([u0 + self.uv[:, 0] * (u1 - u0), v0 + self.uv[:, 1] * (v1 - v0)]); return self

    # ---------------------------------------------------------------- queries
    @property
    def bounds(self):
        return self.v.min(0), self.v.max(0)

    def face_normals(self) -> np.ndarray:
        a, b, c = self.v[self.f[:, 0]], self.v[self.f[:, 1]], self.v[self.f[:, 2]]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        return n / np.where(ln == 0, 1, ln)

    def vertex_normals(self) -> np.ndarray:
        a, b, c = self.v[self.f[:, 0]], self.v[self.f[:, 1]], self.v[self.f[:, 2]]
        fn = np.cross(b - a, c - a)          # area weighted
        vn = np.zeros_like(self.v)
        for k in range(3):
            np.add.at(vn, self.f[:, k], fn)
        ln = np.linalg.norm(vn, axis=1, keepdims=True)
        return vn / np.where(ln == 0, 1, ln)

    def tangents(self, normals: np.ndarray | None = None):
        """Per-vertex tangent/bitangent from UVs (Lengyel), orthogonalised against the normal."""
        n = self.vertex_normals() if normals is None else normals
        t = np.zeros_like(self.v); b = np.zeros_like(self.v)
        i0, i1, i2 = self.f[:, 0], self.f[:, 1], self.f[:, 2]
        e1, e2 = self.v[i1] - self.v[i0], self.v[i2] - self.v[i0]
        d1, d2 = self.uv[i1] - self.uv[i0], self.uv[i2] - self.uv[i0]
        r = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
        r = np.where(np.abs(r) < 1e-12, 1e-12, r)
        sdir = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / r[:, None]
        tdir = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / r[:, None]
        for k in range(3):
            np.add.at(t, self.f[:, k], sdir); np.add.at(b, self.f[:, k], tdir)
        t = t - n * np.sum(n * t, 1, keepdims=True)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
        hand = np.sign(np.sum(np.cross(n, t) * b, 1, keepdims=True)); hand[hand == 0] = 1
        b = np.cross(n, t) * hand
        return t, b

    def split_sharp(self, angle_deg: float = 40.0) -> "Mesh":
        """Duplicate vertices along edges sharper than angle so normals stay crisp (flat-ish shading)."""
        fn = self.face_normals()
        cos_lim = np.cos(np.radians(angle_deg))
        new_v, new_uv, remap = [], [], {}
        out_f = np.empty_like(self.f)
        # group faces around each vertex by normal similarity
        vert_faces: dict[int, list[int]] = {}
        for fi, tri in enumerate(self.f):
            for vi in tri:
                vert_faces.setdefault(int(vi), []).append(fi)
        for vi, faces in vert_faces.items():
            groups: list[tuple[np.ndarray, list[int]]] = []
            for fi in faces:
                for g in groups:
                    if np.dot(g[0], fn[fi]) >= cos_lim:
                        g[1].append(fi); break
                else:
                    groups.append((fn[fi], [fi]))
            for _, fl in groups:
                idx = len(new_v); new_v.append(self.v[vi]); new_uv.append(self.uv[vi])
                for fi in fl:
                    remap[(fi, vi)] = idx
        for fi, tri in enumerate(self.f):
            out_f[fi] = [remap[(fi, int(x))] for x in tri]
        return Mesh(np.array(new_v), out_f, np.array(new_uv), self.part.copy(), list(self.names))

    def weld(self, eps: float = 1e-5) -> "Mesh":
        key = np.round(np.column_stack([self.v / eps, self.uv / eps])).astype(np.int64)
        _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        inv = inv.reshape(-1)
        return Mesh(self.v[first], inv[self.f], self.uv[first], self.part.copy(), list(self.names))


def merge(*meshes: Mesh) -> Mesh:
    vs, fs, uvs, parts, names = [], [], [], [], []
    off = 0
    for i, m in enumerate(meshes):
        vs.append(m.v); uvs.append(m.uv); fs.append(m.f + off)
        parts.append(np.full(len(m.f), i)); names.append(m.names[0] if m.names else f"part{i}")
        off += len(m.v)
    return Mesh(np.vstack(vs), np.vstack(fs), np.vstack(uvs), np.concatenate(parts), names)


# ---------------------------------------------------------------- primitives
def box(sx, sy, sz, name="box") -> Mesh:
    """Axis-aligned box centred on the origin, 24 verts (hard edges), cube-map style UVs per face."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [  # (normal axis corners) counter-clockwise from outside
        [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)],     # +Z
        [(-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz), (-hx, -hy, -hz)], # -Z
        [(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)],     # +X
        [(-hx, hy, -hz), (-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz)], # -X
        [(hx, hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz)],     # +Y
        [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)], # -Y
    ]
    v, f, uv = [], [], []
    for q in faces:
        b = len(v); v += q; uv += [(0, 1), (1, 1), (1, 0), (0, 0)]
        f += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return Mesh(v, f, uv, names=[name])


def lathe(profile, segments=16, axis="y", name="lathe", cap_start=True, cap_end=True) -> Mesh:
    """Revolve a profile [(radius, height), ...] around the axis. UV: u = angle, v = height order."""
    prof = np.asarray(profile, float)
    n = len(prof)
    ang = np.linspace(0, 2 * np.pi, segments + 1)
    v, uv = [], []
    lengths = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(prof, axis=0), axis=1))])
    tv = lengths / max(lengths[-1], 1e-9)
    for i, (r, h) in enumerate(prof):
        for j, a in enumerate(ang):
            x, z = r * np.cos(a), r * np.sin(a)
            v.append((x, h, z) if axis == "y" else (x, z, h))
            uv.append((j / segments, tv[i]))
    f = []
    W = segments + 1
    for i in range(n - 1):
        for j in range(segments):
            a, b, c, d = i * W + j, i * W + j + 1, (i + 1) * W + j + 1, (i + 1) * W + j
            f += [(a, c, b), (a, d, c)] if axis == "y" else [(a, b, c), (a, c, d)]
    m = Mesh(v, f, uv, names=[name])
    caps = []
    for idx, on, flip in ((0, cap_start, True), (n - 1, cap_end, False)):
        r, h = prof[idx]
        if on and r > 1e-6:
            c = disc(r, segments, h, axis, flip)
            caps.append(c)
    return merge(m, *caps) if caps else m


def disc(r, segments, h, axis="y", flip=False) -> Mesh:
    ang = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    pts = [(r * np.cos(a), h, r * np.sin(a)) if axis == "y" else (r * np.cos(a), r * np.sin(a), h) for a in ang]
    v = [(0, h, 0) if axis == "y" else (0, 0, h)] + pts
    uv = [(0.5, 0.5)] + [(0.5 + 0.5 * np.cos(a), 0.5 + 0.5 * np.sin(a)) for a in ang]
    f = []
    for j in range(segments):
        a, b = 1 + j, 1 + (j + 1) % segments
        up = (axis == "y")
        tri = (0, b, a) if up else (0, a, b)
        f.append(tri[::-1] if flip else tri)
    return Mesh(v, f, uv, names=["cap"])


def cylinder(r, h, segments=16, name="cylinder", axis="y") -> Mesh:
    return lathe([(r, 0), (r, h)], segments, axis, name)


def extrude(polygon, depth, name="extrude", bevel=0.0) -> Mesh:
    """Extrude a convex-or-simple 2D polygon [(x, y), ...] (counter-clockwise) along Z, centred on z=0.

    `bevel` > 0 pulls the front/back faces inward to give a sharpened edge (blades).
    Face UVs are planar (x,y normalised); side UVs run around the perimeter.
    """
    P = np.asarray(polygon, float)
    n = len(P)
    lo, hi = P.min(0), P.max(0)
    span = np.where(hi - lo == 0, 1, hi - lo)
    hz = depth / 2
    centroid = P.mean(0)
    inner = centroid + (P - centroid) * (1 - bevel) if bevel else P
    v, uv, f = [], [], []
    # front (+Z) and back (-Z) caps with fan triangulation (requires star-shaped polygon from centroid)
    for side, z in ((1, hz), (-1, -hz)):
        base = len(v)
        v.append((*centroid, z)); uv.append(tuple((centroid - lo) / span))
        for p in inner:
            v.append((p[0], p[1], z)); uv.append(((p[0] - lo[0]) / span[0], 1 - (p[1] - lo[1]) / span[1]))
        for i in range(n):
            a, b = base + 1 + i, base + 1 + (i + 1) % n
            f.append((base, a, b) if side == 1 else (base, b, a))
    # side walls: from inner front edge to outer rim (z=0) to inner back edge when bevelled
    per = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(np.vstack([P, P[:1]]), axis=0), axis=1))])
    per /= per[-1]
    rings = [(inner, hz, 0.0), (P, 0.0, 0.5), (inner, -hz, 1.0)] if bevel else [(P, hz, 0.0), (P, -hz, 1.0)]
    starts = []
    for pts, z, tv in rings:
        starts.append(len(v))
        for i in range(n + 1):
            p = pts[i % n]
            v.append((p[0], p[1], z)); uv.append((per[i], tv))
    for r in range(len(rings) - 1):
        s0, s1 = starts[r], starts[r + 1]
        for i in range(n):
            a, b, c, d = s0 + i, s0 + i + 1, s1 + i + 1, s1 + i
            f += [(a, d, c), (a, c, b)]
    return Mesh(v, f, uv, names=[name])


def loft(sections, name="loft", closed=True) -> Mesh:
    """Connect a list of rings (each (K,3) array, same K) into a tube; caps the ends if closed."""
    S = [np.asarray(s, float) for s in sections]
    K = len(S[0])
    v, uv, f = [], [], []
    for i, ring in enumerate(S):
        for j in range(K + 1):
            v.append(ring[j % K]); uv.append((j / K, i / (len(S) - 1)))
    W = K + 1
    for i in range(len(S) - 1):
        for j in range(K):
            a, b, c, d = i * W + j, i * W + j + 1, (i + 1) * W + j + 1, (i + 1) * W + j
            f += [(a, c, b), (a, d, c)]
    m = Mesh(v, f, uv, names=[name])
    if closed:
        caps = []
        for ring, flip in ((S[0], True), (S[-1], False)):
            c = ring.mean(0)
            cv = [c] + list(ring)
            cuv = [(0.5, 0.5)] + [(0.5, 0.5)] * K
            cf = [((0, j + 1, (j + 1) % K + 1) if flip else (0, (j + 1) % K + 1, j + 1)) for j in range(K)]
            caps.append(Mesh(cv, cf, cuv, names=["cap"]))
        m = merge(m, *caps)
    return m


def ellipse_ring(rx, rz, y, k=12, phase=0.0) -> np.ndarray:
    a = np.linspace(0, 2 * np.pi, k, endpoint=False) + phase
    return np.column_stack([rx * np.cos(a), np.full(k, y), rz * np.sin(a)])
