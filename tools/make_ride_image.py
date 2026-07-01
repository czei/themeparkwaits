"""Convert a ride-intro design into a device-ready indexed BMP (desktop dev tool).

The app shows an optional 64x32 silhouette before a ride's wait time (see
``src/ui/ride_images.py`` + ``RideScreenContent``). This tool turns a hand-drawn
ASCII-art grid (32 lines x 64 chars, one char per LED) — or a 64x32 PNG — into the
exact on-device format:

  * 64x32, **indexed** BMP (Pillow "P" mode), up to 256 palette colors (the 8-bit
    indexed-BMP ceiling). The panel renders bit_depth=4 (4096 colors = 16 levels per
    channel), so author 4-bit-clean shades (multiples of 0x11) for what-you-see == the
    device; ~16-32 well-chosen shades is the practical sweet spot for a 64x32 icon;
  * palette **index 0 = sky**, and the **top-left pixel is sky**, so
    ``palette.make_transparent(0)`` means "sky" on BOTH the device (reads the BMP's
    indexed palette) and the simulator (rebuilds the palette by top-left-first scan).

It writes the BMP into ``src/images/rides/``, saves an LED-dot preview PNG, and
prints the ``manifest.json`` line(s) to add for the given ride UUID(s).

This is desktop-only (like tools/sim_shot.py / classify_rides.py) — never bundled to
the board; only the emitted BMP + manifest ship.

Usage:
    # from an ASCII grid, mapping it to Magic Kingdom's Space Mountain UUID
    python tools/make_ride_image.py design.txt --name space_mountain --uuid <uuid>[,<uuid>...]
    # from a 64x32 PNG (quantized to <=16 colors; top-left pixel becomes sky)
    python tools/make_ride_image.py art.png --name space_mountain --uuid <uuid>

Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""
import argparse
import os

from PIL import Image, ImageDraw

W, H = 64, 32
# Palette ceiling = the 8-bit indexed-BMP limit (NOT a hardware limit). The device's
# OnDiskBitmap + the RideScreenContent palette-fade are palette-size-agnostic, and the
# bit_depth=4 panel shows 4096 colors — so there is no reason to starve an icon of
# shades. Author 4-bit-clean colors; ~16-32 per icon reads richly at 64x32.
MAX_COLORS = 256
SKY = " "

# char -> RGB. ' ' (sky) is forced to palette index 0 and made transparent on device.
# Matches the approved "variant 1" look (white structure, blue rib-fins, dim stars).
# Each image may use AT MOST 16 of these (bit_depth=4); the master map can be larger.
PALETTE = {
    " ": (0, 0, 0),          # sky (index 0; transparent on device — color is irrelevant)
    "#": (255, 255, 255),    # bright white structure
    "|": (255, 255, 255),    # edge highlight
    ":": (0x2A, 0x50, 0xC0), # rib / shade (blue)
    ".": (0x46, 0x56, 0x8C), # deep shade
    "=": (0x40, 0x4E, 0x80), # ground
    "*": (0xCD, 0xD0, 0xE1), # bright star
    "+": (0x18, 0x28, 0x60), # faint star
    "o": (255, 0xD2, 0x46),  # warm accent (gold)
    "r": (0xEB, 0x3C, 0x3C), # red accent
    # NB: this char->color map is only for the simple ASCII-grid path; richly-shaded
    # icons use full ramps via gen_rich_icons.py / the PNG path, not these chars.
    # --- extended palette for the broader ride set (added 2026-06-28) ---
    "w": (0xEA, 0xDF, 0xC4), # warm cream / sailcloth / fur
    "n": (0x9A, 0x5F, 0x2C), # wood / hull brown
    "N": (0x4E, 0x2C, 0x12), # dark brown (mast, shadow)
    "g": (0x36, 0xB0, 0x3E), # foliage green
    "G": (0x1C, 0x62, 0x28), # dark green
    "~": (0x1F, 0x6F, 0xD6), # water blue
    "s": (0x9C, 0x9F, 0xB0), # stone / snow-grey
    "S": (0x4C, 0x50, 0x60), # dark grey
    "R": (0xC0, 0x5A, 0x2E), # rust-red rock (Big Thunder / Everest)
    "y": (0xFF, 0xE0, 0x44), # bright yellow
    # --- extended palette for the Universal batch (added 2026-07-01) ---
    "K": (0x11, 0x11, 0x11), # near-black outline / detail (minion goggle, panda, shark eye)
    "p": (0xFF, 0x88, 0xBB), # pink (Simpsons donut frosting)
    "O": (0xFF, 0x88, 0x22), # orange (Yoshi boots, accents)
    "T": (0xCC, 0xAA, 0x66), # sandstone tan (Mesoamerican pyramid stone)
}

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "src", "images", "rides")


def _from_ascii(path):
    """Indexed image from a 32x64 ASCII grid (sky=index 0, top-left must be sky)."""
    with open(path) as f:
        lines = [ln.rstrip("\n") for ln in f]
    colors = [PALETTE[SKY]]           # index 0 = sky, always first
    idx_of = {PALETTE[SKY]: 0}
    grid = []
    for y in range(H):
        row = lines[y] if y < len(lines) else ""
        out = []
        for x in range(W):
            ch = row[x] if x < len(row) else SKY
            rgb = PALETTE.get(ch, PALETTE[SKY])
            if rgb not in idx_of:
                idx_of[rgb] = len(colors)
                colors.append(rgb)
            out.append(idx_of[rgb])
        grid.append(out)
    return _build(grid, colors)


def _from_png(path):
    """Indexed image from a PNG: quantize to <=16 colors; top-left color -> sky (idx 0)."""
    img = Image.open(path).convert("RGB").resize((W, H))
    q = img.quantize(colors=MAX_COLORS)          # P-mode, <=16 colors
    pal = q.getpalette()
    qpix = list(q.getdata())
    top_left = qpix[0]
    # remap so the top-left palette index becomes 0 (sky)
    order = [top_left] + [i for i in range(MAX_COLORS) if i != top_left]
    remap = {old: new for new, old in enumerate(order)}
    colors = [(pal[3 * o], pal[3 * o + 1], pal[3 * o + 2]) for o in order]
    grid = [[remap[qpix[y * W + x]] for x in range(W)] for y in range(H)]
    return _build(grid, colors)


def _build(grid, colors):
    if len(colors) > MAX_COLORS:
        raise SystemExit("too many colors: %d (max %d, the 8-bit indexed-BMP ceiling) "
                         "— merge near-identical shades" % (len(colors), MAX_COLORS))
    # Pillow encodes a <=2-color P image as a 1-bit BMP, which is not the indexed
    # format the device reads (and fails the P-mode round-trip). Pad with unused
    # palette slots so the encoder emits a 4-bit indexed BMP; sky stays index 0.
    while len(colors) < 3:
        colors.append((1, 1, 1))
    if grid[0][0] != 0:
        raise SystemExit("top-left pixel must be sky (index 0) so make_transparent(0) "
                         "is correct in the simulator — make row 0 / the corners sky")
    img = Image.new("P", (W, H), 0)
    flat = []
    for rgb in colors:
        flat += list(rgb)
    img.putpalette(flat)
    for y in range(H):
        for x in range(W):
            img.putpixel((x, y), grid[y][x])
    return img, colors


def _save_preview(img, colors, path, scale=12):
    """LED-dot preview PNG (sky drawn as near-black so the panel look reads)."""
    big = Image.new("RGB", (W * scale, H * scale), (0, 0, 0))
    d = ImageDraw.Draw(big)
    px = img.load()
    r = scale * 0.82 / 2
    for y in range(H):
        for x in range(W):
            idx = px[x, y]
            col = (3, 6, 18) if idx == 0 else colors[idx]
            cx, cy = x * scale + scale / 2, y * scale + scale / 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    big.save(path)


def main():
    ap = argparse.ArgumentParser(description="Make a 64x32 indexed transparent ride-intro BMP.")
    ap.add_argument("design", help="input .txt ASCII grid or .png image")
    ap.add_argument("--name", help="output basename (default: from the design filename)")
    ap.add_argument("--uuid", default="", help="comma-separated ride UUID(s) for the manifest line")
    ap.add_argument("--out-dir", default=OUT_DIR, help="output dir (default src/images/rides)")
    args = ap.parse_args()

    name = args.name or os.path.splitext(os.path.basename(args.design))[0]
    fname = name + ".bmp"
    os.makedirs(args.out_dir, exist_ok=True)
    bmp_path = os.path.join(args.out_dir, fname)

    if args.design.lower().endswith(".png"):
        img, colors = _from_png(args.design)
    else:
        img, colors = _from_ascii(args.design)

    img.save(bmp_path)                     # Pillow "P" mode -> indexed BMP
    # Preview goes next to the DESIGN (outside src/) so it never ships to the device.
    preview = os.path.splitext(args.design)[0] + ".preview.png"
    _save_preview(img, colors, preview)

    # verify it reloads as an indexed image of the right size with sky at index 0
    chk = Image.open(bmp_path)
    assert chk.size == (W, H) and chk.mode == "P", "BMP did not round-trip as 64x32 P-mode"

    print("wrote %s  (%d colors, %dx%d, sky=index 0)" % (bmp_path, len(colors), W, H))
    print("preview %s" % preview)
    uuids = [u.strip() for u in args.uuid.split(",") if u.strip()]
    if uuids:
        print("\nAdd to src/images/rides/manifest.json under \"rides\":")
        for u in uuids:
            print('    "%s": "%s",' % (u, fname))


if __name__ == "__main__":
    main()
