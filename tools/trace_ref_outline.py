"""Trace a reference image (line-art or photo) into a 64x32 ride-intro design.

Crops the subject out of a reference, downscales it to fit 64x32, thresholds the
dark outline, INVERTS it (so the line shows bright on the dark LED panel), then keeps
only the largest connected silhouette (drops stray sparkles / watermarks). Emits a
``designs/<name>.txt`` ASCII grid; feed it to ``tools/make_ride_image.py`` to build the BMP.

Two render modes:
  * ``--fill``    (default) solid silhouette: white interior + a 1px coloured outline.
  * ``--outline`` just the traced outline (interior left dark).

Used to match user-supplied references (e.g. the glass-slipper pump). Desktop-only.

    python tools/trace_ref_outline.py ref.jpg --name glass_slipper \
        --crop 180,175,590,480 --thresh 120 --edge '~'

Copyright (c) 2024-2026 Michael Czeiszperger
"""
import argparse
import os
from collections import deque

from PIL import Image

W, H = 64, 32
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "designs")


def _dilate(mask, nw, nh):
    d = [[False] * nw for _ in range(nh)]
    for y in range(nh):
        for x in range(nw):
            if mask[y][x]:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if 0 <= y + dy < nh and 0 <= x + dx < nw:
                            d[y + dy][x + dx] = True
    return d


def _largest_component(solid, nw, nh):
    comp = [[0] * nw for _ in range(nh)]
    cid, sizes = 0, {}
    for y0 in range(nh):
        for x0 in range(nw):
            if solid[y0][x0] and comp[y0][x0] == 0:
                cid += 1; sz = 0; st = [(x0, y0)]; comp[y0][x0] = cid
                while st:
                    cx, cy = st.pop(); sz += 1
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < nw and 0 <= ny < nh and solid[ny][nx] and comp[ny][nx] == 0:
                            comp[ny][nx] = cid; st.append((nx, ny))
                sizes[cid] = sz
    if not sizes:
        return solid
    best = max(sizes, key=sizes.get)
    return [[comp[y][x] == best for x in range(nw)] for y in range(nh)]


def trace(ref, crop, thresh, fill_mode, fill_ch, edge_ch):
    im = Image.open(ref).convert("L")
    if crop:
        im = im.crop(crop)
    cw, ch = im.size
    scale = min((W - 2) / cw, (H - 2) / ch)
    nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
    px = im.resize((nw, nh), Image.LANCZOS).load()
    mask = [[px[x, y] < thresh for x in range(nw)] for y in range(nh)]

    grid = [[" "] * W for _ in range(H)]
    ox, oy = (W - nw) // 2, (H - nh) // 2
    if not fill_mode:                               # just the traced outline
        for y in range(nh):
            for x in range(nw):
                if mask[y][x]:
                    grid[oy + y][ox + x] = edge_ch
        return grid, nw, nh

    md = _dilate(mask, nw, nh)                       # close hairline gaps for the flood fill
    ext = [[False] * nw for _ in range(nh)]
    q = deque()
    for x in range(nw):
        for y in (0, nh - 1):
            if not md[y][x] and not ext[y][x]:
                ext[y][x] = True; q.append((x, y))
    for y in range(nh):
        for x in (0, nw - 1):
            if not md[y][x] and not ext[y][x]:
                ext[y][x] = True; q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < nw and 0 <= ny < nh and not ext[ny][nx] and not md[ny][nx]:
                ext[ny][nx] = True; q.append((nx, ny))
    solid = _largest_component([[not ext[y][x] for x in range(nw)] for y in range(nh)], nw, nh)
    for y in range(nh):
        for x in range(nw):
            if solid[y][x]:
                edge = any(not (0 <= x + dx < nw and 0 <= y + dy < nh) or not solid[y + dy][x + dx]
                           for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                grid[oy + y][ox + x] = edge_ch if edge else fill_ch
    return grid, nw, nh


def main():
    ap = argparse.ArgumentParser(description="Trace a reference image into a 64x32 ride design.")
    ap.add_argument("ref", help="reference image (jpg/png)")
    ap.add_argument("--name", required=True, help="output basename -> designs/<name>.txt")
    ap.add_argument("--crop", help="left,top,right,bottom px crop of the subject")
    ap.add_argument("--thresh", type=int, default=120, help="dark-outline threshold 0-255")
    ap.add_argument("--fill", dest="fill", action="store_true", default=True,
                    help="solid silhouette (default)")
    ap.add_argument("--outline", dest="fill", action="store_false", help="outline only")
    ap.add_argument("--fill-ch", default="#", help="interior char (default '#': white)")
    ap.add_argument("--edge", default="~", help="outline char (default '~': blue)")
    args = ap.parse_args()

    crop = tuple(int(v) for v in args.crop.split(",")) if args.crop else None
    grid, nw, nh = trace(args.ref, crop, args.thresh, args.fill, args.fill_ch, args.edge)
    out = os.path.join(OUT_DIR, args.name + ".txt")
    with open(out, "w") as f:
        for row in grid:
            f.write("".join(row).rstrip() + "\n")
    print("wrote %s  (%s, traced %dx%d)" % (out, "fill" if args.fill else "outline", nw, nh))


if __name__ == "__main__":
    main()
