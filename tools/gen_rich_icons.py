"""Re-shade the flat ride-intro silhouettes into rich, multi-shade BMPs (desktop tool).

The original icons used 3-8 colors on a panel that shows 4096 (bit_depth=4). This reads
each icon's FLAT source from ``designs/originals/`` (the preserved pre-enhancement art,
the "before"), keeps its human-approved SHAPE, and replaces every flat fill with a
4-bit-clean shade ramp lit from the top-left, plus rim light and ambient occlusion at
the base. A handful of hero rides get hand-tuned ramps + extras (neon, glows, lit
windows, sky sparkle); every other icon is shaded generically from its own region
colors. Same icon, with depth and palette sophistication — not a redraw.

Shades are ordered-dithered onto the bit_depth=4 grid by default, so gradients read
smooth at LED viewing distance instead of banding (validated on hardware: this matches
bit_depth=6 with no refresh cost). Output is the exact device format (64x32 indexed BMP,
sky=index 0, top-left sky), via make_ride_image._build/_save_preview. Desktop-only.

    python tools/gen_rich_icons.py            # rebuild EVERY icon (dithered) from originals
    python tools/gen_rich_icons.py tron       # just one
    python tools/gen_rich_icons.py --no-dither   # flat-banded shades (no dithering)

Copyright (c) 2024-2026 Michael Czeiszperger
"""
import glob
import math
import os
import sys

from PIL import Image

import make_ride_image as mri   # sibling module (tools/ on sys.path when run directly)

W, H = mri.W, mri.H
OUT_DIR = mri.OUT_DIR
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG_DIR = os.path.join(_ROOT, "designs", "originals")   # flat "before" source art
PREVIEW_DIR = os.path.join(_ROOT, "designs")


def q4(rgb):
    """Snap each channel to the bit_depth=4 grid (multiples of 0x11) -> sim == device."""
    return tuple(round(c / 17) * 17 for c in rgb)


def ramp(dark, light, n):
    """n 4-bit-clean shades from `dark` to `light` (index 0 = darkest)."""
    out = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 1.0
        out.append(q4(tuple(dark[c] + (light[c] - dark[c]) * t for c in range(3))))
    return out


def _mix(a, b, t):
    return tuple(a[c] + (b[c] - a[c]) * t for c in range(3))


def ramp3(dark, mid, light, n=6):
    """An n-shade ramp passing through `mid` (dark -> mid -> light), all 4-bit-clean."""
    half = n // 2
    return ramp(dark, mid, half + 1)[:-1] + ramp(mid, light, n - half)


def _gen_bayer(size):
    m = [[0]]
    s = 1
    while s < size:
        nm = [[0] * (s * 2) for _ in range(s * 2)]
        for y in range(s):
            for x in range(s):
                v = m[y][x]
                nm[y][x] = 4 * v
                nm[y][x + s] = 4 * v + 2
                nm[y + s][x] = 4 * v + 3
                nm[y + s][x + s] = 4 * v + 1
        m = nm
        s *= 2
    return m


_BAYER = _gen_bayer(8)
DITHER = True             # ordered-dither continuous shades to 4-bit (--no-dither turns off)


def _dither_rgb(c, x, y):
    """Ordered-dither a continuous RGB color onto the bit_depth=4 grid, per channel, so
    a gradient that would band into ~6 steps reads smooth at LED viewing distance."""
    t = (_BAYER[y % 8][x % 8] + 0.5) / 64.0
    out = []
    for v in c:
        scaled = v / 255 * 15
        lo = int(scaled)
        idx = lo + (1 if (scaled - lo) > t else 0)
        idx = 15 if idx > 15 else 0 if idx < 0 else idx
        out.append(idx * 17)
    return (out[0], out[1], out[2])


def auto_ramp(base):
    """A 6-shade ramp CENTERED on a region's flat color (the original sits mid-ramp), so
    shading adds depth without washing the color out. The shadow drops to 0.34x and the
    highlight brightens by VALUE (x1.38), not toward white, to preserve saturation —
    punchy reds stay red, not pink. Wider endpoints = visibly more shades on the panel."""
    shadow = tuple(c * 0.34 for c in base)
    hi = tuple(min(255, c * 1.38) for c in base)
    return [q4(shadow), q4(_mix(shadow, base, 0.45)), q4(base),
            q4(_mix(base, hi, 0.4)), q4(_mix(base, hi, 0.72)), q4(hi)]


class Pal:
    """Palette accumulator: index 0 is always sky-black; dedups colors."""
    def __init__(self):
        self.colors = [(0, 0, 0)]
        self._idx = {(0, 0, 0): 0}

    def of(self, rgb):
        rgb = q4(rgb)
        if rgb == (0, 0, 0):                 # never collide a real shade with sky
            rgb = (17, 17, 17)
        i = self._idx.get(rgb)
        if i is None:
            i = len(self.colors)
            self._idx[rgb] = i
            self.colors.append(rgb)
        return i


def _load(name):
    """(RGB pixel grid, subject mask set, bbox) for a flat original; bg = top-left."""
    im = Image.open(os.path.join(ORIG_DIR, name + ".bmp")).convert("RGB")
    px = im.load()
    bg = px[0, 0]
    grid = [[px[x, y] for x in range(W)] for y in range(H)]
    mask = {(x, y) for y in range(H) for x in range(W) if grid[y][x] != bg}
    xs = [x for x, _ in mask] or [0]
    ys = [y for _, y in mask] or [0]
    return grid, mask, (min(xs), min(ys), max(xs), max(ys))


def _shade(name, region_ramps, extras=None, occlude=True, centered=False, light_fn=None):
    """Re-shade `name` using {existing_hex: (ramp, level_bias)} and optional extras().

    Lighting is global top-left across the whole icon bbox; rim-light brightens top/left
    edges and ambient-occlusion darkens bottom/right edges, so every material gets a
    coherent 3-D read. ``centered`` (the generic path) centers the light on L=0.5 so a
    ramp's MIDDLE shade (the original flat color) dominates and only edges swing bright/
    dark — this preserves saturation. ``light_fn(x, y, bbox) -> L`` overrides the base
    light for shapes the linear model can't read (a sphere needs radial light, water a
    vertical gradient). Hero ramps go dark->light, so they keep the bright-biased curve.
    Writes the BMP + a preview; returns the final color count.
    """
    grid, mask, (x0, y0, x1, y1) = _load(name)
    gw = max(1, x1 - x0)
    gh = max(1, y1 - y0)
    pal = Pal()
    out = [[0] * W for _ in range(H)]

    def bg(x, y):
        return not (0 <= x < W and 0 <= y < H) or (x, y) not in mask

    for (x, y) in mask:
        hexc = "%02x%02x%02x" % grid[y][x]
        spec = region_ramps.get(hexc)
        if spec is None:
            spec = next(iter(region_ramps.values()))   # unmapped -> first material
        rmp, bias = spec
        left = 1.0 - (x - x0) / gw
        top = 1.0 - (y - y0) / gh
        if light_fn is not None:
            L = light_fn(x, y, (x0, y0, x1, y1)) + bias
        elif centered:
            L = 0.5 + 0.50 * (left - 0.5) + 0.24 * (top - 0.5) + bias
        else:
            L = 0.42 + 0.32 * left + 0.16 * top + bias
        if bg(x - 1, y) or bg(x, y - 1) or bg(x - 1, y - 1):
            L += 0.22 if centered else 0.26            # rim highlight (lit edge)
        if occlude and (bg(x + 1, y) or bg(x, y + 1) or bg(x + 1, y + 1)):
            L -= 0.20                                   # ambient occlusion (shadow edge)
        L = 0.0 if L < 0 else 1.0 if L > 1 else L
        if DITHER:
            p = L * (len(rmp) - 1)
            lo = int(p)
            if lo >= len(rmp) - 1:
                col = rmp[-1]
            else:                                  # continuous along the ramp polyline
                f = p - lo
                a, b = rmp[lo], rmp[lo + 1]
                col = tuple(a[i] + (b[i] - a[i]) * f for i in range(3))
            out[y][x] = pal.of(_dither_rgb(col, x, y))
        else:
            out[y][x] = pal.of(rmp[round(L * (len(rmp) - 1))])

    if extras:
        extras(out, pal, mask, (x0, y0, x1, y1))

    img, colors = mri._build(out, pal.colors)
    img.save(os.path.join(OUT_DIR, name + ".bmp"))
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    mri._save_preview(img, colors, os.path.join(PREVIEW_DIR, name + ".rich.preview.png"))
    return len(colors)


def generic(name):
    """Shade any icon from its own region colors (no hand-tuning, no extras)."""
    _grid, mask, _ = _load(name)
    colors = {"%02x%02x%02x" % _grid[y][x] for (x, y) in mask}
    region_ramps = {h: (auto_ramp((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))), 0.0)
                    for h in colors}
    return _shade(name, region_ramps, centered=True)


def _dot(out, pal, x, y, rgb):
    if 0 <= x < W and 0 <= y < H:
        out[y][x] = pal.of(rgb)


# ---- hand-tuned hero icons --------------------------------------------------------

# Shared material ramps (dark -> flat -> light, 4-bit-clean), reused across the Efteling
# hero set at the bottom of this section so common materials (wood, water, gold, steel,
# greenery) read with consistent depth. Signature elements (dragon fire, fairy wings,
# snake scales) still get bespoke ramps inside their own functions.
_RED     = ramp3((0x88, 0x14, 0x14), (0xeb, 0x3c, 0x3c), (0xff, 0x7a, 0x66), 6)
_GOLD    = ramp3((0x88, 0x55, 0x11), (0xff, 0xd2, 0x46), (0xff, 0xf4, 0xaa), 6)
_CREAM   = ramp3((0x8a, 0x7a, 0x55), (0xea, 0xdf, 0xc4), (0xff, 0xff, 0xf0), 6)
_WOOD    = ramp3((0x4a, 0x2a, 0x12), (0x9a, 0x5f, 0x2c), (0xd6, 0x96, 0x54), 6)
_DKWOOD  = ramp((0x24, 0x12, 0x08), (0x5a, 0x34, 0x1c), 4)
_STEEL   = ramp3((0x36, 0x3c, 0x4c), (0x9c, 0x9f, 0xb0), (0xe8, 0xee, 0xff), 6)
_DKSTEEL = ramp3((0x1c, 0x20, 0x2c), (0x4c, 0x50, 0x60), (0x88, 0x90, 0xa4), 6)
_WATER   = ramp3((0x0a, 0x44, 0x88), (0x1f, 0x6f, 0xd6), (0x88, 0xdd, 0xff), 6)
_BLUE    = ramp((0x1e, 0x30, 0x80), (0x7a, 0xa0, 0xf0), 5)
_GREEN   = ramp3((0x0e, 0x3a, 0x14), (0x36, 0xb0, 0x3e), (0x9a, 0xf0, 0x66), 6)
_DKGREEN = ramp((0x08, 0x24, 0x0e), (0x2c, 0x6a, 0x30), 5)
_WHITE   = ramp((0xcc, 0xcc, 0xdd), (0xff, 0xff, 0xff), 3)


def space_mountain():
    structure = ramp((0x44, 0x55, 0x99), (0xFF, 0xFF, 0xFF), 6)
    ribs = ramp((0x22, 0x33, 0x77), (0x66, 0x88, 0xEE), 5)
    R = {"ffffff": (structure, 0.0), "2a50c0": (ribs, 0.05), "182860": (ribs, -0.2)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        for x in range(x0 + 4, x1 - 3):
            for y in range(y1 - 1, min(H, y1 + 2)):
                if (x, y) not in mask:
                    d = (y - y1) + 1
                    _dot(out, pal, x, y, (0xCC - d * 0x33, 0x66 - d * 0x22, 0x11))
        for (sx, sy, c) in [(6, 4, (0xFF, 0xFF, 0xFF)), (54, 6, (0xCC, 0xDD, 0xFF)),
                            (12, 9, (0x66, 0x88, 0xCC)), (48, 3, (0xFF, 0xCC, 0x66)),
                            (58, 14, (0x99, 0xAA, 0xDD)), (3, 12, (0x55, 0x66, 0xAA))]:
            if (sx, sy) not in mask:
                _dot(out, pal, sx, sy, c)
    return _shade("space_mountain", R, extras)


def tron():
    body = ramp((0x22, 0x22, 0x33), (0x55, 0x60, 0x80), 5)
    neon = ramp((0x0A, 0x44, 0x88), (0xCC, 0xFF, 0xFF), 6)
    R = {"4c5060": (body, 0.0), "1f6fd6": (neon, 0.25)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        for x in range(0, x0):
            t = x / max(1, x0)
            cy = (y0 + y1) // 2
            for y in (cy - 1, cy, cy + 1):
                if (x, y) not in mask:
                    _dot(out, pal, x, y, (int(0x33 * t), int(0xBB * t), int(0xEE * t)))
        for x in range(x0, x1 + 1, 2):
            if (x, y1 + 3) not in mask:
                _dot(out, pal, x, y1 + 3, (0x11, 0x55, 0x77))
    return _shade("tron", R, extras, occlude=True)


def everest():
    rock = ramp((0x3A, 0x24, 0x18), (0xC0, 0x90, 0x60), 6)
    snow = ramp((0x88, 0xAA, 0xDD), (0xFF, 0xFF, 0xFF), 5)
    R = {"9c9fb0": (rock, 0.0), "eadfc4": (snow, 0.08)}

    def extras(out, pal, mask, bbox):
        for (sx, sy, c) in [(7, 5, (0xCC, 0xDD, 0xFF)), (56, 4, (0xFF, 0xFF, 0xFF)),
                            (50, 9, (0x88, 0x99, 0xCC)), (14, 3, (0x99, 0xAA, 0xDD))]:
            if (sx, sy) not in mask:
                _dot(out, pal, sx, sy, c)
    return _shade("everest", R, extras)


def big_thunder_goat():
    # white goat with real contour (shadowed belly/legs -> lit back), standing on a
    # Big-Thunder-Mountain red-rock/dirt mesa instead of the flat bluish stone it was.
    goat = ramp3((0x6E, 0x68, 0x5A), (0xCC, 0xC4, 0xAE), (0xFF, 0xFF, 0xF4), 6)
    rock = ramp3((0x5A, 0x2C, 0x16), (0xA8, 0x5E, 0x30), (0xDD, 0x9E, 0x5C), 6)
    dirt = ramp((0x2E, 0x18, 0x0C), (0x5A, 0x32, 0x18), 3)   # the dark hoof/shadow specks
    dyna = ramp((0xB0, 0x22, 0x22), (0xFF, 0x55, 0x44), 5)   # red dynamite cylinder
    fuse = ramp((0xC0, 0x55, 0x11), (0xFF, 0x99, 0x33), 3)   # orange wick
    spark = ramp((0xFF, 0xAA, 0x22), (0xFF, 0xFF, 0xCC), 3)  # hot yellow-white spark
    # Flat source hexes: eb3c3c="r", ff8822="O", ffe044="y" — each needs a key or
    # _shade falls the pixel back to the FIRST material (fur) and the fuse/stick
    # would render cream. Sparks get a big positive bias so they read as LIT.
    R = {"eadfc4": (goat, 0.08), "9c9fb0": (rock, 0.10), "4e2c12": (dirt, 0.0),
         "eb3c3c": (dyna, 0.14), "ff8822": (fuse, 0.24), "ffe044": (spark, 0.42)}
    return _shade("big_thunder_goat", R, occlude=True)


def castle():
    stone = ramp((0x49, 0x58, 0x7F), (0xCC, 0xD4, 0xE8), 6)
    roof = ramp((0x1E, 0x30, 0x80), (0x7A, 0xA0, 0xF0), 6)
    gold = ramp((0xCC, 0x99, 0x22), (0xFF, 0xE0, 0x55), 4)
    dark = ramp((0x22, 0x26, 0x3A), (0x40, 0x48, 0x66), 4)
    red = ramp((0xCC, 0x22, 0x22), (0xFF, 0x66, 0x55), 4)
    R = {"9c9fb0": (stone, 0.0), "2a50c0": (roof, 0.05), "eadfc4": (gold, 0.1),
         "4c5060": (dark, -0.1), "eb3c3c": (red, 0.15)}

    def extras(out, pal, mask, bbox):
        for (wx, wy) in [(15, 20), (15, 23), (31, 18), (31, 21), (47, 20), (47, 23),
                         (23, 24), (39, 24)]:
            if (wx, wy) in mask:
                _dot(out, pal, wx, wy, (0xFF, 0xCC, 0x55))
        for (sx, sy, c) in [(9, 4, (0xFF, 0xEE, 0x88)), (54, 6, (0x88, 0xCC, 0xFF)),
                            (44, 3, (0xFF, 0x99, 0xCC))]:
            if (sx, sy) not in mask:
                _dot(out, pal, sx, sy, c)
    return _shade("castle", R, extras)


def _vertical(x, y, bbox):
    """1.0 at the top of the shape, 0.0 at the bottom (top-lit / crest-bright)."""
    x0, y0, x1, y1 = bbox
    return 1.0 - (y - y0) / max(1, y1 - y0)


def _radial(cxf, cyf, reach, squash=1.0):
    """Light brightest at a point (cxf,cyf as fractions of the bbox), falling off over
    `reach` x the bbox radius — for spheres / glows. `squash` narrows the x-axis."""
    def fn(x, y, bbox):
        x0, y0, x1, y1 = bbox
        cx = x0 + (x1 - x0) * cxf
        cy = y0 + (y1 - y0) * cyf
        R = max(x1 - x0, y1 - y0) / 2 or 1
        d = math.hypot((x - cx) * squash, y - cy)
        return 1.0 - d / (R * reach)
    return fn


def haunted_mansion():
    # spectral ghost: luminous greenish core -> white -> cool blue at the drips
    body = ramp3((0x44, 0x55, 0x66), (0xCC, 0xDD, 0xDD), (0xEE, 0xFF, 0xEE), 6)
    R = {"ffffff": (body, 0.0)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) // 2
        for (dx, dy, c) in [(0, 2, (0x66, 0xFF, 0xAA)), (-1, 4, (0x33, 0xCC, 0x88))]:
            if (cx + dx, y0 + dy) in mask:                # faint green heart-glow
                _dot(out, pal, cx + dx, y0 + dy, c)
    return _shade("haunted_mansion", R, extras, occlude=True,
                  light_fn=_radial(0.5, 0.38, 1.5, squash=0.8))


def skull():
    bone = ramp3((0x55, 0x55, 0x66), (0xCC, 0xC4, 0xAA), (0xFF, 0xFF, 0xEE), 6)
    R = {"eadfc4": (bone, 0.0)}
    return _shade("skull", R, occlude=True, light_fn=_vertical)


def splash():
    water = ramp3((0x11, 0x44, 0x99), (0x22, 0x77, 0xDD), (0x88, 0xDD, 0xFF), 6)
    foam = ramp((0xCC, 0xEE, 0xFF), (0xFF, 0xFF, 0xFF), 3)
    R = {"1f6fd6": (water, 0.0), "eadfc4": (foam, 0.1)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        for (sx, sy, c) in [(20, y0 - 1, (0x88, 0xDD, 0xFF)), (32, y0 - 2, (0xCC, 0xF0, 0xFF)),
                            (44, y0, (0x66, 0xCC, 0xFF))]:
            if (sx, sy) not in mask:
                _dot(out, pal, sx, sy, c)
    return _shade("splash", R, extras, occlude=False, light_fn=_vertical)


def seashell():
    cream = ramp3((0x88, 0x77, 0x44), (0xEA, 0xDF, 0xC4), (0xFF, 0xFF, 0xEE), 6)
    gold = ramp3((0x88, 0x55, 0x11), (0xFF, 0xD2, 0x46), (0xFF, 0xF0, 0xAA), 6)
    R = {"eadfc4": (cream, 0.0), "ffd246": (gold, 0.05)}
    # lit from the top rim, fanning down to the shadowed hinge at bottom-centre
    return _shade("seashell", R, occlude=True, light_fn=_radial(0.5, 1.05, 1.7))


def spaceship_earth():
    panel = ramp3((0x33, 0x3A, 0x4A), (0x9C, 0x9F, 0xB0), (0xDD, 0xE4, 0xF0), 6)
    facet = ramp3((0x22, 0x26, 0x33), (0x55, 0x59, 0x66), (0x88, 0x8E, 0x9C), 6)
    R = {"9c9fb0": (panel, 0.0), "4c5060": (facet, -0.05)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox                              # specular glint, upper-left
        for (fx, fy) in [(0.30, 0.26), (0.36, 0.20)]:
            sx = int(x0 + (x1 - x0) * fx); sy = int(y0 + (y1 - y0) * fy)
            if (sx, sy) in mask:
                _dot(out, pal, sx, sy, (0xFF, 0xFF, 0xFF))
    return _shade("spaceship_earth", R, extras, occlude=True,
                  light_fn=_radial(0.34, 0.30, 1.9))


def wave():
    water = ramp3((0x0A, 0x44, 0x77), (0x1F, 0x6F, 0xD6), (0x66, 0xCC, 0xFF), 6)
    foam = ramp((0xCC, 0xEE, 0xFF), (0xFF, 0xFF, 0xFF), 3)
    R = {"1f6fd6": (water, 0.0), "eadfc4": (foam, 0.1)}

    def extras(out, pal, mask, bbox):
        for (sx, sy, c) in [(18, 2, (0xCC, 0xF0, 0xFF)), (24, 1, (0xFF, 0xFF, 0xFF)),
                            (12, 4, (0x88, 0xDD, 0xFF))]:
            if (sx, sy) not in mask:
                _dot(out, pal, sx, sy, c)
    return _shade("wave", R, extras, occlude=True, light_fn=_vertical)


# ---- Efteling hero icons ----------------------------------------------------------
# These 15 silhouettes drive Efteling's marquee rides (Joris en de Draak, Python,
# Droomvlucht, Piraña, Pagode, Fata Morgana, ...). They were previously auto-shaded (a
# mild 6-shade ramp CENTERED on the flat colour, so only edges swung). Here each gets
# hand-tuned material ramps + accents so the gradients actually read on the panel. Shared
# with every other park that uses the same silhouette.

def bird():
    feather = ramp3((0x22, 0x2a, 0x3a), (0x4c, 0x50, 0x60), (0x9a, 0xaa, 0xc8), 6)
    R = {"4c5060": (feather, 0.0), "ffffff": (_WHITE, 0.05),
         "ffd246": (_GOLD, 0.0), "9c9fb0": (_STEEL, 0.0), "4e2c12": (_DKWOOD, 0.0)}
    return _shade("bird", R, occlude=True)


def canoe():
    R = {"1f6fd6": (_WATER, 0.0), "9a5f2c": (_WOOD, 0.0),
         "eadfc4": (_CREAM, 0.05), "4e2c12": (_DKWOOD, 0.0)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        for fx in (0.2, 0.5, 0.8):                      # foam flecks along the waterline
            sx = int(x0 + (x1 - x0) * fx)
            if (sx, y1) not in mask:
                _dot(out, pal, sx, y1, (0xcc, 0xf0, 0xff))
    return _shade("canoe", R, extras, occlude=True)


def carousel_horse():
    horse = ramp3((0x8a, 0x82, 0x6a), (0xea, 0xdf, 0xc4), (0xff, 0xff, 0xf6), 6)
    R = {"eadfc4": (horse, 0.06), "2a50c0": (_BLUE, 0.0),
         "ffd246": (_GOLD, 0.05), "eb3c3c": (_RED, 0.05)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) // 2
        if (cx, y0) not in mask:
            _dot(out, pal, cx, y0, (0xff, 0xff, 0xcc))   # brass-pole top sparkle
    return _shade("carousel_horse", R, extras, occlude=True)


def child():
    dress = ramp3((0x99, 0x18, 0x18), (0xeb, 0x3c, 0x3c), (0xff, 0x86, 0x74), 6)
    hair = ramp3((0x4a, 0x2a, 0x12), (0x9a, 0x5f, 0x2c), (0xd6, 0x9a, 0x58), 6)
    skin = ramp3((0xb0, 0x82, 0x5e), (0xea, 0xdf, 0xc4), (0xff, 0xf2, 0xe2), 6)
    R = {"eb3c3c": (dress, 0.05), "9a5f2c": (hair, 0.05),
         "eadfc4": (skin, 0.08), "2a50c0": (_BLUE, 0.0)}
    return _shade("child", R, occlude=True)


def coaster_car():
    car = ramp3((0x99, 0x18, 0x18), (0xeb, 0x3c, 0x3c), (0xff, 0x86, 0x6a), 6)
    R = {"eb3c3c": (car, 0.05), "4c5060": (_DKSTEEL, 0.0),
         "9c9fb0": (_STEEL, 0.0), "eadfc4": (_CREAM, 0.05), "ffd246": (_GOLD, 0.0),
         "9a5f2c": (_WOOD, 0.0), "4e2c12": (_DKWOOD, 0.0)}   # trestle lattice
    return _shade("coaster_car", R, occlude=True)


def dragon():
    scale = ramp3((0x0e, 0x3a, 0x14), (0x36, 0xb0, 0x3e), (0x9a, 0xf0, 0x66), 6)
    fire = [q4(c) for c in [(0xcc, 0x22, 0x11), (0xee, 0x44, 0x11), (0xff, 0x77, 0x11),
                            (0xff, 0xaa, 0x22), (0xff, 0xcc, 0x33), (0xff, 0xee, 0x66)]]
    tooth = ramp((0xbb, 0xaa, 0x88), (0xff, 0xff, 0xee), 4)
    R = {"36b03e": (scale, 0.0), "1c6228": (_DKGREEN, 0.0), "eb3c3c": (fire, 0.15),
         "eadfc4": (tooth, 0.0), "ffd246": (_GOLD, 0.1), "ffe044": (_GOLD, 0.15),
         "4e2c12": (_DKWOOD, 0.0)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        cy = (y0 + y1) // 2
        for dx in range(1, 5):                          # fire glow trailing off the muzzle
            gx = x0 - dx
            if (gx, cy) not in mask:
                t = 1.0 - dx / 5.0
                _dot(out, pal, gx, cy, (int(0xff * t), int(0xaa * t), int(0x22 * t)))
    return _shade("dragon", R, extras, occlude=True)


def fairy():
    wing1 = ramp3((0x11, 0x22, 0x66), (0x2a, 0x50, 0xc0), (0x9a, 0xd6, 0xff), 6)
    wing2 = ramp3((0x11, 0x44, 0x99), (0x1f, 0x6f, 0xd6), (0xa0, 0xe4, 0xff), 6)
    body = ramp3((0x99, 0x18, 0x18), (0xeb, 0x3c, 0x3c), (0xff, 0x86, 0x74), 6)
    star = ramp((0xcc, 0x99, 0x22), (0xff, 0xff, 0xbb), 5)
    R = {"2a50c0": (wing1, 0.1), "1f6fd6": (wing2, 0.1), "eb3c3c": (body, 0.05),
         "eadfc4": (_CREAM, 0.05), "ffd246": (star, 0.15), "ffe044": (star, 0.2),
         "ffffff": (_WHITE, 0.1)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) // 2
        if (cx, y0) not in mask:
            _dot(out, pal, cx, y0, (0xff, 0xff, 0xdd))   # crown-star glint
    return _shade("fairy", R, extras, occlude=False)


def fish():
    body = ramp3((0x33, 0x3a, 0x4a), (0x9c, 0x9f, 0xb0), (0xe8, 0xee, 0xff), 6)
    belly = ramp3((0x99, 0x18, 0x18), (0xeb, 0x3c, 0x3c), (0xff, 0x7a, 0x66), 6)
    R = {"9c9fb0": (body, 0.0), "eb3c3c": (belly, 0.05),
         "ffffff": (_WHITE, 0.05), "4c5060": (_DKSTEEL, -0.05), "4e2c12": (_DKWOOD, 0.0)}
    return _shade("fish", R, occlude=True, light_fn=_radial(0.6, 0.34, 1.9))


def locomotive():
    boiler = ramp3((0x0a, 0x2a, 0x10), (0x1c, 0x62, 0x28), (0x5a, 0xc0, 0x5c), 6)
    R = {"1c6228": (boiler, 0.0), "4c5060": (_DKSTEEL, 0.0), "2a50c0": (_BLUE, 0.0),
         "eb3c3c": (_RED, 0.05), "9a5f2c": (_WOOD, 0.0), "9c9fb0": (_STEEL, 0.0),
         "ffd246": (_GOLD, 0.0)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        sx = int(x0 + (x1 - x0) * 0.28)                 # steam puffs off the stack
        for i, dy in enumerate((3, 5, 7)):
            px, py = sx + i, y0 - dy
            if py >= 0 and (px, py) not in mask:
                g = 0xdd - i * 0x22
                _dot(out, pal, px, py, (g, g, g))
    return _shade("locomotive", R, extras, occlude=True)


def magic_carpet():
    weave = ramp3((0x88, 0x14, 0x14), (0xeb, 0x3c, 0x3c), (0xff, 0x7a, 0x62), 6)
    R = {"eb3c3c": (weave, 0.0), "ffd246": (_GOLD, 0.05), "2a50c0": (_BLUE, 0.1),
         "ffe044": (_GOLD, 0.1)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        if (cx, cy) in mask:
            _dot(out, pal, cx, cy, (0x99, 0xcc, 0xff))   # jewel-medallion glint
    return _shade("magic_carpet", R, extras, occlude=True)


def mushroom():
    cap = ramp3((0x88, 0x14, 0x14), (0xeb, 0x3c, 0x3c), (0xff, 0x7a, 0x5a), 6)
    stem = ramp3((0x8a, 0x7a, 0x55), (0xea, 0xdf, 0xc4), (0xff, 0xff, 0xf0), 6)
    grass = ramp3((0x0a, 0x2a, 0x10), (0x1c, 0x62, 0x28), (0x4a, 0xb0, 0x4a), 6)
    R = {"eb3c3c": (cap, 0.05), "eadfc4": (stem, 0.05),
         "1c6228": (grass, 0.0), "36b03e": (grass, 0.1), "ffffff": (_WHITE, 0.1)}
    return _shade("mushroom", R, occlude=True)


def old_car():
    body = ramp3((0x88, 0x14, 0x14), (0xeb, 0x3c, 0x3c), (0xff, 0x7a, 0x66), 6)
    chrome = ramp3((0x44, 0x4a, 0x5a), (0x9c, 0x9f, 0xb0), (0xee, 0xf2, 0xff), 6)
    tire = ramp((0x1e, 0x14, 0x0e), (0x5a, 0x3a, 0x2a), 4)
    R = {"eb3c3c": (body, 0.05), "9c9fb0": (chrome, 0.0), "4e2c12": (tire, 0.0),
         "2a50c0": (_BLUE, 0.0), "eadfc4": (_CREAM, 0.05), "ffd246": (_GOLD, 0.0)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        hx, hy = x1, int(y0 + (y1 - y0) * 0.55)         # headlamp glint at the front
        if (hx, hy) in mask:
            _dot(out, pal, hx, hy, (0xff, 0xff, 0xcc))
    return _shade("old_car", R, extras, occlude=True)


def pagoda():
    roof = ramp3((0x88, 0x14, 0x14), (0xeb, 0x3c, 0x3c), (0xff, 0x7a, 0x5a), 6)
    body = ramp3((0x8a, 0x7a, 0x55), (0xea, 0xdf, 0xc4), (0xff, 0xff, 0xf0), 6)
    R = {"eb3c3c": (roof, 0.05), "eadfc4": (body, 0.05), "2a50c0": (_BLUE, 0.0),
         "ffd246": (_GOLD, 0.1), "ffe044": (_GOLD, 0.15)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) // 2
        if (cx, y0) not in mask:
            _dot(out, pal, cx, y0, (0xff, 0xf0, 0x99))   # gold finial sparkle
    return _shade("pagoda", R, extras, occlude=True, light_fn=_vertical)


def pirates():
    sail = ramp3((0x88, 0x7a, 0x55), (0xea, 0xdf, 0xc4), (0xff, 0xff, 0xf0), 6)
    hull = ramp3((0x4a, 0x2a, 0x12), (0x9a, 0x5f, 0x2c), (0xd6, 0x96, 0x54), 6)
    R = {"eadfc4": (sail, 0.05), "1f6fd6": (_WATER, 0.0), "9a5f2c": (hull, 0.0),
         "4e2c12": (_DKWOOD, 0.0), "eb3c3c": (_RED, 0.1)}

    def extras(out, pal, mask, bbox):
        x0, y0, x1, y1 = bbox
        for fx in (0.25, 0.55, 0.8):                    # whitecaps on the waterline
            sx = int(x0 + (x1 - x0) * fx)
            if (sx, y1) in mask:
                _dot(out, pal, sx, y1, (0xcc, 0xf0, 0xff))
    return _shade("pirates", R, extras, occlude=True)


def snake():
    scale = ramp3((0x0e, 0x3a, 0x14), (0x36, 0xb0, 0x3e), (0x9a, 0xf0, 0x62), 6)
    R = {"36b03e": (scale, 0.0), "1c6228": (_DKGREEN, 0.0),
         "eb3c3c": (_RED, 0.1), "ffe044": (_GOLD, 0.2), "4e2c12": (_DKWOOD, 0.0)}
    return _shade("snake", R, occlude=True)


# ---- Universal hero icons ---------------------------------------------------------
# On this panel sky = LEDs off (black), so a pure-black fill is invisible. These lift
# "black" regions to a visible dark grey and give signature parts (goggle, glowing
# eyes) a brighter bias so they read at LED distance.
_INK = ramp((0x22, 0x22, 0x22), (0x66, 0x66, 0x66), 4)   # visible "black" (fur, rims)


def minion():
    body = ramp3((0xaa, 0x77, 0x11), (0xff, 0xe0, 0x44), (0xff, 0xf6, 0xaa), 6)
    R = {"ffe044": (body, 0.05), "2a50c0": (_BLUE, 0.0), "9c9fb0": (_STEEL, 0.0),
         "4c5060": (_DKSTEEL, 0.0), "111111": (_INK, 0.0), "ffffff": (_WHITE, 0.1),
         "9a5f2c": (_WOOD, 0.0)}
    return _shade("minion", R, occlude=True)


def panda():
    R = {"111111": (_INK, 0.1), "ffffff": (_WHITE, 0.05)}
    return _shade("panda", R, occlude=False)


def transformers():
    blue = ramp3((0x1e, 0x2a, 0x70), (0x2a, 0x50, 0xc0), (0x9a, 0xc0, 0xff), 6)
    eye = ramp((0x33, 0x88, 0xff), (0xcc, 0xf0, 0xff), 4)
    R = {"2a50c0": (blue, 0.0), "9c9fb0": (_STEEL, 0.0), "4c5060": (_DKSTEEL, 0.0),
         "1f6fd6": (eye, 0.4), "ffffff": (_WHITE, 0.1)}
    return _shade("transformers", R, occlude=True)


def rock_roller():
    # Rock 'n' Roller Coaster: a realistic Gibson Les Paul. The body ("R") is painted as a
    # cherry sunburst by a RADIAL light centred on the body — bright amber core falling to
    # a dark cherry edge — rather than the default top-left gradient. Everything off the
    # body (neck, headstock, hardware) sits at a neutral mid-light and is tuned by per-
    # material bias, so the burst does not drag the rest of the icon dark.
    burst = ramp3((0x2a, 0x0e, 0x06), (0xb0, 0x3a, 0x12), (0xff, 0xc6, 0x3e), 8)
    bcx, bcy, br = 45, 16, 15

    def sun(x, y, bbox):
        # elliptical falloff (body is wider than tall) so the burst darkens evenly all
        # round the edge; a hair under 1.0 at the core keeps the centre amber, not white.
        d = math.hypot((x - bcx) * 0.82, (y - bcy) * 1.05)
        return (0.92 - 0.86 * (d / br)) if d <= br else 0.5

    R = {"c05a2e": (burst, 0.0),          # sunburst maple top
         "eadfc4": (_CREAM, 0.12),        # cream binding + pickguard + inlays
         "4e2c12": (_DKWOOD, 0.05),       # rosewood fretboard
         "9c9fb0": (_STEEL, 0.10),        # frets, strings, tune-o-matic bridge
         "111111": (_INK, 0.0),           # humbuckers + headstock
         "ffd246": (_GOLD, 0.20)}         # tuners, top-hat knobs, pole pieces

    def extras(out, pal, mask, bbox):
        if (40, 10) in mask:
            _dot(out, pal, 40, 10, (0xff, 0xe4, 0x9a))   # soft gloss glint, off-centre
    return _shade("rock_roller", R, extras, occlude=True, light_fn=sun)


HEROES = {"minion": minion, "panda": panda, "transformers": transformers,
          "rock_roller": rock_roller,
          "space_mountain": space_mountain, "tron": tron,
          "everest": everest, "castle": castle, "big_thunder_goat": big_thunder_goat,
          "haunted_mansion": haunted_mansion, "skull": skull, "splash": splash,
          "seashell": seashell, "spaceship_earth": spaceship_earth, "wave": wave,
          "bird": bird, "canoe": canoe, "carousel_horse": carousel_horse, "child": child,
          "coaster_car": coaster_car, "dragon": dragon, "fairy": fairy, "fish": fish,
          "locomotive": locomotive, "magic_carpet": magic_carpet, "mushroom": mushroom,
          "old_car": old_car, "pagoda": pagoda, "pirates": pirates, "snake": snake}


def main():
    global DITHER
    want = sys.argv[1:]
    if "--no-dither" in want:
        DITHER = False
    want = [a for a in want if a not in ("--dither", "--no-dither")]
    if not want:
        want = sorted(os.path.splitext(os.path.basename(p))[0]
                      for p in glob.glob(os.path.join(ORIG_DIR, "*.bmp")))
    for name in want:
        if not os.path.exists(os.path.join(ORIG_DIR, name + ".bmp")):
            print("  (skip) no flat original: %s" % name)
            continue
        nc = HEROES[name]() if name in HEROES else generic(name)
        tag = "hero" if name in HEROES else "auto"
        print("  %-22s %-5s %2d colors" % (name, tag, nc))


if __name__ == "__main__":
    main()
