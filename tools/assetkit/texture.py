"""Procedural textures and DDS writing for Oblivion (numpy + Pillow).

Outputs follow vanilla conventions:
  <name>.dds     diffuse (RGB) + alpha (opacity, or unused)        DXT1 if no alpha, else DXT5
  <name>_n.dds   tangent-space normal map; ALPHA = specular strength (DXT5)
The engine finds the normal map automatically by the _n suffix, so only the diffuse path goes in
the NIF. Sizes must be powers of two; full mip chains are always written.

Material generators return float images in 0..1: color (H,W,3), height (H,W), spec (H,W).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

# --------------------------------------------------------------------------- noise


def _rng(seed):
    return np.random.default_rng(seed)


def value_noise(h, w, cells, seed=0) -> np.ndarray:
    """Tileable smooth value noise in 0..1 with `cells` lattice cells across the width."""
    g = _rng(seed).random((cells + 1, cells + 1))
    g[-1, :] = g[0, :]; g[:, -1] = g[:, 0]
    y = np.linspace(0, cells, h, endpoint=False); x = np.linspace(0, cells, w, endpoint=False)
    yi, xi = y.astype(int), x.astype(int)
    yf, xf = y - yi, x - xi
    sy, sx = yf * yf * (3 - 2 * yf), xf * xf * (3 - 2 * xf)
    a = g[yi][:, xi]; b = g[yi][:, xi + 1]; c = g[yi + 1][:, xi]; d = g[yi + 1][:, xi + 1]
    top = a + (b - a) * sx[None, :]; bot = c + (d - c) * sx[None, :]
    return top + (bot - top) * sy[:, None]


def fbm(h, w, base_cells=4, octaves=5, seed=0, gain=0.5) -> np.ndarray:
    out = np.zeros((h, w)); amp, tot = 1.0, 0.0
    for o in range(octaves):
        out += amp * value_noise(h, w, base_cells * 2 ** o, seed + o * 17); tot += amp; amp *= gain
    return out / tot


def stretched(h, w, cells_x, cells_y, seed=0, octaves=4) -> np.ndarray:
    """Anisotropic noise: cells_x across, cells_y down (brushed metal, wood grain)."""
    out = np.zeros((h, w)); amp, tot = 1.0, 0.0
    for o in range(octaves):
        cy, cx = max(1, cells_y * 2 ** o), max(1, cells_x * 2 ** o)
        n = value_noise(h, cx * 8, cx * 8, seed + o * 31)        # oversample then resize per axis
        from PIL import Image
        img = Image.fromarray((n * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        rows = np.asarray(img, float) / 255.0
        if cy > 1:
            rows = 0.5 * rows + 0.5 * value_noise(h, w, cy, seed + o * 7)
        out += amp * rows; tot += amp; amp *= 0.5
    return out / tot


def scratches(h, w, count=60, seed=0, length=0.25) -> np.ndarray:
    rng = _rng(seed)
    img = np.zeros((h, w))
    for _ in range(count):
        x0, y0 = rng.random() * w, rng.random() * h
        ang = rng.normal(0, 0.35) + (np.pi / 2 if rng.random() < 0.3 else 0)
        L = rng.random() * length * w
        t = np.linspace(0, 1, int(L) + 2)
        xs = ((x0 + np.cos(ang) * L * t) % w).astype(int); ys = ((y0 + np.sin(ang) * L * t) % h).astype(int)
        img[ys, xs] = np.maximum(img[ys, xs], rng.random() * 0.8 + 0.2)
    return img


def hex_color(c: str) -> np.ndarray:
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


# --------------------------------------------------------------------------- materials
@dataclass
class Layer:
    color: np.ndarray   # (H,W,3)
    height: np.ndarray  # (H,W)
    spec: np.ndarray    # (H,W)


def material(kind: str, size=(256, 256), color="#a0a4a8", seed=0, **kw) -> Layer:
    h, w = size
    base = hex_color(color)
    if kind == "metal":          # brushed steel / iron; kw: brushed (bool), wear (0..1)
        grain = stretched(h, w, 64, 2, seed) if kw.get("brushed", True) else fbm(h, w, 8, 5, seed)
        blotch = fbm(h, w, 3, 4, seed + 5)
        scr = scratches(h, w, int(80 * kw.get("wear", 0.5)) + 5, seed + 9)
        lum = 0.82 + 0.18 * grain - 0.12 * (blotch - 0.5) + 0.12 * scr
        col = np.clip(base[None, None, :] * lum[..., None], 0, 1)
        return Layer(col, 0.5 + 0.08 * grain - 0.15 * scr, np.clip(0.75 + 0.2 * grain - 0.3 * blotch * kw.get("wear", 0.5), 0, 1))
    if kind == "blade":          # metal + sharpened edge bevel + optional fuller; u runs across the blade width
        l = material("metal", size, color, seed, brushed=True, wear=kw.get("wear", 0.35))
        u = np.linspace(0, 1, w)[None, :].repeat(h, 0)
        edge = np.clip(1 - np.minimum(u, 1 - u) / max(kw.get("edge", 0.12), 1e-3), 0, 1)   # 1 at the edge
        fw = kw.get("fuller", 0.0)
        groove = np.clip(1 - np.abs(u - 0.5) / max(fw / 2, 1e-3), 0, 1) if fw > 0 else np.zeros_like(u)
        lum = 1 + 0.18 * edge - 0.22 * groove
        l.color = np.clip(l.color * lum[..., None], 0, 1)
        l.height = l.height - 0.25 * groove ** 0.5 - 0.1 * edge
        l.spec = np.clip(l.spec + 0.2 * edge - 0.1 * groove, 0, 1)
        return l
    if kind == "gold":
        l = material("metal", size, color, seed, brushed=False, wear=kw.get("wear", 0.3))
        l.spec = np.clip(l.spec + 0.15, 0, 1); return l
    if kind == "leather":        # grip wraps; kw: wraps (count of diagonal bands)
        n = fbm(h, w, 16, 5, seed)
        yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
        wraps = kw.get("wraps", 8)
        band = np.abs(np.sin(np.pi * (yy * wraps + xx * 1.0)))
        groove = np.clip((band - 0.08) * 6, 0, 1)
        lum = (0.75 + 0.25 * n) * (0.55 + 0.45 * groove)
        return Layer(np.clip(base * lum[..., None], 0, 1), 0.3 + 0.5 * groove + 0.1 * n, 0.15 + 0.1 * n)
    if kind == "wood":
        g = stretched(h, w, 2, 48, seed + 3)
        rings = 0.5 + 0.5 * np.sin((g * 18 + fbm(h, w, 4, 3, seed) * 4) * np.pi)
        lum = 0.65 + 0.25 * rings + 0.1 * g
        return Layer(np.clip(base * lum[..., None], 0, 1), 0.5 + 0.2 * rings, 0.1 + 0.1 * rings)
    if kind == "cloth":
        yy, xx = np.mgrid[0:h, 0:w]
        weave = (np.sin(xx * np.pi / 2) * np.sin(yy * np.pi / 2) + 1) / 2
        n = fbm(h, w, 8, 4, seed)
        lum = 0.8 + 0.12 * weave + 0.1 * n
        return Layer(np.clip(base * lum[..., None], 0, 1), 0.5 + 0.2 * weave, 0.05 + 0.0 * n)
    if kind == "stone":
        n = fbm(h, w, 6, 6, seed); cr = fbm(h, w, 12, 3, seed + 1)
        cracks = np.clip(1 - np.abs(cr - 0.5) * 30, 0, 1)
        lum = 0.7 + 0.3 * n - 0.35 * cracks
        return Layer(np.clip(base * lum[..., None], 0, 1), n - 0.4 * cracks, 0.1 + 0.1 * n)
    if kind == "gem":
        n = fbm(h, w, 4, 3, seed)
        lum = 0.75 + 0.35 * n
        return Layer(np.clip(base * lum[..., None], 0, 1), 0.5 + 0.1 * n, np.full((h, w), 0.95))
    raise ValueError(f"unknown material kind {kind!r} (metal, gold, leather, wood, cloth, stone, gem)")


def atlas(regions: list[tuple[tuple[float, float, float, float], Layer]], size=(512, 512)) -> Layer:
    """Paint layers into UV rectangles (u0, v0, u1, v1) of one texture. Layers are resized to fit."""
    from PIL import Image
    H, W = size
    col = np.zeros((H, W, 3)); hei = np.full((H, W), 0.5); spe = np.zeros((H, W))
    for (u0, v0, u1, v1), L in regions:
        x0, x1 = int(round(u0 * W)), int(round(u1 * W)); y0, y1 = int(round(v0 * H)), int(round(v1 * H))
        if x1 <= x0 or y1 <= y0:
            continue
        def fit(a):
            if a.ndim == 3:
                img = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).resize((x1 - x0, y1 - y0), Image.BILINEAR)
                return np.asarray(img, float) / 255.0
            img = Image.fromarray((np.clip(a, 0, 1) * 65535).astype(np.uint16)).resize((x1 - x0, y1 - y0), Image.BILINEAR)
            return np.asarray(img, float) / 65535.0
        col[y0:y1, x0:x1] = fit(L.color); hei[y0:y1, x0:x1] = fit(L.height); spe[y0:y1, x0:x1] = fit(L.spec)
    return Layer(col, hei, spe)


def normal_from_height(height: np.ndarray, strength=4.0, green: str = "dx") -> np.ndarray:
    """Tangent-space normal map (RGB 0..1) from a height field.

    green="dx": green points down the image (DirectX, +V); "gl": green up. Which one Oblivion's
    shaders expect is still UNVERIFIED in game for assetkit output - check bumps on the first
    test asset (agent-docs/11 §6) and flip with the recipe key "normal_green" if they look inverted.
    """
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5
    gy = dy if green == "dx" else -dy
    n = np.dstack([-dx * strength, gy * strength, np.ones_like(height)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


# --------------------------------------------------------------------------- DDS
DDSD = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000  # caps|height|width|pixelformat|mipmapcount|linearsize


def _to_u8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def _mips(rgba: np.ndarray) -> list[np.ndarray]:
    from PIL import Image
    out = [rgba]
    h, w = rgba.shape[:2]
    while h > 1 or w > 1:
        h, w = max(1, h // 2), max(1, w // 2)
        out.append(np.asarray(Image.fromarray(out[-1]).resize((w, h), Image.BOX)))
    return out


def _rgb565(c):  # c (...,3) uint8
    c = c.astype(np.uint32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def _unpack565(v):
    r = ((v >> 11) & 31) * 255 // 31; g = ((v >> 5) & 63) * 255 // 63; b = (v & 31) * 255 // 31
    return np.stack([r, g, b], -1).astype(np.int32)


def _blocks(img: np.ndarray):
    h, w = img.shape[:2]
    ph, pw = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    if (ph, pw) != (h, w):
        img = np.pad(img, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")
    b = img.reshape(ph // 4, 4, pw // 4, 4, img.shape[2]).transpose(0, 2, 1, 3, 4).reshape(-1, 16, img.shape[2])
    return b


def _encode_color_blocks(rgb_blocks: np.ndarray) -> np.ndarray:
    """BC1 color part: endpoints = min/max along the principal axis; 4-colour mode. Returns (N,8) uint8."""
    px = rgb_blocks.astype(np.float64)
    mean = px.mean(1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", px - mean, px - mean)
    axis = np.ones((len(px), 3)) / np.sqrt(3)
    for _ in range(4):
        axis = np.einsum("nij,nj->ni", cov, axis)
        axis /= np.maximum(np.linalg.norm(axis, axis=1, keepdims=True), 1e-9)
    proj = np.einsum("nki,ni->nk", px - mean, axis)
    lo = mean[:, 0] + axis * proj.min(1, keepdims=True); hi = mean[:, 0] + axis * proj.max(1, keepdims=True)
    c0 = _rgb565(np.clip(hi, 0, 255).astype(np.uint8)); c1 = _rgb565(np.clip(lo, 0, 255).astype(np.uint8))
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    eq = c0 == c1                       # flat block: index 0 everywhere (valid in any mode)
    e0, e1 = _unpack565(c0), _unpack565(c1)
    pal = np.stack([e0, e1, (2 * e0 + e1) // 3, (e0 + 2 * e1) // 3], 1)          # (N,4,3)
    d = ((px[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)                   # (N,16,4)
    idx = d.argmin(-1).astype(np.uint32)
    idx[eq] = 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.zeros((len(px), 8), np.uint8)
    out[:, 0:2] = np.stack([c0 & 255, c0 >> 8], 1)
    out[:, 2:4] = np.stack([c1 & 255, c1 >> 8], 1)
    out[:, 4:8] = np.stack([(bits >> s) & 255 for s in (0, 8, 16, 24)], 1)
    return out


def _encode_alpha_blocks(a_blocks: np.ndarray) -> np.ndarray:
    """BC3 alpha part (8-alpha interpolated mode). Returns (N,8) uint8."""
    a = a_blocks[..., 0].astype(np.int32)
    a0, a1 = a.max(1), a.min(1)
    flat = a0 == a1                     # a0 > a1 selects 8-alpha mode; flat blocks use index 0
    pal = np.stack([a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)], 1)  # (N,8)
    idx = np.abs(a[:, :, None] - pal[:, None, :]).argmin(-1).astype(np.uint64)
    idx[flat] = 0
    bits = (idx << (3 * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.zeros((len(a), 8), np.uint8)
    out[:, 0] = a0; out[:, 1] = a1
    for k in range(6):
        out[:, 2 + k] = ((bits >> np.uint64(8 * k)) & np.uint64(255)).astype(np.uint8)
    return out


def encode_dds(rgba_u8: np.ndarray, fmt: str = "DXT5") -> bytes:
    """rgba_u8: (H,W,4) uint8, power-of-two sides. fmt: DXT1, DXT5 or RGBA (uncompressed 32-bit)."""
    h, w = rgba_u8.shape[:2]
    if h & (h - 1) or w & (w - 1):
        raise ValueError(f"texture size {w}x{h} is not a power of two")
    mips = _mips(rgba_u8)
    body = bytearray()
    for m in mips:
        if fmt == "RGBA":
            body += m[..., [2, 1, 0, 3]].tobytes()           # BGRA in memory
            continue
        blk = _blocks(m)
        col = _encode_color_blocks(blk[..., :3])
        if fmt == "DXT1":
            body += col.tobytes()
        else:
            body += np.hstack([_encode_alpha_blocks(blk[..., 3:4]), col]).tobytes()
    if fmt == "RGBA":
        pf = struct.pack("<II4sIIIII", 32, 0x41, b"\0\0\0\0", 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
        linear = w * 4
        flags = DDSD & ~0x80000 | 0x8
    else:
        pf = struct.pack("<II4sIIIII", 32, 0x4, fmt.encode(), 0, 0, 0, 0, 0)
        linear = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == "DXT1" else 16)
        flags = DDSD
    caps = 0x1000 | 0x8 | 0x400000  # texture | complex | mipmap
    hdr = struct.pack("<4sIIIIIII44x", b"DDS ", 124, flags, h, w, linear, 0, len(mips)) + pf + \
        struct.pack("<IIII4x", caps, 0, 0, 0)
    return hdr + bytes(body)


def save_textures(layer: Layer, base_path, normal_strength=4.0, alpha: np.ndarray | None = None,
                  preview_png: bool = True, normal_green: str = "dx") -> dict:
    """Write <base>.dds (+ <base>_n.dds) and PNG previews. Returns file paths."""
    from pathlib import Path
    from PIL import Image
    base = Path(base_path)
    base.parent.mkdir(parents=True, exist_ok=True)
    rgb = _to_u8(layer.color)
    a = _to_u8(alpha) if alpha is not None else np.full(rgb.shape[:2], 255, np.uint8)
    diffuse = np.dstack([rgb, a])
    nrm = _to_u8(normal_from_height(layer.height, normal_strength, normal_green))
    normal = np.dstack([nrm, _to_u8(layer.spec)])
    d_path = base.with_suffix(".dds"); n_path = base.parent / (base.name + "_n.dds")
    d_path.write_bytes(encode_dds(diffuse, "DXT5" if alpha is not None else "DXT1"))
    n_path.write_bytes(encode_dds(normal, "DXT5"))
    out = {"diffuse": str(d_path), "normal": str(n_path)}
    if preview_png:
        Image.fromarray(rgb).save(base.parent / (base.name + "_preview.png"))
        Image.fromarray(nrm).save(base.parent / (base.name + "_n_preview.png"))
    return out


def check_dds(path) -> dict:
    """Validate a DDS file the way Oblivion needs it: power-of-two, mipmaps, DXT1/DXT5/RGBA."""
    from pathlib import Path
    b = Path(path).read_bytes()
    problems = []
    if b[:4] != b"DDS ":
        return {"ok": False, "problems": ["not a DDS file"]}
    h, w, mips = struct.unpack_from("<III", b, 12)[0], struct.unpack_from("<I", b, 16)[0], struct.unpack_from("<I", b, 28)[0]
    fourcc = b[84:88]
    if h & (h - 1) or w & (w - 1):
        problems.append(f"size {w}x{h} not power of two")
    full = int(np.log2(max(w, h))) + 1
    if mips < full:
        problems.append(f"{mips} mipmaps (need {full}) - textures shimmer/blur and can look wrong at distance")
    try:
        from PIL import Image
        Image.open(path).load()
    except Exception as exc:
        problems.append(f"Pillow could not decode it: {exc}")
    return {"ok": not problems, "width": w, "height": h, "mipmaps": mips,
            "format": fourcc.decode("latin-1").strip("\0") or "RGBA", "problems": problems}
