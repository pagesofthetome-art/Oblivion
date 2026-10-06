"""Software preview renderer (numpy + Pillow): lets an agent *look* at an asset without Blender.

render_views(mesh, texture_rgb) -> PIL image sheet with front / side / 3-4 / top views.
render_icon(...)                 -> square RGBA image for an inventory icon.
Lighting: one key light + fill + ambient, Blinn specular driven by the spec map (normal map alpha).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw


def _look(yaw, pitch):
    """Rotation matrix for a camera orbiting the object (yaw around Z-up world, pitch down)."""
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    return Rx @ Rz


def _sample(tex, uv):
    h, w = tex.shape[:2]
    x = np.clip((uv[..., 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
    y = np.clip((uv[..., 1] % 1.0) * (h - 1), 0, h - 1).astype(int)
    return tex[y, x]


def render(mesh, tex=None, spec=None, size=512, yaw=30.0, pitch=20.0, up="z", bg=(38, 40, 46, 255),
           transparent=False, fill=0.82):
    """Orthographic render. up='y' for weapons (blade along +Y), 'z' for statics."""
    V = mesh.v.copy()
    if up == "y":                              # convert Y-up asset to Z-up view space
        V = V[:, [0, 2, 1]] * np.array([1, -1, 1])
    N = mesh.vertex_normals()
    if up == "y":
        N = N[:, [0, 2, 1]] * np.array([1, -1, 1])
    R = _look(np.radians(yaw), np.radians(pitch))
    # camera looks along +Y in view space, screen x = X, screen y = Z
    P = V @ R.T; Nn = N @ R.T
    lo, hi = P.min(0), P.max(0)
    span = max(hi[0] - lo[0], hi[2] - lo[2], 1e-6)
    scale = size * fill / span
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    sx = (P[:, 0] - cx) * scale + size / 2
    sy = size / 2 - (P[:, 2] - cz) * scale
    depth = P[:, 1]
    img = np.zeros((size, size, 3)); zbuf = np.full((size, size), np.inf); alpha = np.zeros((size, size))
    light = np.array([-0.45, -0.6, 0.66]); light /= np.linalg.norm(light)
    fill_l = np.array([0.7, -0.3, 0.2]); fill_l /= np.linalg.norm(fill_l)
    view = np.array([0, -1, 0])
    half = (light + view); half /= np.linalg.norm(half)
    uv = mesh.uv
    for tri in mesh.f:
        x, y, z = sx[tri], sy[tri], depth[tri]
        x0, x1 = int(max(np.floor(x.min()), 0)), int(min(np.ceil(x.max()), size - 1))
        y0, y1 = int(max(np.floor(y.min()), 0)), int(min(np.ceil(y.max()), size - 1))
        if x1 < x0 or y1 < y0:
            continue
        area = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0])
        if abs(area) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((x[1] - gx) * (y[2] - gy) - (x[2] - gx) * (y[1] - gy)) / area
        w1 = ((x[2] - gx) * (y[0] - gy) - (x[0] - gx) * (y[2] - gy)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        m = inside & (zz < sub)
        if not m.any():
            continue
        n = (w0[..., None] * Nn[tri[0]] + w1[..., None] * Nn[tri[1]] + w2[..., None] * Nn[tri[2]])[m]
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        if np.dot(n.mean(0), view) < -0.2:     # back face seen: flip so thin parts still shade
            n = -n
        t = (w0[..., None] * uv[tri[0]] + w1[..., None] * uv[tri[1]] + w2[..., None] * uv[tri[2]])[m]
        base = _sample(tex, t) if tex is not None else np.full((len(t), 3), 0.7)
        s = _sample(spec, t) if spec is not None else np.full(len(t), 0.3)
        diff = np.clip(n @ light, 0, 1) * 0.85 + np.clip(n @ fill_l, 0, 1) * 0.25 + 0.18
        sp = np.clip(n @ half, 0, 1) ** 40 * s * 0.9
        col = np.clip(base * diff[:, None] + sp[:, None], 0, 1)
        block = img[y0:y1 + 1, x0:x1 + 1]; block[m] = col
        sub[m] = zz[m]; alpha[y0:y1 + 1, x0:x1 + 1][m] = 1
    out = np.dstack([img * 255, alpha * 255]).astype(np.uint8)
    im = Image.fromarray(out, "RGBA")
    if transparent:
        return im
    bgim = Image.new("RGBA", im.size, bg)
    bgim.alpha_composite(im)
    return bgim


VIEWS = [("front", 0, 0), ("side", 90, 0), ("three-quarter", 35, 22), ("top", 0, 89)]


def render_views(mesh, tex=None, spec=None, up="z", size=384, title="") -> Image.Image:
    tiles = [render(mesh, tex, spec, size, yaw, pitch, up) for _, yaw, pitch in VIEWS]
    sheet = Image.new("RGBA", (size * 2, size * 2 + 28), (24, 25, 29, 255))
    d = ImageDraw.Draw(sheet)
    for i, (name, _, _) in enumerate(VIEWS):
        x, y = (i % 2) * size, (i // 2) * size + 28
        sheet.paste(tiles[i], (x, y))
        d.text((x + 6, y + 4), name, fill=(220, 220, 220, 255))
    d.text((6, 7), title, fill=(255, 210, 120, 255))
    return sheet


def render_icon(mesh, tex=None, spec=None, up="z", size=128, yaw=35, pitch=20, rotate=-45) -> Image.Image:
    """Transparent-background icon. Weapons are drawn diagonally like vanilla icons."""
    big = render(mesh, tex, spec, size * 4, yaw, pitch, up, transparent=True, fill=0.9)
    if rotate:
        big = big.rotate(rotate, resample=Image.BICUBIC, expand=False)
    return big.resize((size, size), Image.LANCZOS)
