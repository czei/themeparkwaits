"""Programmatic generator for the ride-intro ASCII designs (64x32) — desktop dev tool.

Draws clean shapes into a char grid via primitives, then writes ``designs/<name>.txt``
for every ride icon. This is the reproducible source for the designs/*.txt files; after
editing a shape, re-run this then ``tools/make_ride_image.py`` to rebuild the BMP.
Row 0 / top-left stays sky (' ') per the BMP sky=index-0 rule.

    python tools/gen_ride_designs.py      # regenerate every designs/*.txt

Copyright (c) 2024-2026 Michael Czeiszperger
"""
import math
import os

W, H = 64, 32
# tools/ lives directly under the repo root; designs/ is a sibling of tools/.
DESIGNS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "designs")


def grid():
    return [[" "] * W for _ in range(H)]


def put(g, x, y, ch):
    if 0 <= x < W and 0 <= y < H:
        g[y][x] = ch


def hline(g, x0, x1, y, ch):
    for x in range(min(x0, x1), max(x0, x1) + 1):
        put(g, x, y, ch)


def vline(g, x, y0, y1, ch):
    for y in range(min(y0, y1), max(y0, y1) + 1):
        put(g, x, y, ch)


def rect(g, x0, y0, x1, y1, ch):
    for y in range(min(y0, y1), max(y0, y1) + 1):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            put(g, x, y, ch)


def line(g, x0, y0, x1, y1, ch):
    dx = abs(x1 - x0); dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1; sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        put(g, x0, y0, ch)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy


def thick_line(g, x0, y0, x1, y1, ch, width):
    dx, dy = x1 - x0, y1 - y0
    L = max(math.hypot(dx, dy), 0.001)
    px, py = -dy / L, dx / L
    r = (width - 1) / 2.0
    w = -r
    while w <= r + 1e-6:
        line(g, x0 + round(px * w), y0 + round(py * w),
             x1 + round(px * w), y1 + round(py * w), ch)
        w += 0.7


def ring(g, cx, cy, r, ch, cond=None):
    for a in range(0, 360, 5):
        x = cx + round(r * math.cos(math.radians(a)))
        y = cy + round(r * math.sin(math.radians(a)))
        if cond is None or cond(x, y):
            put(g, x, y, ch)


def ellipse(g, cx, cy, rx, ry, ch, half=None):
    """Fill an ellipse. half=None all, 'top' upper, 'bottom' lower."""
    for y in range(H):
        for x in range(W):
            if half == "top" and y > cy:
                continue
            if half == "bottom" and y < cy:
                continue
            dx = (x - cx) / max(rx, 0.5); dy = (y - cy) / max(ry, 0.5)
            if dx * dx + dy * dy <= 1.0:
                put(g, x, y, ch)


def fill_tri(g, p0, p1, p2, ch):
    """Fill the triangle p0-p1-p2 (each an (x, y) tuple) with ch."""
    pts = (p0, p1, p2)
    minx = max(0, min(p[0] for p in pts)); maxx = min(W - 1, max(p[0] for p in pts))
    miny = max(0, min(p[1] for p in pts)); maxy = min(H - 1, max(p[1] for p in pts))

    def edge(a, b, c):
        return (a[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (a[1] - c[1])

    for y in range(miny, maxy + 1):
        for x in range(minx, maxx + 1):
            p = (x, y)
            d1, d2, d3 = edge(p, p0, p1), edge(p, p1, p2), edge(p, p2, p0)
            neg = d1 < 0 or d2 < 0 or d3 < 0
            pos = d1 > 0 or d2 > 0 or d3 > 0
            if not (neg and pos):
                put(g, x, y, ch)


def write(name, g):
    path = os.path.join(DESIGNS, name + ".txt")
    with open(path, "w") as f:
        for row in g:
            f.write("".join(row).rstrip() + "\n")
    print("wrote", path)


def write_sheet(name, grids):
    """Compose N char-grids (each 64x32) side by side into ONE indexed strip BMP at
    src/images/rides/<name>.bmp — a cel spritesheet for CelWalkAnimator's tile-indexed
    TileGrid. All tiles share one palette (sky=index 0, so make_transparent(0) is correct on
    both device and simulator); the global top-left pixel is sky by the row-0-blank rule.
    Reuses make_ride_image's char->RGB PALETTE so the look matches the flat design path."""
    from PIL import Image
    import make_ride_image as mri            # sibling in tools/ (on sys.path when run as a script)

    sky = mri.PALETTE[mri.SKY]
    colors = [sky]
    idx_of = {sky: 0}
    n = len(grids)
    img = Image.new("P", (W * n, H), 0)
    for ti, g in enumerate(grids):
        for y in range(H):
            row = g[y]
            for x in range(W):
                rgb = mri.PALETTE.get(row[x], sky)
                if rgb not in idx_of:
                    idx_of[rgb] = len(colors)
                    colors.append(rgb)
                img.putpixel((ti * W + x, y), idx_of[rgb])
    while len(colors) < 3:                    # avoid a 1-bit BMP (see make_ride_image._build)
        colors.append((1, 1, 1))
    flat = []
    for rgb in colors:
        flat += list(rgb)
    img.putpalette(flat)
    out = os.path.join(mri.OUT_DIR, name + ".bmp")
    img.save(out)
    print("wrote %s (%dx%d, %d tiles, %d colors)" % (out, W * n, H, n, len(colors)))


# ---------------------------------------------------------------- GHOST
def ghost():
    g = grid()
    cx = 32
    # classic draped-sheet ghost: small rounded head, body billowing wider, raised
    # "boo" arms, a flowing tattered hem, big eyes + an open wailing mouth.
    ellipse(g, cx, 12, 9, 9, "#", half="top")
    for y in range(12, 24):
        t = (y - 12) / 11.0
        hw = int(9 + 3 * t)                        # sheet billows out lower down
        hline(g, cx - hw, cx + hw, y, "#")
    # raised sheet arms
    ellipse(g, cx - 12, 15, 3, 4, "#")
    ellipse(g, cx + 12, 15, 3, 4, "#")
    # flowing tattered hem: pointed wisps of varying length (sky gaps between)
    base = 23
    for wx, ln in ((cx - 10, 4), (cx - 6, 2), (cx - 2, 5), (cx + 3, 2), (cx + 7, 5), (cx + 11, 3)):
        for dy in range(ln + 1):
            w = max(0, 2 - dy)
            hline(g, wx - w, wx + w, base + dy, "#")
    # big friendly eyes + a tall open "Boooo" mouth (carved sky)
    ellipse(g, cx - 5, 11, 2, 3, " ")
    ellipse(g, cx + 5, 11, 2, 3, " ")
    ellipse(g, cx, 17, 2, 4, " ")
    write("haunted_mansion", g)


# ---------------------------------------------------------------- PIRATE SHIP
def pirate_ship():
    g = grid()
    # water
    for y in (28, 29, 30):
        for x in range(W):
            if (x + y) % 6 != 0:
                put(g, x, y, "~")
    # hull (brown trapezoid, pointed bow to the right)
    for y in range(23, 28):
        t = (y - 23) / 4.0
        x0 = int(10 + 9 * t)
        x1 = int(54 + 4 * t)          # bow extends right as it rises? keep simple
        hline(g, x0, min(x1, 56), y, "n")
    hline(g, 10, 54, 23, "w")          # deck rail highlight
    # waterline shadow
    hline(g, 19, 52, 27, "N")
    # bowsprit
    line(g, 54, 24, 61, 21, "n")
    # two masts
    for mx in (25, 41):
        vline(g, mx, 6, 23, "N")
    # square sails, billowing to the right (wind from left)
    def sail(mx, yt, yb, bulge):
        for y in range(yt, yb + 1):
            t = (y - yt) / max(yb - yt, 1)
            edge = mx + int(bulge * (0.5 + 0.5 * math.sin(math.pi * t)))
            hline(g, mx + 1, edge, y, "w")
    sail(25, 8, 13, 12)
    sail(25, 15, 20, 12)
    sail(41, 9, 14, 11)
    sail(41, 16, 21, 11)
    # flag at main masthead
    line(g, 25, 6, 31, 5, "r")
    line(g, 25, 7, 30, 7, "r")
    put(g, 25, 5, "N")
    write("pirates", g)


# ---------------------------------------------------------------- JUNGLE CRUISE BOAT
def jungle_cruise():
    g = grid()
    # water
    for y in (26, 27, 28, 29):
        for x in range(W):
            if (x + y) % 5 != 0:
                put(g, x, y, "~")
    # hull (brown), pointed bow right
    for y in range(21, 25):
        t = (y - 21) / 3.0
        x0 = int(13 + 6 * t)
        x1 = int(52 - 2 * t)
        hline(g, x0, x1, y, "n")
    hline(g, 13, 52, 20, "N")          # gunwale
    # corner poles
    vline(g, 17, 11, 20, "N")
    vline(g, 47, 11, 20, "N")
    # smokestack + puff
    vline(g, 39, 5, 9, "S")
    ellipse(g, 37, 4, 3, 2, "s")
    # striped canopy roof
    for x in range(15, 50):
        ch = "r" if (x // 3) % 2 == 0 else "w"
        put(g, x, 9, ch)
        put(g, x, 10, ch)
    hline(g, 15, 49, 8, "w")            # roof crown
    # scalloped fringe under the canopy
    for x in range(16, 49):
        if x % 3 == 1:
            put(g, x, 11, "w")
    write("jungle_cruise", g)


# ---------------------------------------------------------------- GOAT (Big Thunder, refined)
def goat():
    g = grid()
    # grassy/rock ledge the goat stands on
    ellipse(g, 32, 30, 28, 5, "s")
    rect(g, 4, 29, 60, 31, "s")
    # body (cream), chunky
    ellipse(g, 34, 17, 10, 5, "w")
    rect(g, 26, 15, 42, 20, "w")
    # rump/tail
    line(g, 44, 14, 46, 12, "w")
    # neck rising to the head on the left
    for y in range(12, 20):
        x0 = 20 + (y - 12)
        hline(g, x0, x0 + 3, y, "w")
    # head + muzzle (pointing left)
    ellipse(g, 19, 13, 4, 3, "w")
    rect(g, 13, 13, 18, 15, "w")        # muzzle
    # beard hanging under the chin
    vline(g, 14, 15, 19, "w")
    put(g, 15, 18, "w"); put(g, 13, 17, "w")
    # one bold backward-curving horn (thick)
    line(g, 21, 10, 26, 9, "w"); line(g, 22, 11, 27, 10, "w")
    line(g, 26, 9, 28, 12, "w"); line(g, 27, 10, 29, 13, "w")
    # ear
    line(g, 20, 11, 22, 13, "w")
    # legs (front pair forward, back pair back)
    for lx in (27, 31, 38, 42):
        vline(g, lx, 21, 28, "w")
    # little hooves
    for lx in (27, 31, 38, 42):
        put(g, lx, 28, "N")
    # stick of dynamite clenched in the mouth, pointing forward (left).
    # Drawn last so it sits on top of the muzzle; the free (left) end carries
    # a lit fuse. Kept within cols 3-12 so the head-nod hinge box encloses it.
    rect(g, 6, 14, 12, 15, "r")               # red cylinder at the mouth line
    put(g, 5, 13, "O"); put(g, 4, 12, "O")    # short orange wick off the tip
    put(g, 4, 11, "y"); put(g, 3, 11, "y")    # bright yellow spark
    put(g, 3, 10, "O")                        # ember flick
    write("big_thunder_goat", g)


# ---------------------------------------------------------------- RED-ROCK MESA (Big Thunder alt)
def mesa():
    g = grid()
    def butte(x0, x1, top, base):
        # rust body with darker strata + a shadowed right face + sunlit left face
        rect(g, x0, top, x1, base, "R")
        for y in range(top, base + 1):
            put(g, x1, y, "N"); put(g, x1 - 1, y, "N")   # shadow face
            put(g, x0, y, "o")                            # sunlit edge
        for y in range(top + 3, base, 4):                # strata lines
            hline(g, x0, x1, y, "N")
        hline(g, x0, x1, top, "o")                        # bright cap
    # three buttes of different heights (classic Monument-Valley read)
    butte(8, 20, 15, 28)
    butte(24, 41, 7, 28)
    butte(45, 57, 12, 28)
    # desert floor
    rect(g, 0, 29, 63, 31, "N")
    hline(g, 0, 63, 29, "R")
    write("big_thunder_mesa", g)


# ================================================================ BATCH 2
# ---------------------------------------------------------------- TEA CUP
def tea_cup():
    g = grid()
    cx = 32
    # steam curls
    for sx, ph in ((28, 0), (36, 1)):
        for y in range(2, 10):
            x = sx + int(2 * math.sin((y + ph * 3) / 1.6))
            put(g, x, y, "w")
    # cup body (trapezoid, wider at top)
    for y in range(12, 23):
        t = (y - 12) / 10.0
        hw = int(12 - 6 * t)
        hline(g, cx - hw, cx + hw, y, "#")
    hline(g, cx - 12, cx + 12, 12, "r")   # rim
    hline(g, cx - 12, cx + 12, 13, "r")
    hline(g, cx - 9, cx + 9, 17, ":")     # stripe
    # handle (right-side C)
    ring(g, cx + 12, 17, 4, "#", cond=lambda x, y: x >= cx + 12)
    ring(g, cx + 12, 17, 3, "#", cond=lambda x, y: x >= cx + 12)
    # saucer
    ellipse(g, cx, 25, 17, 2, "#")
    ellipse(g, cx, 26, 12, 1, ":")
    write("tea_cup", g)


# ---------------------------------------------------------------- HONEY POT
def honey_pot():
    g = grid()
    cx = 32
    # pot body with a FLAT base (acorn/trophy taper at the bottom -> the acorn read);
    # gentle bulge in the middle.
    for y in range(14, 27):
        t = abs(y - 20) / 7.0
        hw = int(10 - 3 * t * t)
        hline(g, cx - hw, cx + hw, y, "o")
    rect(g, cx - 8, 26, cx + 8, 27, "o")          # flat base
    hline(g, cx - 8, cx + 8, 26, "n")             # base contour
    # WIDE overhanging lip (a pot's rim is wider than the body -> not an acorn cap)
    rect(g, cx - 12, 11, cx + 12, 13, "n")
    ellipse(g, cx, 12, 9, 1, "N")                 # dark open mouth
    # dark cursive "hunny" squiggle straight on the amber (no white band -> no burger)
    for sx in range(cx - 6, cx + 7):
        put(g, sx, 19 + (1 if (sx // 2) % 2 else 0), "N")
    # wooden honey dipper + thread
    vline(g, cx + 4, 3, 12, "n")
    ellipse(g, cx + 4, 4, 2, 2, "o")
    line(g, cx + 4, 5, cx + 6, 8, "y")
    # drips spilling over the rim
    for dx, dl in ((cx - 7, 3), (cx - 1, 5), (cx + 8, 2)):
        vline(g, dx, 13, 13 + dl, "y")
    # a little bee above
    ellipse(g, cx - 12, 7, 2, 2, "y")
    put(g, cx - 12, 7, "N")
    line(g, cx - 14, 5, cx - 12, 6, "w")
    write("honey_pot", g)


# ---------------------------------------------------------------- CAROUSEL HORSE
def carousel_horse():
    g = grid()
    # brass pole the horse is mounted on
    vline(g, 33, 2, 30, "o")
    vline(g, 34, 2, 30, "o")
    # barrel/body (cream)
    ellipse(g, 33, 16, 11, 6, "w")
    # arched neck rising to the head (upper-left)
    for i in range(9):
        y = 16 - i
        x0 = 24 - i // 2
        hline(g, x0, x0 + 4, y, "w")
    ellipse(g, 20, 7, 3, 3, "w")                  # head
    line(g, 13, 9, 19, 8, "w"); line(g, 13, 10, 19, 9, "w")   # muzzle
    line(g, 21, 3, 22, 6, "w")                    # ear
    # flowing mane (blue) down the neck + forelock
    for i in range(9):
        put(g, 26 - i // 2, 16 - i, ":")
    line(g, 19, 4, 21, 8, ":")
    # saddle
    rect(g, 29, 11, 38, 13, "r")
    # galloping legs: front pair reaching forward, back pair kicking back
    line(g, 28, 21, 23, 29, "w"); line(g, 31, 21, 27, 29, "w")
    line(g, 38, 21, 43, 29, "w"); line(g, 41, 21, 46, 28, "w")
    # tail streaming down-right
    line(g, 44, 14, 49, 27, ":"); line(g, 45, 15, 50, 26, ":")
    write("carousel_horse", g)


# ---------------------------------------------------------------- BEAR (face)
def bear():
    g = grid()
    cx = 32
    # ears
    ellipse(g, cx - 11, 8, 5, 5, "n")
    ellipse(g, cx + 11, 8, 5, 5, "n")
    ellipse(g, cx - 11, 8, 2, 2, "N")
    ellipse(g, cx + 11, 8, 2, 2, "N")
    # head
    ellipse(g, cx, 18, 14, 11, "n")
    # muzzle
    ellipse(g, cx, 22, 7, 5, "w")
    # nose
    ellipse(g, cx, 20, 2, 2, "N")
    # eyes
    ellipse(g, cx - 6, 15, 1, 2, "N")
    ellipse(g, cx + 6, 15, 1, 2, "N")
    write("bear", g)


# ---------------------------------------------------------------- LASER BLASTER (Buzz)
def laser_blaster():
    g = grid()
    # ray-gun pointing right — COMPACT and CENTERED; no drawn bolt (the intro's
    # emitter fires the beam, so painting one both elongated and double-drew it).
    rect(g, 20, 13, 38, 19, "g")          # body
    rect(g, 38, 14, 46, 17, "w")          # barrel
    rect(g, 20, 13, 38, 14, "w")          # top highlight
    line(g, 24, 12, 29, 8, "g"); line(g, 25, 12, 30, 8, "g")
    rect(g, 26, 8, 31, 10, "G")           # sight fin
    rect(g, 22, 19, 28, 27, "G")          # grip
    put(g, 46, 15, "y"); put(g, 46, 16, "y")   # muzzle glow
    write("laser_blaster", g)


# ---------------------------------------------------------------- TIKI BIRD (toucan)
def tiki_bird():
    g = grid()
    # perch branch
    rect(g, 6, 27, 58, 29, "G")
    vline(g, 40, 22, 27, "G")
    # body (dark) on the perch
    ellipse(g, 34, 18, 9, 8, "S")
    # white chest
    ellipse(g, 30, 20, 5, 5, "w")
    # head
    ellipse(g, 26, 11, 5, 5, "S")
    # big toucan beak (yellow/orange) pointing left
    line(g, 22, 10, 10, 12, "o"); line(g, 22, 12, 11, 13, "o")
    rect(g, 11, 11, 22, 13, "o"); rect(g, 12, 12, 20, 13, "r")
    # eye
    put(g, 26, 10, "y"); put(g, 26, 10, "y")
    ellipse(g, 26, 10, 1, 1, "w")
    # tail
    line(g, 42, 16, 47, 12, "S"); line(g, 43, 18, 48, 15, "S")
    # legs
    vline(g, 32, 25, 27, "o"); vline(g, 36, 25, 27, "o")
    write("tiki_bird", g)


# ---------------------------------------------------------------- TURTLE (Crush)
def turtle():
    # side-profile swimming sea turtle (Crush), head to the right. Per art-direction:
    # domed shell + cream belly band for value separation, big swept front flipper drawn
    # OVER the belly, enlarged head w/ catch-light eye, negative space under the flipper.
    g = grid()
    # cream belly band (laid down first; the green flipper crosses it for edge separation)
    rect(g, 15, 19, 46, 23, "w")
    # neck + enlarged head (right) with a blunt beak
    rect(g, 43, 12, 50, 19, "g")
    ellipse(g, 54, 14, 6, 5, "g")
    put(g, 60, 13, "g"); put(g, 60, 14, "g"); put(g, 61, 14, "g")     # beak
    # rear flipper (left/back) — small paddle
    fill_tri(g, (16, 19), (4, 26), (17, 25), "g")
    # front flipper — massive, swept down-left over the belly (leaves top row of belly cream)
    fill_tri(g, (45, 20), (45, 26), (19, 31), "g")
    fill_tri(g, (45, 23), (31, 25), (19, 31), "g")
    # domed carapace (mid green) on top
    ellipse(g, 30, 18, 17, 13, "g", half="top")
    # dark shadow under the shell overhang (separates shell from belly)
    hline(g, 14, 46, 18, "G")
    # scute seams (dark green) + light-green bevel highlights (no black lines)
    hline(g, 16, 44, 12, "G")
    for sx in (23, 30, 37):
        vline(g, sx, 6, 17, "G")
    for hx, hy in ((19, 9), (26, 8), (33, 8), (40, 9), (19, 15), (26, 14), (33, 14), (40, 15)):
        put(g, hx, hy, "L")
    # eye (dark block + white catch-light) + mouth line
    rect(g, 54, 12, 56, 14, "N"); put(g, 56, 12, "#")
    hline(g, 58, 61, 16, "G")
    write("turtle", g)


# ---------------------------------------------------------------- SEASHELL (scallop)
def seashell():
    g = grid()
    cx, baseY, R = 32, 26, 19
    # ORIGINAL scallop fan (the version approved in batch 2): a ~150-degree wedge of a
    # disk centred on the hinge at the bottom -> rounded outer edge, ribs radiating up.
    # AI blind-tests overthink it ("fan/peacock"), but a person reads it as a shell.
    for y in range(baseY - R, baseY + 1):
        for x in range(cx - R, cx + R + 1):
            dx = x - cx; dy = baseY - y
            if dy < 0:
                continue
            if math.hypot(dx, dy) <= R and abs(math.degrees(math.atan2(dx, dy))) <= 76:
                put(g, x, y, "w")
    # ribs radiating from the hinge (gold)
    for a in range(-70, 71, 14):
        x2 = cx + int(R * math.sin(math.radians(a)))
        y2 = baseY - int(R * math.cos(math.radians(a)))
        line(g, cx, baseY, x2, y2, "o")
    # scalloped rim: carve a notch at the tip of each rib so the top edge waves
    for a in range(-63, 64, 14):
        x2 = cx + int(R * math.sin(math.radians(a)))
        y2 = baseY - int(R * math.cos(math.radians(a)))
        put(g, x2, y2, " ")
    # hinge knob at the base
    ellipse(g, cx, baseY, 3, 2, "o")
    write("seashell", g)


# ================================================================ BATCH 3
# ---------------------------------------------------------------- RACE CAR
def race_car():
    g = grid()
    # speed lines trailing left
    for y in (16, 19, 22):
        hline(g, 2, 11, y, "s")
    # low sleek body (red), nose to the right
    rect(g, 13, 17, 49, 22, "r")
    line(g, 49, 17, 57, 20, "r"); rect(g, 49, 18, 56, 22, "r"); line(g, 49, 22, 57, 20, "r")
    # low raked cockpit canopy (a short sleek bump, not a tall truck cab)
    rect(g, 28, 15, 37, 17, "r")
    line(g, 26, 17, 29, 15, "r")             # raked windscreen post
    line(g, 37, 15, 40, 17, "r")             # rear-deck slope
    rect(g, 30, 15, 35, 16, ":")             # windscreen glass
    ellipse(g, 32, 15, 1, 1, "w")            # driver helmet
    # tall rear wing (left) -> the clearest "race car" tell
    rect(g, 9, 11, 17, 12, "r"); rect(g, 11, 12, 15, 17, "r")
    vline(g, 9, 11, 14, "r"); vline(g, 17, 11, 14, "r")
    # racing roundel
    ellipse(g, 21, 19, 3, 3, "w"); put(g, 21, 19, "N")
    # wheels (black tyre + grey hub)
    ellipse(g, 23, 23, 4, 4, "N"); ellipse(g, 44, 23, 4, 4, "N")
    ellipse(g, 23, 23, 2, 2, "s"); ellipse(g, 44, 23, 2, 2, "s")
    write("race_car", g)


# ---------------------------------------------------------------- LOCOMOTIVE
def locomotive():
    g = grid()
    # smoke puffs over the stack
    for px, py, r in ((42, 4, 2), (38, 6, 2), (45, 7, 2)):
        ellipse(g, px, py, r, r, "s")
    # cab (back/left) + boiler (to the front/right)
    rect(g, 6, 8, 18, 23, "G")
    rect(g, 18, 13, 50, 23, "G")
    rect(g, 9, 11, 16, 16, ":")              # cab window
    hline(g, 6, 50, 22, "r")                 # red running-board trim
    # steam dome + smokestack near the front
    rect(g, 28, 11, 31, 13, "S")
    rect(g, 41, 6, 45, 13, "S")
    # smokebox front + headlight + cowcatcher
    ellipse(g, 50, 18, 2, 5, "S")
    ellipse(g, 51, 17, 1, 1, "o")
    line(g, 50, 23, 57, 28, "S"); line(g, 50, 28, 57, 28, "S"); line(g, 53, 23, 57, 28, "S")
    # big driving wheels + rods
    for wx in (16, 28, 40):
        ellipse(g, wx, 26, 4, 4, "S"); ellipse(g, wx, 26, 1, 1, "o")
    hline(g, 14, 44, 26, "n")
    # railroad track under the wheels: railhead + ties (stays FIXED; the train is
    # lifted over it by the intro animation)
    hline(g, 0, 63, 30, "s")
    for tx in range(1, 63, 4):
        put(g, tx, 31, "n")
    write("locomotive", g)


# ---------------------------------------------------------------- ROCKET
def rocket():
    g = grid()
    cx = 32
    for sx, sy in ((12, 6), (52, 9), (49, 23), (14, 24), (44, 5)):
        put(g, sx, sy, "*")
    # nose cone (red)
    for i in range(7):
        hline(g, cx - i, cx + i, 4 + i, "r")
    # body (white)
    rect(g, cx - 6, 11, cx + 6, 24, "#")
    hline(g, cx - 6, cx + 6, 19, "r")        # band
    ellipse(g, cx, 15, 2, 2, ":")            # porthole
    # fins (red)
    for s in (-1, 1):
        line(g, cx + 6 * s, 21, cx + 10 * s, 27, "r")
        line(g, cx + 6 * s, 25, cx + 10 * s, 27, "r")
        rect(g, cx + 6 * s, 25, cx + 9 * s, 27, "r")
    # exhaust flame
    for i, c in enumerate(("o", "y", "r")):
        hline(g, cx - 3 + i, cx + 3 - i, 25 + i, c)
    write("rocket", g)


# ---------------------------------------------------------------- X-WING
def xwing():
    g = grid()
    cx = 32
    # FRONT view (nose up), after the XEROSTAR reference: 4 S-foils in an X, red
    # wing-root markings, central cockpit, twin engine nacelles below, firing lasers.
    # Grey shapes on the dark panel (no black outlines -> black = LED off).
    wings = (((28, 13), (4, 6)), ((36, 13), (60, 6)),
             ((28, 19), (4, 26)), ((36, 19), (60, 26)))
    for (rx, ry), (tx, ty) in wings:                # grey S-foils
        thick_line(g, rx, ry, tx, ty, "s", 4)
    for (rx, ry), (tx, ty) in wings:                # bright red wing-root markings
        mx, my = rx + (tx - rx) // 3, ry + (ty - ry) // 3
        thick_line(g, rx, ry, mx, my, "r", 3)
    for (rx, ry), (tx, ty) in wings:                # wingtip cannons (thin grey nub)
        ex, ey = tx + (tx - rx) // 14, ty + (ty - ry) // 14
        line(g, tx, ty, ex, ey, "S")
    # central fuselage + nose
    rect(g, 29, 8, 35, 24, "s")
    rect(g, 30, 3, 34, 9, "w")                      # nose
    put(g, 31, 2, "w"); put(g, 33, 2, "w"); put(g, 32, 1, "s")   # nose tip cross
    # cockpit: blue canopy strip + dark opening
    rect(g, 30, 11, 34, 12, ":")
    ellipse(g, 32, 16, 2, 4, "S")
    # twin engine nacelles hanging below
    rect(g, 25, 22, 29, 30, "S"); rect(g, 35, 22, 39, 30, "S")
    vline(g, 26, 22, 29, "s"); vline(g, 36, 22, 29, "s")         # highlights
    # twin red laser bolts firing up
    vline(g, 30, 0, 3, "r"); vline(g, 34, 0, 3, "r")
    write("xwing", g)


# ---------------------------------------------------------------- TREE
def tree():
    g = grid()
    # leafy canopy (overlapping green blobs)
    for cx_, cy_, r in ((32, 12, 11), (22, 15, 7), (42, 15, 7), (27, 9, 6), (38, 9, 6)):
        ellipse(g, cx_, cy_, r, r, "g")
    ellipse(g, 32, 18, 13, 5, "G")           # shaded underside
    for cx_, cy_, r in ((28, 9, 4), (37, 10, 4)):
        ellipse(g, cx_, cy_, r, r, "g")      # sunlit highlights on top
    # thick trunk + roots
    rect(g, 29, 20, 35, 30, "n")
    line(g, 29, 28, 24, 31, "n"); line(g, 35, 28, 40, 31, "n")
    vline(g, 30, 21, 30, "N")                # bark shadow
    write("tree", g)


# ================================================================ BATCH 4
# ---------------------------------------------------------------- CINDERELLA CASTLE
def castle():
    g = grid()
    # towers: (cx, wall_top, half_width, roof_height) — tall centre spire + flanks
    towers = ((32, 7, 5, 8), (20, 13, 4, 6), (44, 13, 4, 6), (11, 17, 3, 5), (53, 17, 3, 5))
    wb = 28
    for tx, wt, hw, rh in towers:
        rect(g, tx - hw, wt, tx + hw, wb, "s")          # stone wall
        vline(g, tx - hw, wt, wb, "w")                  # lit edge
        for i in range(rh + 1):                         # conical blue roof
            w = int((hw + 1) * (1 - i / rh))
            hline(g, tx - w, tx + w, wt - 1 - i, ":")
        put(g, tx, wt - rh - 2, "o")                    # gold finial
        line(g, tx, wt - rh - 2, tx + 2, wt - rh - 1, "r")   # pennant
        put(g, tx, wt + 3, ":")                         # a window
    # central archway + base wall
    rect(g, 8, 26, 56, 29, "s")
    ellipse(g, 32, 29, 3, 4, "S"); rect(g, 29, 26, 35, 29, "S")
    write("castle", g)


# ---------------------------------------------------------------- SPACESHIP EARTH
def spaceship_earth():
    g = grid()
    cx, cy, R = 32, 15, 13
    # solid light-grey sphere with a clear triangular geodesic seam grid (the dot
    # crosshatch read as a grill; legs tucked under so it's a sphere, not a mic stand)
    for y in range(cy - R, cy + R + 1):
        for x in range(cx - R, cx + R + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= R * R:
                seam = (x % 6 == 0) or ((x + 2 * y) % 7 == 0) or ((x - 2 * y) % 7 == 0)
                put(g, x, y, "S" if seam else "s")
    # short tripod legs tucked right under the sphere
    for lx, dx in ((cx - 7, -1), (cx, 0), (cx + 7, 1)):
        line(g, lx, cy + R - 2, lx + dx, 31, "S")
    write("spaceship_earth", g)


# ---------------------------------------------------------------- EXPEDITION EVEREST
def everest():
    g = grid()
    # main peak: filled triangle, snow on top / rock below, jagged ridges
    for y in range(6, 29):
        t = (y - 6) / 22.0
        hw = int(2 + 27 * t)
        ch = "w" if y < 14 else "s"
        hline(g, 30 - hw, 30 + hw, y, ch)
    # twin-peak notch at the very top
    ellipse(g, 30, 7, 2, 3, " "); put(g, 30, 6, " ")
    put(g, 27, 6, "w"); put(g, 33, 7, "w")
    # snow streaks running down the rock
    for sx in (22, 30, 38):
        for k in range(5):
            put(g, sx + k, 14 + k, "w")
    # a smaller foothill peak on the right
    for y in range(16, 29):
        t = (y - 16) / 13.0
        hw = int(1 + 8 * t)
        hline(g, 52 - hw, 52 + hw, y, "s" if y > 19 else "w")
    write("everest", g)


# ---------------------------------------------------------------- DUMBO (elephant)
def elephant():
    g = grid()
    cx = 32
    # big floppy ears
    ellipse(g, cx - 12, 17, 7, 8, "s")
    ellipse(g, cx + 12, 17, 7, 8, "s")
    ellipse(g, cx - 12, 17, 4, 5, "S")
    ellipse(g, cx + 12, 17, 4, 5, "S")
    # head
    ellipse(g, cx, 16, 9, 9, "s")
    # trunk curling down
    for i, ty in enumerate(range(21, 31)):
        tx = cx + int(3 * math.sin(i / 2.6))
        rect(g, tx - 1, ty, tx + 1, ty, "s")
    # eyes
    put(g, cx - 4, 14, "w"); put(g, cx + 4, 14, "w")
    put(g, cx - 4, 15, "S"); put(g, cx + 4, 15, "S")
    # tiny yellow circus hat
    rect(g, cx - 3, 5, cx + 3, 7, "o"); rect(g, cx - 2, 3, cx + 2, 5, "o")
    write("elephant", g)


# ---------------------------------------------------------------- GIRAFFE (Kilimanjaro Safaris)
def giraffe():
    g = grid()
    # savanna ground
    hline(g, 2, 61, 31, "g")
    for x in range(3, 61, 4):
        put(g, x, 30, "g")
    # body (tan), front (left) raised into a sloping back
    ellipse(g, 38, 18, 12, 5, "T")
    rect(g, 28, 15, 48, 21, "T")
    rect(g, 28, 14, 34, 15, "T")              # withers
    # long legs, dark hooves + lighter lower "socks"
    for lx in (30, 34, 44, 48):
        rect(g, lx, 21, lx + 1, 29, "T")
        rect(g, lx, 27, lx + 1, 29, "w")
        put(g, lx, 30, "N"); put(g, lx + 1, 30, "N")
    # tail + tuft
    line(g, 49, 16, 52, 23, "T")
    put(g, 52, 23, "N"); put(g, 52, 24, "N")
    # long neck, leaning left to the head
    thick_line(g, 28, 17, 21, 5, "T", 5)
    # head + muzzle (left), ossicones, ear, eye, nostril
    ellipse(g, 20, 4, 3, 2, "T")
    rect(g, 14, 4, 20, 6, "T")
    put(g, 19, 1, "N"); put(g, 19, 2, "T")
    put(g, 22, 1, "N"); put(g, 22, 2, "T")
    line(g, 23, 3, 25, 4, "T")
    put(g, 17, 4, "K")
    put(g, 14, 5, "N")
    # short mane down the back of the neck
    for i in range(0, 12):
        put(g, 29 - i // 2, 17 - i, "n")
    # reticulated patches (brown)
    for (x0, y0, w, h) in [(31, 16, 3, 2), (36, 18, 3, 2), (41, 16, 3, 2),
                           (45, 19, 2, 2), (25, 12, 2, 2), (23, 9, 2, 2), (33, 19, 2, 1)]:
        rect(g, x0, y0, x0 + w - 1, y0 + h - 1, "n")
    write("giraffe", g)


# ---------------------------------------------------------------- TRON LIGHTCYCLE
def tron():
    g = grid()
    # sleek side-view LIGHTCYCLE (no long horizontal trail -> it read as a gun barrel).
    # two big solid disc wheels (no spokes) with cyan rims, close coupled.
    for wx in (19, 45):
        ellipse(g, wx, 21, 6, 6, "S")
        ring(g, wx, 21, 6, "~"); ring(g, wx, 21, 5, "~")
        ellipse(g, wx, 21, 2, 2, "~")
    # low swept deck bridging the wheels (dips in the middle)
    for x in range(19, 46):
        top = 15 + int(2 * math.sin((x - 19) / 27.0 * math.pi))
        vline(g, x, top, 20, "S")
        put(g, x, top - 1, "~")                # cyan glowing top edge
    # front cowl sweeping up over the front wheel
    line(g, 45, 14, 52, 11, "~"); line(g, 46, 16, 53, 13, "S"); line(g, 47, 18, 53, 15, "~")
    # crouched rider
    rect(g, 28, 12, 38, 15, "S")
    ellipse(g, 33, 11, 2, 2, "S")
    line(g, 31, 10, 35, 10, "~")               # visor glow
    # a short light-ribbon stub off the tail (not a full barrel)
    rect(g, 11, 17, 16, 19, "~")
    write("tron", g)


# ---------------------------------------------------------------- MILLENNIUM FALCON
def falcon():
    g = grid()
    cx, cy = 30, 15
    # saucer hull (grey), front (mandibles) to the right
    ellipse(g, cx, cy, 17, 11, "s")
    # mandible fork: carve a V notch into the front-right edge
    for i in range(7):
        w = 6 - i
        for yy in range(cy - w, cy + w + 1):
            put(g, cx + 11 + i, yy, " ")
    # the two mandible prongs
    rect(g, cx + 10, cy - 6, cx + 17, cy - 4, "s")
    rect(g, cx + 10, cy + 4, cx + 17, cy + 6, "s")
    # round sensor dish on top
    ellipse(g, cx - 3, cy - 9, 3, 2, "S"); put(g, cx - 3, cy - 9, "s")
    # cockpit pod sticking out the lower-right with a blue window
    rect(g, cx + 9, cy + 6, cx + 14, cy + 9, "s")
    put(g, cx + 12, cy + 7, ":")
    # panel detailing + central ring
    ring(g, cx, cy, 7, "S")
    # bright rear engine band (left) so the BACK is unmistakable (vs a fish tail)
    rect(g, cx - 18, cy - 5, cx - 14, cy + 5, "~")
    vline(g, cx - 16, cy - 4, cy + 4, "w")
    write("falcon", g)


# ================================================================ BATCH 5 (water)
def _water(g, rows):
    for y in rows:
        for x in range(W):
            if (x + y) % 5:
                put(g, x, y, "~")


# ---------------------------------------------------------------- SUBMARINE (Nemo)
def submarine():
    g = grid()
    _water(g, (27, 28, 29))
    ellipse(g, 32, 18, 18, 7, "y")                 # yellow hull
    rect(g, 28, 9, 38, 14, "y")                    # conning tower
    rect(g, 30, 7, 36, 9, "y")
    vline(g, 33, 3, 7, "S"); hline(g, 33, 36, 3, "S")   # periscope
    for px in (23, 31, 39):                        # portholes
        ellipse(g, px, 18, 2, 2, "~"); ring(g, px, 18, 2, "S")
    line(g, 14, 14, 12, 22, "S"); line(g, 12, 14, 14, 22, "S")   # propeller
    rect(g, 14, 17, 16, 19, "S")
    for bx, by in ((48, 8), (52, 5), (50, 11)):    # bubbles
        put(g, bx, by, "w")
    write("submarine", g)


# ---------------------------------------------------------------- RIVERBOAT (Mark Twain)
def riverboat():
    g = grid()
    _water(g, (27, 28, 29))
    rect(g, 9, 22, 52, 26, "w"); line(g, 52, 22, 57, 26, "w")    # hull + bow
    rect(g, 13, 17, 48, 22, "w")                   # main deck
    rect(g, 17, 12, 44, 17, "w")                   # upper deck
    hline(g, 13, 48, 17, "r"); hline(g, 17, 44, 12, "r")        # red trim
    for x in range(15, 48, 3):
        put(g, x, 20, "S")                         # railings
    rect(g, 23, 4, 26, 12, "S"); rect(g, 31, 4, 34, 12, "S")    # twin stacks
    for sx, sy in ((23, 2), (21, 1), (32, 2), (30, 1)):
        ellipse(g, sx, sy, 1, 1, "s")              # smoke
    ellipse(g, 9, 22, 4, 4, "r"); ring(g, 9, 22, 4, "S")        # red paddlewheel
    line(g, 9, 18, 9, 26, "S"); line(g, 5, 22, 13, 22, "S")
    write("riverboat", g)


# ---------------------------------------------------------------- CANOE (Davy Crockett)
def canoe():
    g = grid()
    _water(g, (23, 24, 25))
    # slender hull with UPSWEPT pointed ends (the canoe tell vs a generic boat)
    for x in range(9, 56):
        t = (x - 32) / 23.0
        gun = 18 - int(5 * t * t)                  # gunwale: low centre, sweeps up at ends
        bot = 22 - int(9 * t * t)                  # bottom meets the gunwale at the tips
        if bot >= gun:
            vline(g, x, gun, bot, "n")
            put(g, x, gun, "w")                    # gunwale highlight
    for x in range(16, 49, 6):
        put(g, x, 21, "N")                         # interior ribs
    # seated paddler
    ellipse(g, 28, 12, 2, 2, "N"); rect(g, 26, 14, 30, 18, "N")
    # paddle angled down, blade dipping into the water
    line(g, 30, 11, 39, 22, "w"); rect(g, 38, 22, 40, 25, "n")
    write("canoe", g)


# ---------------------------------------------------------------- WAVE (Tiana's)
def wave():
    g = grid()
    _water(g, (28, 29, 30))
    # breaking wave: a tall hump peaking on the left (the curl) sloping down right
    def peak(x):
        return 7 + 17 * math.exp(-((x - 24) ** 2) / 120.0)
    for x in range(8, 58):
        top = int(27 - peak(x))
        vline(g, x, top, 27, "~")
    ellipse(g, 19, 16, 6, 5, " ")                  # carve the barrel (open scoop)
    for x in range(8, 58):                         # white foam crest
        top = int(27 - peak(x))
        put(g, x, top, "w"); put(g, x, top + 1, "w")
    ring(g, 19, 16, 6, "w")                        # foam lining the barrel
    for fx, fy in ((13, 5), (9, 8), (27, 3), (31, 6), (17, 3)):  # spray off the crest
        put(g, fx, fy, "w")
    write("wave", g)


# ---------------------------------------------------------------- JELLYFISH
def jellyfish():
    g = grid()
    cx = 32
    ellipse(g, cx, 13, 10, 8, ":", half="top")     # bell dome
    rect(g, cx - 10, 13, cx + 10, 15, ":")
    ellipse(g, cx, 12, 5, 4, "~")                  # inner glow
    for x in range(cx - 9, cx + 10, 3):
        put(g, x, 16, "~")                         # scalloped rim
    for i, tx in enumerate(range(cx - 8, cx + 9, 3)):          # trailing tentacles
        for y in range(16, 30):
            x = tx + int(2 * math.sin((y + 2 * i) / 2.0))
            put(g, x, y, "~" if y % 2 else "w")
    write("jellyfish", g)


# ---------------------------------------------------------------- RIVER (Na'vi)
def river():
    g = grid()
    for y in range(32):                            # winding river through banks
        cxr = 32 + int(13 * math.sin(y / 6.5))
        for x in range(W):
            d = abs(x - cxr)
            if d < 5:
                put(g, x, y, "~")
            elif d < 8:
                put(g, x, y, "G")
    for px, py, c in ((19, 5, "o"), (47, 11, "r"), (15, 19, "~"),   # glowing plants
                      (49, 25, "o"), (23, 29, "r"), (44, 3, "~")):
        ellipse(g, px, py, 1, 1, c)
    write("river", g)


# ================================================================ BATCH 6 (props)
# ---------------------------------------------------------------- BIG BEN (Peter Pan)
def big_ben():
    g = grid()
    ellipse(g, 11, 7, 4, 4, "o")                   # moon behind
    rect(g, 26, 9, 38, 30, "w")                    # stone tower
    vline(g, 26, 9, 30, "s")                       # shaded edge
    for i in range(5):                             # gold spire roof
        w = 6 - i
        hline(g, 32 - w, 32 + w, 8 - i, "o")
    put(g, 32, 2, "o")
    ellipse(g, 32, 14, 4, 4, "#"); ring(g, 32, 14, 4, "S")     # clock face
    line(g, 32, 14, 32, 11, "S"); line(g, 32, 14, 34, 15, "S")  # hands
    for y in (20, 24, 28):                         # windows
        put(g, 29, y, ":"); put(g, 35, y, ":")
    write("big_ben", g)


# ---------------------------------------------------------------- GEMS (Seven Dwarfs)
def gems():
    g = grid()
    def gem(cx, cy, s, c):
        for dy in range(-s, s + 1):
            w = s - abs(dy)
            hline(g, cx - w, cx + w, cy + dy, c)
        hline(g, cx - s + 1, cx + s - 1, cy - s + 1, "w")   # top-facet glint
    gem(19, 19, 5, ":")                            # blue
    gem(34, 17, 6, "r")                            # red
    gem(47, 20, 4, "g")                            # green
    for sx, sy in ((27, 8), (41, 6), (12, 12), (52, 11)):    # sparkles
        put(g, sx, sy, "w"); put(g, sx, sy - 1, "o")
    write("gems", g)


def magic_carpet():
    g = grid()
    def yo(x):
        return int(2.5 * math.sin((x - 14) / 8.0))
    # bordered rectangular RUG (not a flat band) with a centre medallion + tassels
    for x in range(14, 51):
        o = yo(x)
        vline(g, x, 12 + o, 22 + o, "r")
        put(g, x, 12 + o, "o"); put(g, x, 22 + o, "o")          # gold top/bottom border
    vline(g, 14, 12 + yo(14), 22 + yo(14), "o")
    vline(g, 50, 12 + yo(50), 22 + yo(50), "o")                 # gold side borders
    for x in range(16, 49):                        # inner border lines
        o = yo(x); put(g, x, 14 + o, "o"); put(g, x, 20 + o, "o")
    o = yo(32)                                     # centre medallion (blue diamond)
    for dy in range(-3, 4):
        w = 3 - abs(dy); hline(g, 32 - w, 32 + w, 17 + o + dy, ":")
    put(g, 32, 17 + o, "y")
    for tx in range(17, 49, 5):                    # tassels hanging off the bottom
        o = yo(tx); vline(g, tx, 23 + o, 26 + o, "o")
    write("magic_carpet", g)


# ---------------------------------------------------------------- JACK-IN-THE-BOX (Toy Story)
def jack_in_box():
    g = grid()
    cx = 32
    rect(g, 22, 19, 42, 30, "r")                   # box
    hline(g, 22, 42, 22, ":"); hline(g, 22, 42, 27, ":")        # box bands
    rect(g, 22, 19, 42, 20, "o")
    line(g, 22, 19, 17, 13, "r"); line(g, 42, 19, 47, 13, "r"); hline(g, 17, 47, 13, "o")  # open lid
    for i, y in enumerate(range(8, 19)):           # coil spring
        x = cx + int(3 * math.sin(i * 1.1))
        put(g, x, y, "s"); put(g, x + 1, y, "S")
    ellipse(g, cx, 6, 3, 3, "w")                   # clown head
    put(g, cx - 1, 6, "r"); put(g, cx + 1, 6, "r")
    line(g, cx - 2, 4, cx - 3, 2, "r"); line(g, cx + 2, 4, cx + 3, 2, "r")   # hat points
    write("jack_in_box", g)


# ---------------------------------------------------------------- MOP & BUCKET (PhilharMagic)
def mop_bucket():
    g = grid()
    # bucket (right) — tapered pail with water + handle
    for y in range(20, 30):
        hw = 5 + (y - 20) // 4
        hline(g, 44 - hw, 44 + hw, y, "S")
    hline(g, 38, 50, 20, "s")
    ellipse(g, 44, 20, 5, 1, "~")                  # water surface
    ring(g, 44, 19, 6, "s", cond=lambda x, y: y < 20)          # handle
    # mop — handle leaning in + stringy head
    line(g, 14, 7, 30, 22, "n"); line(g, 15, 7, 31, 22, "n")
    for i in range(9):                             # mop strings
        line(g, 27 + i // 2, 22, 24 + i, 30, "w")
    write("mop_bucket", g)


# ================================================================ BATCH 7
# ---------------------------------------------------------------- OLD CAR (Main St)
def old_car():
    g = grid()
    rect(g, 14, 16, 52, 23, "r")                   # body
    rect(g, 18, 8, 39, 16, "r")                    # cabin
    rect(g, 18, 7, 39, 8, "w")                     # roof
    rect(g, 20, 10, 37, 13, ":")                   # windows
    rect(g, 39, 14, 53, 18, "r")                   # hood (front)
    hline(g, 16, 50, 23, "N")                      # running board
    ellipse(g, 53, 17, 1, 1, "o")                  # headlight
    for wx in (20, 46):                            # spoked wheels
        ellipse(g, wx, 24, 5, 5, "N"); ring(g, wx, 24, 5, "s")
        ellipse(g, wx, 24, 2, 2, "s")
        for a in range(0, 360, 45):
            line(g, wx, 24, wx + int(4 * math.cos(math.radians(a))),
                 24 + int(4 * math.sin(math.radians(a))), "s")
    write("old_car", g)


# ---------------------------------------------------------------- BARN (Barnstormer)
def barn():
    g = grid()
    rect(g, 16, 16, 48, 29, "r")                   # barn body
    for y in range(6, 17):                         # gambrel roof
        w = int((y - 6) * 1.6) + 3 if y < 11 else int((y - 11) * 2.6) + 11
        hline(g, 32 - w, 32 + w, y, "N")
    hline(g, 16, 48, 16, "w")                      # eave trim
    rect(g, 26, 20, 38, 29, "w")                   # big doors
    line(g, 26, 20, 38, 29, "r"); line(g, 38, 20, 26, 29, "r")  # door X-bracing
    vline(g, 32, 20, 29, "r")
    rect(g, 30, 11, 34, 15, "w"); put(g, 32, 13, "o")           # hayloft window
    rect(g, 50, 14, 55, 29, "s"); ellipse(g, 52, 14, 3, 2, "S")  # silo
    write("barn", g)


# ---------------------------------------------------------------- DOOR (Monsters Inc)
def door():
    g = grid()
    vline(g, 21, 3, 30, "s"); vline(g, 43, 3, 30, "s"); hline(g, 21, 43, 3, "s")  # frame
    rect(g, 22, 4, 42, 30, "n")                    # door slab
    rect(g, 23, 5, 41, 29, "r")                    # painted face
    for y0 in (8, 19):                             # two recessed panels
        rect(g, 26, y0, 38, y0 + 8, "N"); rect(g, 27, y0 + 1, 37, y0 + 7, "r")
    ellipse(g, 39, 17, 1, 1, "o"); put(g, 39, 16, "y")          # knob
    write("door", g)


# ---------------------------------------------------------------- RAT (Remy)
def rat():
    g = grid()
    # side-profile rat facing right, with the rat-defining long curling tail
    ellipse(g, 23, 20, 8, 6, ":")                  # rounded haunch/body
    ellipse(g, 33, 20, 8, 5, ":")                  # mid body
    ellipse(g, 42, 19, 5, 4, ":")                  # head
    rect(g, 45, 18, 50, 20, ":"); put(g, 51, 20, "r")          # snout + pink nose
    ellipse(g, 40, 13, 3, 3, ":"); ellipse(g, 40, 13, 1, 1, "r")   # round ear
    put(g, 44, 17, "w"); put(g, 44, 17, "S")       # eye
    line(g, 51, 21, 46, 22, "s"); line(g, 51, 19, 47, 18, "s")  # whiskers
    tail = ((16, 22), (9, 21), (5, 16), (8, 10), (15, 8))       # long curling tail
    for i in range(len(tail) - 1):
        line(g, tail[i][0], tail[i][1], tail[i + 1][0], tail[i + 1][1], "r")
    ellipse(g, 26, 26, 2, 1, ":"); ellipse(g, 36, 26, 2, 1, ":")  # feet
    write("rat", g)


# ---------------------------------------------------------------- FROG (Mr. Toad)
def frog():
    g = grid()
    cx = 32
    ellipse(g, cx, 20, 12, 8, "g")                 # body
    ellipse(g, cx - 6, 11, 4, 4, "g"); ellipse(g, cx + 6, 11, 4, 4, "g")    # eye bulges
    ellipse(g, cx - 6, 10, 2, 2, "w"); ellipse(g, cx + 6, 10, 2, 2, "w")
    put(g, cx - 6, 10, "S"); put(g, cx + 6, 10, "S")           # pupils
    for x in range(cx - 8, cx + 9):                # wide smile
        put(g, x, 22 + int(2 * math.sin((x - cx + 8) / 16.0 * math.pi)), "G")
    put(g, cx - 2, 17, "G"); put(g, cx + 2, 17, "G")           # nostrils
    ellipse(g, cx - 10, 27, 3, 1, "g"); ellipse(g, cx + 10, 27, 3, 1, "g")  # feet
    write("frog", g)


# ---------------------------------------------------------------- VOLCANO (Journey of Water)
def volcano():
    g = grid()
    for y in range(11, 29):                        # rock cone
        hw = int(3 + 22 * (y - 11) / 18.0)
        hline(g, 32 - hw, 32 + hw, y, "N")
    hline(g, 26, 38, 11, "S")
    ellipse(g, 32, 11, 5, 2, "r"); ellipse(g, 32, 11, 3, 1, "o")            # lava crater
    for sx in (27, 36):                            # lava streaks
        for k in range(9):
            put(g, sx + int(1.5 * math.sin(k)), 12 + k, "r" if k % 2 else "o")
    for px, py, r in ((30, 5, 2), (35, 3, 2), (26, 6, 2)):     # smoke
        ellipse(g, px, py, r, r, "s")
    write("volcano", g)


# ---------------------------------------------------------------- PLANT (Living with the Land)
def plant():
    g = grid()
    ellipse(g, 32, 27, 13, 4, "n"); rect(g, 20, 27, 44, 30, "n")            # soil
    vline(g, 32, 11, 27, "G")                      # stem
    for lx, ly in ((26, 16), (38, 16), (27, 20), (37, 20)):    # leaf pairs
        ellipse(g, lx, ly, 4, 2, "g"); ellipse(g, lx, ly, 2, 1, "G")
    ellipse(g, 30, 11, 3, 2, "g"); ellipse(g, 34, 11, 3, 2, "g")            # top sprout
    put(g, 32, 9, "o")                             # bud
    write("plant", g)


# ================================================================ BATCH 8 (final)
# ---------------------------------------------------------------- CHILD (small world)
def child():
    g = grid()
    cx = 32
    ellipse(g, cx, 11, 6, 6, "w")                  # head (skin)
    ellipse(g, cx, 7, 6, 3, "n"); rect(g, cx - 6, 6, cx + 6, 8, "n")        # hair
    ellipse(g, cx - 7, 12, 2, 3, "n"); ellipse(g, cx + 7, 12, 2, 3, "n")    # pigtails
    put(g, cx - 2, 11, ":"); put(g, cx + 2, 11, ":")           # eyes
    put(g, cx - 3, 13, "r"); put(g, cx + 3, 13, "r")           # cheeks
    hline(g, cx - 1, cx + 1, 14, "r")              # smile
    for y in range(17, 27):                        # triangular dress
        hw = int(2 + (y - 17) * 0.95)
        hline(g, cx - hw, cx + hw, y, "r")
    line(g, cx - 4, 18, cx - 9, 22, "w"); line(g, cx + 4, 18, cx + 9, 22, "w")  # arms
    vline(g, cx - 3, 27, 30, "w"); vline(g, cx + 3, 27, 30, "w")            # legs
    write("child", g)


# ---------------------------------------------------------------- WATER / SPLASH (Casey Jr)
def splash():
    g = grid()
    cx = 32
    ellipse(g, cx, 27, 16, 3, "~")                 # puddle
    for ang in range(-60, 61, 20):                 # splash crown spikes
        x2 = cx + int(15 * math.sin(math.radians(ang)))
        y2 = 24 - int(15 * math.cos(math.radians(ang)))
        line(g, cx, 24, x2, y2, "~"); put(g, x2, y2, "w")
    vline(g, cx, 7, 24, "~"); put(g, cx, 6, "w")   # central jet
    for dx, dy in ((16, 11), (48, 13), (20, 6), (45, 19), (12, 17), (52, 8)):   # droplets
        put(g, dx, dy, "w"); put(g, dx, dy + 1, "~")
    write("splash", g)


# ---------------------------------------------------------------- BOBSLED (Matterhorn)
def bobsled():
    g = grid()
    # banked snow/ice chute (white, NOT blue -> blue read as water/boat) curving behind
    for x in range(W):
        wall = 13 - int(6 * math.sin(math.pi * x / 63.0))
        put(g, x, wall, "s"); put(g, x, wall + 1, "w")
    hline(g, 0, 63, 26, "w"); hline(g, 0, 63, 27, "s"); hline(g, 0, 63, 28, "s")   # ice floor
    rect(g, 17, 18, 42, 24, "r")                   # compact sled body
    ellipse(g, 43, 20, 5, 4, "r")                  # rounded front cowling
    rect(g, 19, 16, 39, 18, "S")                   # open cockpit rim
    for i, hx in enumerate((22, 27, 32, 37)):      # FOUR helmets in a row = bobsled crew
        ellipse(g, hx, 16, 2, 2, ("o", "y", ":", "r")[i])
    hline(g, 15, 45, 25, "S"); put(g, 16, 26, "S"); put(g, 44, 26, "S")            # runner blades
    for y in (19, 22):
        hline(g, 2, 13, y, "s")                    # speed lines
    write("bobsled", g)


# ---------------------------------------------------------------- COASTER CAR (Incredicoaster)
def coaster_car():
    g = grid()
    pts = ((2, 7), (16, 9), (28, 15), (40, 24), (61, 28))      # swooping track
    for i in range(len(pts) - 1):
        line(g, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], "S")
        line(g, pts[i][0], pts[i][1] + 1, pts[i + 1][0], pts[i + 1][1] + 1, "s")
    # wooden trestle: posts under the rail + stringers + cross-braces (classic woodie)
    posts = ((8, 9), (16, 11), (24, 14), (32, 18), (40, 26), (48, 27), (56, 29))
    for px, py in posts:
        vline(g, px, py, 30, "n")
    hline(g, 8, 33, 22, "n")                       # upper stringer (under the drop)
    hline(g, 8, 52, 28, "n")                       # lower stringer
    line(g, 8, 30, 16, 22, "N"); line(g, 16, 30, 24, 22, "N")   # cross-braces
    line(g, 24, 30, 32, 22, "N"); line(g, 32, 30, 40, 28, "N")
    # red coaster car at the crest — ROUNDED body (scooped tub, curved nose),
    # not a hard-cornered box
    for y, (xa, xb) in ((10, (24, 33)), (11, (23, 35)), (12, (22, 36)),
                        (13, (22, 37)), (14, (23, 37)), (15, (24, 36))):
        hline(g, xa, xb, y, "r")
    for hx in (25, 29, 32):                        # riders + raised arms
        put(g, hx, 8, "w"); line(g, hx, 8, hx - 1, 6, "w"); line(g, hx, 8, hx + 1, 6, "w")
    put(g, 24, 16, "o"); put(g, 32, 16, "o")       # wheels
    write("coaster_car", g)


# ---------------------------------------------------------------- AIRPLANE (Soarin' EPCOT)
def airplane():
    g = grid()
    # TOP-DOWN airliner, nose RIGHT (its traverse direction) — from above the swept
    # wings are unmistakable, which the old side view never managed at 64x32.
    cy = 16
    rect(g, 8, cy - 2, 50, cy + 2, "w")            # fuselage tube
    for i in range(7):                             # tapered nose to x56
        hw = 2 if i < 3 else (1 if i < 5 else 0)
        for y in range(cy - hw, cy + hw + 1):
            put(g, 50 + i, y, "w")
    # big swept main wings, mirrored above/below the fuselage
    for d in range(11):
        span = 7 - (d * 4) // 10                   # chord narrows toward the tip
        xr = 31 - d                                # trailing sweep
        hline(g, xr - span, xr, cy - 3 - d, "s")
        hline(g, xr - span, xr, cy + 3 + d, "s")
    # swept tailplane pair at the rear
    for d in range(4):
        xr = 12 - d
        hline(g, xr - 3, xr, cy - 3 - d, "s")
        hline(g, xr - 3, xr, cy + 3 + d, "s")
    hline(g, 4, 10, cy, "S")                       # dorsal fin seen edge-on
    # engines on the wings + cockpit windshield
    put(g, 24, cy - 6, "o"); put(g, 24, cy + 6, "o")
    put(g, 48, cy - 1, ":"); put(g, 49, cy, ":"); put(g, 48, cy + 1, ":")
    write("airplane", g)


# ---------------------------------------------------------------- HANG GLIDER (Soarin' DCA)
def hang_glider():
    g = grid()
    ellipse(g, 9, 25, 3, 2, "s"); ellipse(g, 54, 27, 3, 2, "s")            # clouds
    for y in range(6, 16):                         # delta wing (striped)
        hw = int((y - 6) * 2.3)
        hline(g, 32 - hw, 32 + hw, y, "r" if (y % 2) else "o")
    vline(g, 32, 6, 16, "w")                       # keel
    hline(g, 27, 37, 19, "S")                      # control bar
    line(g, 28, 16, 27, 19, "S"); line(g, 36, 16, 37, 19, "S")
    line(g, 32, 16, 33, 21, "s")                   # harness line
    ellipse(g, 33, 22, 4, 1, "S"); put(g, 37, 22, "w")        # prone pilot + head
    write("hang_glider", g)


# ================================================================ BATCH 9 (Efteling)
# ---------------------------------------------------------------- MUSHROOM (Fairytale Forest)
def mushroom():
    g = grid()
    cx = 32
    # grassy hummock the toadstool grows from
    ellipse(g, cx, 28, 15, 3, "g")
    ellipse(g, cx, 30, 22, 2, "G")
    # white stem, flaring gently at the base
    for y in range(15, 28):
        t = (y - 15) / 12.0
        hw = int(4 + 3 * t * t)
        hline(g, cx - hw, cx + hw, y, "w")
    # red dome cap (rounded top, flat underside) with a thick lip
    ellipse(g, cx, 15, 18, 10, "r", half="top")
    hline(g, cx - 18, cx + 18, 15, "r")
    hline(g, cx - 16, cx + 16, 16, "r")
    hline(g, cx - 7, cx + 7, 17, "w")              # cream collar under the cap
    # white polka spots
    for sx, sy, sr in ((22, 9, 3), (41, 8, 2), (31, 12, 2), (47, 12, 2),
                       (16, 12, 2), (36, 6, 2)):
        ellipse(g, sx, sy, sr, sr, "#")
    write("mushroom", g)


# ---------------------------------------------------------------- SNAKE (Python coaster)
def snake():
    g = grid()
    cx, cy = 26, 21
    # coiled body: a thick green ring (a wound coil you can see through the middle)
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - cx, (y - cy) * 1.25)
            if 6.5 <= d <= 11.5:
                put(g, x, y, "g")
                if d <= 7.5 or d >= 10.5:
                    put(g, x, y, "G")              # darker inner/outer body edge
    # diamond markings around the coil (python blotches)
    for a in range(0, 360, 45):
        bx = cx + int(9 * math.cos(math.radians(a)))
        by = cy + int(7 * math.sin(math.radians(a)))
        ellipse(g, bx, by, 1, 1, "G")
    # tail tip poking out of the coil (lower-left)
    line(g, cx - 9, cy + 6, cx - 14, cy + 9, "g"); put(g, cx - 14, cy + 9, "G")
    # neck rising up-right from the coil to a raised head
    npts = ((cx + 8, cy - 6), (cx + 12, cy - 11), (cx + 16, cy - 14))
    for i in range(len(npts) - 1):
        thick_line(g, npts[i][0], npts[i][1], npts[i + 1][0], npts[i + 1][1], "g", 5)
    # raised head (upper-right) + snout
    ellipse(g, cx + 19, cy - 15, 5, 4, "g")        # ~ (45, 6)
    rect(g, cx + 22, cy - 16, cx + 26, cy - 14, "g")
    ellipse(g, cx + 18, cy - 16, 1, 1, "y"); put(g, cx + 19, cy - 16, "N")   # eye
    # forked red tongue flicking out to the right
    line(g, cx + 26, cy - 15, cx + 32, cy - 17, "r")
    line(g, cx + 26, cy - 15, cx + 32, cy - 13, "r"); put(g, cx + 30, cy - 15, "r")
    write("snake", g)


# ---------------------------------------------------------------- PAGODA (Pagode)
def pagoda():
    g = grid()
    cx = 32

    def roof(cy, hw):
        for i in range(3):                         # narrows upward over 3 rows
            w = hw - i * 3
            hline(g, cx - w, cx + w, cy - i, "r")
        put(g, cx - hw, cy - 1, "o"); put(g, cx + hw, cy - 1, "o")          # upturned
        put(g, cx - hw - 1, cy - 2, "o"); put(g, cx + hw + 1, cy - 2, "o")  # gold eaves

    def body(y0, y1, hw, door=False):
        rect(g, cx - hw, y0, cx + hw, y1, "w")
        hline(g, cx - hw, cx + hw, y0, ":")        # shaded line under the eave
        if door:
            rect(g, cx - 2, y1 - 4, cx + 2, y1, "r")
        else:
            put(g, cx, (y0 + y1) // 2, ":")        # little window

    vline(g, cx, 2, 5, "o"); put(g, cx, 1, "y")    # finial spike
    roof(7, 9);   body(8, 11, 4)                   # top tier
    roof(14, 13); body(15, 18, 6)                  # mid tier
    roof(21, 17); body(22, 29, 8, door=True)       # base tier
    write("pagoda", g)


# ---------------------------------------------------------------- SKULL (Danse Macabre)
def skull():
    g = grid()
    cx = 32
    ellipse(g, cx, 13, 11, 10, "w")                # bone cranium
    for y in range(19, 27):                        # cheeks taper to the chin
        hw = int(10 - (y - 19) * 1.0)
        hline(g, cx - hw, cx + hw, y, "w")
    ellipse(g, cx - 5, 13, 3, 3, " ")              # deep eye sockets (carve to dark)
    ellipse(g, cx + 5, 13, 3, 3, " ")
    for i in range(3):                             # inverted-triangle nose cavity
        hline(g, cx - (2 - i), cx + (2 - i), 18 + i, " ")
    rect(g, cx - 7, 22, cx + 7, 26, "w")           # teeth block
    for tx in range(cx - 6, cx + 7, 2):            # gaps between the teeth
        vline(g, tx, 22, 26, " ")
    write("skull", g)


# ---------------------------------------------------------------- FISH / PIRANHA (Piraña)
def fish():
    g = grid()
    cx, cy = 31, 16
    ellipse(g, cx, cy, 14, 9, "s")                 # deep silvery body, head to the right
    ellipse(g, cx + 5, cy + 4, 9, 4, "r")          # red belly
    # forked tail fin sweeping out to the left
    for x in range(7, 19):
        t = (18 - x) / 11.0
        h = int(1 + 8 * t)
        vline(g, x, cy - h, cy + h, "s")
    fill_tri(g, (7, cy), (12, cy - 2), (12, cy + 2), " ")   # tail notch (fork)
    # dorsal fin (top)
    fill_tri(g, (26, 8), (37, 8), (31, 3), "s")
    # anal fin (bottom)
    fill_tri(g, (28, 24), (38, 24), (33, 28), "r")
    # open jaw + teeth (under-bite, right side)
    fill_tri(g, (40, 18), (46, 16), (46, 21), " ")          # mouth gap
    for tx in (42, 44):
        fill_tri(g, (tx, 16), (tx + 2, 16), (tx + 1, 19), "#")   # upper teeth
        fill_tri(g, (tx, 21), (tx + 2, 21), (tx + 1, 18), "#")   # lower teeth
    # gill arc + eye
    ring(g, 38, cy, 7, "S", cond=lambda x, y: x < 39)
    ellipse(g, 40, 12, 2, 2, "#"); put(g, 40, 12, "N")
    write("fish", g)


# ---------------------------------------------------------------- BIRD / ROC (Vogel Rok)
def bird():
    g = grid()
    cx = 32
    # soaring bald-eagle look, head-on: dark wings/body, WHITE head + WHITE tail so it
    # reads as a BIRD, not a bat (both AI testers called the all-dark version a bat).
    thick_line(g, cx - 2, 14, 5, 7, "S", 4)
    thick_line(g, cx + 2, 14, 59, 7, "S", 4)
    thick_line(g, cx - 2, 16, 14, 16, "S", 3)
    thick_line(g, cx + 2, 16, 50, 16, "S", 3)
    fill_tri(g, (cx - 2, 13), (5, 7), (14, 16), "S")           # left wing membrane
    fill_tri(g, (cx + 2, 13), (59, 7), (50, 16), "S")          # right wing membrane
    for fx in range(10, 26, 4):                    # lighter feather separations
        put(g, fx, 15 + (fx - 10) // 8, "s")
    for fx in range(40, 56, 4):
        put(g, fx, 15 + (54 - fx) // 8, "s")
    for ex, ey in ((5, 7), (8, 5), (11, 7)):       # left wingtip primary fingers
        line(g, cx - 8, 12, ex, ey, "S")
    for ex, ey in ((59, 7), (56, 5), (53, 7)):     # right wingtip primary fingers
        line(g, cx + 8, 12, ex, ey, "S")
    ellipse(g, cx, 18, 3, 6, "S")                  # dark body
    ellipse(g, cx, 9, 3, 3, "#")                   # white head (eagle)
    fill_tri(g, (cx - 2, 11), (cx + 2, 11), (cx, 14), "o")     # gold hooked beak
    put(g, cx - 1, 8, "N"); put(g, cx + 1, 8, "N")            # eyes
    fill_tri(g, (cx - 4, 23), (cx + 4, 23), (cx, 30), "#")     # fanned white tail
    write("bird", g)


# ---------------------------------------------------------------- DRAGON (Joris en de Draak)
def dragon():
    g = grid()
    cy = 15
    # fire breath blasting LEFT (red outer, orange mid, yellow core)
    fill_tri(g, (0, 7), (0, 23), (19, cy), "r")
    fill_tri(g, (2, 10), (2, 20), (15, cy), "o")
    fill_tri(g, (4, 12), (4, 18), (12, cy), "y")
    # head mass (right of the jaws)
    ellipse(g, 40, 14, 13, 11, "g")
    # upper jaw / snout reaching left, lower jaw below — open mouth between them
    fill_tri(g, (13, 11), (32, 8), (32, 15), "g")          # upper jaw
    fill_tri(g, (15, 22), (32, 17), (32, 23), "g")         # lower jaw
    fill_tri(g, (16, 15), (31, 12), (31, 18), " ")         # open mouth (dark gap)
    # white fangs ringing the mouth
    fill_tri(g, (21, 13), (24, 13), (22, 17), "w")         # upper fang
    fill_tri(g, (27, 13), (30, 13), (28, 16), "w")
    fill_tri(g, (22, 19), (25, 19), (23, 16), "w")         # lower fang
    put(g, 14, 11, "N")                                    # nostril
    # reptilian eye (yellow, vertical slit) + brow
    ellipse(g, 35, 11, 2, 2, "y"); vline(g, 35, 10, 12, "N")
    line(g, 31, 7, 40, 6, "G")                             # brow ridge
    # swept-back horns (bone)
    thick_line(g, 37, 5, 52, 1, "w", 2)
    thick_line(g, 41, 5, 53, 4, "w", 2)
    # spiky frill / crest down the back of the head (right edge)
    for hx, hy in ((52, 9), (54, 14), (53, 19), (49, 24)):
        fill_tri(g, (46, hy - 2), (46, hy + 2), (hx, hy), "G")
    # scaly neck curving down to the lower-right
    thick_line(g, 45, 23, 52, 29, "g", 7)
    ellipse(g, 51, 28, 7, 3, "g")
    for sx in range(30, 47, 4):                            # belly scale shading
        put(g, sx, 23, "G")
    write("dragon", g)


# ---------------------------------------------------------------- FAIRY (Droomvlucht)
def fairy():
    g = grid()
    cx = 28
    # translucent butterfly wings spread behind (light blue)
    fill_tri(g, (cx, 15), (cx - 16, 6), (cx - 8, 16), ":")     # upper-left wing
    fill_tri(g, (cx, 15), (cx - 13, 22), (cx - 5, 17), ":")    # lower-left wing
    fill_tri(g, (cx, 15), (cx + 16, 6), (cx + 8, 16), ":")     # upper-right wing
    fill_tri(g, (cx, 15), (cx + 13, 22), (cx + 5, 17), ":")    # lower-right wing
    ring(g, cx - 9, 10, 6, "~", cond=lambda x, y: x < cx)      # wing edge glow
    ring(g, cx + 9, 10, 6, "~", cond=lambda x, y: x > cx)
    # little figure: head + triangular dress
    ellipse(g, cx, 8, 2, 2, "w")                   # head (skin)
    ellipse(g, cx, 6, 2, 2, "o")                   # hair
    for y in range(11, 19):                         # dress (pink/red gown)
        hw = int(1 + (y - 11) * 0.7)
        hline(g, cx - hw, cx + hw, y, "r")
    line(g, cx - 1, 11, cx - 5, 14, "w"); line(g, cx + 1, 11, cx + 6, 9, "w")   # arms
    vline(g, cx - 1, 19, 22, "w"); vline(g, cx + 1, 19, 22, "w")                # legs
    # wand with a gold star sparkle + a trail of fairy dust
    put(g, cx + 6, 9, "o")
    for sx, sy in ((48, 7), (53, 11), (44, 14), (57, 16), (50, 19), (40, 5)):
        put(g, sx, sy, "y"); put(g, sx + 1, sy, "o")
    put(g, cx + 6, 8, "#"); put(g, cx + 7, 9, "#"); put(g, cx + 5, 9, "#")      # star points
    write("fairy", g)


# ================================================================ BATCH 10 (Chessington)
# ---------------------------------------------------------------- CROCODILE (Croc Drop)
def crocodile():
    g = grid()
    # long jaws (left), upper + lower with a mouth gap + teeth
    rect(g, 3, 15, 28, 17, "g")                    # upper jaw
    rect(g, 6, 20, 28, 22, "g")                    # lower jaw
    put(g, 5, 15, "N")                             # nostril at the snout tip
    for tx in range(8, 27, 3):                     # white fangs ringing the mouth
        put(g, tx, 18, "w"); put(g, tx, 19, "w")
    # head + eye bump on top
    ellipse(g, 32, 17, 8, 6, "g")
    ellipse(g, 30, 11, 3, 2, "g"); put(g, 30, 10, "y"); put(g, 30, 11, "N")
    # body + thick tapering tail to the right
    ellipse(g, 46, 18, 12, 6, "g")
    for x in range(56, 64):
        t = (x - 56) / 7.0
        h = int(5 * (1 - t))
        vline(g, x, 18 - h, 18 + h, "g")
    # ridged back scutes (dark-green triangles along the spine)
    for sx in range(28, 60, 5):
        fill_tri(g, (sx, 13), (sx + 3, 13), (sx + 1, 10), "G")
    # FOUR clawed legs sticking down (a fish has none -> breaks the fish read)
    for lx in (34, 41, 50, 57):
        rect(g, lx, 23, lx + 1, 27, "g")
        for c in (-1, 0, 1):
            put(g, lx + c, 28, "G")                # 3-toe foot
    write("crocodile", g)


# ---------------------------------------------------------------- WITCH ON A BROOM (Room on the Broom)
def witch():
    g = grid()
    # crescent moon behind (upper right)
    ellipse(g, 53, 8, 7, 7, "o"); ellipse(g, 50, 7, 6, 6, " ")
    # broomstick handle (lower-left up to the right) + bristles
    thick_line(g, 6, 26, 46, 15, "n", 2)
    for i in range(-4, 5):
        line(g, 7, 26, 1, 25 + i, "y")
    # witch: flowing cloak (purple), face, pointy hat, arm to the broom
    fill_tri(g, (26, 11), (32, 23), (18, 23), ":")     # cloak
    ellipse(g, 26, 9, 2, 2, "w")                       # face
    fill_tri(g, (21, 6), (31, 6), (25, 0), "S")        # pointy hat
    rect(g, 19, 6, 32, 7, "S")                         # hat brim
    line(g, 27, 12, 36, 16, "w")                       # arm reaching to the broom
    write("witch", g)


# ---------------------------------------------------------------- BAT (Vampire)
def bat():
    g = grid()
    cx = 32
    # body + head with two pointed ears (the bat tell) + red vampire eyes
    ellipse(g, cx, 16, 3, 5, "S")
    ellipse(g, cx, 10, 3, 3, "S")
    fill_tri(g, (cx - 3, 10), (cx - 1, 10), (cx - 2, 5), "S")
    fill_tri(g, (cx + 1, 10), (cx + 3, 10), (cx + 2, 5), "S")
    put(g, cx - 1, 10, "r"); put(g, cx + 1, 10, "r")
    # spread wings with a SCALLOPED trailing edge (vs the eagle's feathered one)
    fill_tri(g, (cx - 3, 13), (3, 7), (12, 20), "S")           # left membrane
    fill_tri(g, (cx + 3, 13), (61, 7), (52, 20), "S")          # right membrane
    fill_tri(g, (cx - 3, 14), (10, 19), (20, 21), "S")
    fill_tri(g, (cx + 3, 14), (54, 19), (44, 21), "S")
    for bx in (5, 9, 14, 19):                                  # finger bones (left)
        line(g, cx - 4, 14, bx, 7 + (bx % 3) + (19 - bx) // 2, "S")
    for sx, sy in ((9, 20), (16, 21), (23, 21)):               # scallop notches (left)
        ellipse(g, sx, sy + 1, 2, 2, " ")
    for sx, sy in ((55, 20), (48, 21), (41, 21)):              # scallop notches (right)
        ellipse(g, sx, sy + 1, 2, 2, " ")
    write("bat", g)


# ---------------------------------------------------------------- FIRETRUCK (Marshall)
def firetruck():
    g = grid()
    rect(g, 5, 15, 57, 24, "r")                    # red body
    rect(g, 44, 10, 57, 16, "r")                   # cab
    rect(g, 46, 11, 55, 15, ":")                   # windshield
    hline(g, 5, 44, 19, "w"); hline(g, 5, 44, 20, "w")        # white side stripe
    # silver extension ladder along the top
    line(g, 8, 13, 42, 8, "s"); line(g, 9, 15, 43, 10, "s")
    for k in range(0, 34, 4):
        line(g, 8 + k, 13 - k * 5 // 34, 9 + k, 15 - k * 5 // 34, "S")   # rungs
    put(g, 50, 8, "y"); put(g, 50, 7, "r")         # roof beacon
    for wx in (16, 47):                            # wheels
        ellipse(g, wx, 25, 4, 4, "N"); ellipse(g, wx, 25, 2, 2, "s")
    write("firetruck", g)


# ---------------------------------------------------------------- HELICOPTER (Skye)
def helicopter():
    g = grid()
    hline(g, 7, 57, 6, "s"); hline(g, 7, 57, 7, "s")          # main rotor blades
    vline(g, 32, 7, 11, "S")                       # rotor mast
    ellipse(g, 26, 17, 11, 7, "r")                 # body
    ellipse(g, 21, 16, 5, 4, ":")                  # cockpit bubble
    rect(g, 35, 15, 57, 18, "r")                   # tail boom
    fill_tri(g, (53, 10), (59, 11), (57, 17), "r") # tail fin
    line(g, 57, 10, 57, 15, "S"); line(g, 55, 12, 59, 12, "S")   # tail rotor
    hline(g, 17, 39, 26, "S")                      # landing skid
    vline(g, 22, 23, 26, "S"); vline(g, 34, 23, 26, "S")
    write("helicopter", g)


# ---------------------------------------------------------------- TIGER (Tiger Rock)
def tiger():
    g = grid()
    cx = 32
    # ears
    ellipse(g, cx - 11, 8, 4, 4, "o"); ellipse(g, cx + 11, 8, 4, 4, "o")
    ellipse(g, cx - 11, 9, 2, 2, "N"); ellipse(g, cx + 11, 9, 2, 2, "N")
    # orange face
    ellipse(g, cx, 17, 13, 12, "o")
    # white muzzle + brow patches
    ellipse(g, cx, 22, 8, 5, "w")
    ellipse(g, cx - 5, 13, 3, 2, "w"); ellipse(g, cx + 5, 13, 3, 2, "w")
    # bold black stripes (forehead + cheeks)
    for dx in (-2, 0, 2):
        vline(g, cx + dx, 6, 11, "N")
    for sx in (-12, -9, 9, 12):
        line(g, cx + sx, 15, cx + sx + (1 if sx < 0 else -1) * 3, 20, "N")
    # eyes + nose + mouth
    ellipse(g, cx - 5, 14, 1, 2, "N"); ellipse(g, cx + 5, 14, 1, 2, "N")
    fill_tri(g, (cx - 2, 19), (cx + 2, 19), (cx, 21), "r")
    vline(g, cx, 21, 23, "N"); put(g, cx - 2, 24, "N"); put(g, cx + 2, 24, "N")
    write("tiger", g)


# ---------------------------------------------------------------- MONKEY / MANDRILL (Mandrill Mayhem)
def monkey():
    g = grid()
    cx = 32
    # big round ears
    ellipse(g, cx - 12, 15, 5, 5, "n"); ellipse(g, cx + 12, 15, 5, 5, "n")
    ellipse(g, cx - 12, 15, 3, 3, "w"); ellipse(g, cx + 12, 15, 3, 3, "w")
    # brown head + tan face
    ellipse(g, cx, 15, 11, 10, "n")
    ellipse(g, cx, 18, 8, 8, "w")
    ellipse(g, cx, 8, 6, 3, "n")                   # brow/fur crown
    # eyes, nose pad, mouth (clean monkey — no cheek streaks, which read as tears)
    ellipse(g, cx - 3, 13, 1, 2, "N"); ellipse(g, cx + 3, 13, 1, 2, "N")
    ellipse(g, cx, 19, 2, 1, "n")                  # nose pad
    put(g, cx - 1, 19, "N"); put(g, cx + 1, 19, "N")   # nostrils
    put(g, cx - 4, 22, "N"); put(g, cx + 4, 22, "N")
    for x in range(cx - 3, cx + 4):                # smile
        put(g, x, 23, "N")
    write("monkey", g)


# ---------------------------------------------------------------- OSTRICH (Ostrich Stampede)
# Split into body + legs so the walk-cycle spritesheet (ostrich_walk_sheet) can reuse a
# pixel-identical body across frames and vary ONLY the legs. The legs attach at fixed hips
# under the body; a pose is just the two foot positions.
_OSTRICH_HIP_L, _OSTRICH_HIP_R, _OSTRICH_HIP_Y = 25, 31, 21


def _ostrich_body(g):
    """Everything but the legs — identical in every walk frame (no jitter)."""
    ellipse(g, 27, 15, 11, 7, "S")                 # round body of dark plumes
    ellipse(g, 26, 18, 5, 3, "w")                  # folded white wing (low/central)
    ellipse(g, 18, 16, 4, 3, "w")                  # white tail tuft (rear, left)
    # very long thin S-neck to a SMALL head (tiny beak -> not a toucan)
    nk = ((36, 11), (43, 7), (48, 4), (51, 3))
    for i in range(len(nk) - 1):
        thick_line(g, nk[i][0], nk[i][1], nk[i + 1][0], nk[i + 1][1], "w", 2)
    ellipse(g, 52, 3, 2, 2, "w")                   # small head
    put(g, 54, 3, "o")                             # tiny beak
    put(g, 52, 2, "N")                             # eye


def _ostrich_legs(g, lf, rf):
    """Two long thick legs from the fixed hips to feet ``lf``/``rf`` (each an (x, y)),
    with splayed gold feet. A lifted foot (y < 31) draws a shorter, raised leg."""
    thick_line(g, _OSTRICH_HIP_L, _OSTRICH_HIP_Y, lf[0], lf[1], "w", 2)
    thick_line(g, _OSTRICH_HIP_R, _OSTRICH_HIP_Y, rf[0], rf[1], "w", 2)
    for (fx, fy) in (lf, rf):
        put(g, fx - 1, fy, "o")
        put(g, fx + 1, fy, "o")


def ostrich():
    g = grid()
    _ostrich_body(g)
    _ostrich_legs(g, (22, 31), (34, 31))           # static splayed stance (unchanged art)
    write("ostrich", g)


# One walk cycle, 4 frames (each = one foot pair). Travel is L->R (+x): each leg plants a
# foot forward, drags it BACKWARD relative to the body through 3 planted frames, then LIFTS
# (y=29) and swings forward — so the planted foot reads as staying put on the ground while
# the sprite translates right (no "moonwalk"). The two legs run 180 deg out of phase:
# left lifts on frame 3, right lifts on frame 1; frames 0 and 2 are double-support (both down).
_OSTRICH_WALK_POSES = [
    ((28, 31), (30, 31)),   # f0 double-support: left plants forward, right planted back
    ((25, 31), (33, 29)),   # f1 right lifts + swings forward, left drags back
    ((22, 31), (36, 31)),   # f2 double-support: right plants forward, left dragged back
    ((26, 29), (33, 31)),   # f3 left lifts + swings forward, right drags back
]


def ostrich_walk_sheet():
    """Write the ostrich walk-cycle spritesheet: a horizontal strip of the 4 poses (one
    palette, sky=index 0) to src/images/rides/ostrich_walk.bmp, consumed by CelWalkAnimator."""
    grids = []
    for lf, rf in _OSTRICH_WALK_POSES:
        g = grid()
        _ostrich_body(g)
        _ostrich_legs(g, lf, rf)
        grids.append(g)
    write_sheet("ostrich_walk", grids)


# ================================================================ BATCH 11 (worldwide Disney)
# ---------------------------------------------------------------- IRON MAN (helmet)
def iron_man():
    g = grid()
    cx = 32

    # red helmet silhouette, front view: domed crown, wide temples, jaw to a chin
    def hw_at(y):
        if y < 7:
            return int(4 + (y - 3) * 1.7)              # 4..10 dome
        if y < 15:
            return 11                                  # temples / cheeks (widest)
        if y < 23:
            return int(11 - (y - 15) * 0.5)            # taper down the face
        return max(3, int(7 - (y - 23) * 0.8))         # jaw -> pointed chin
    for y in range(3, 29):
        hline(g, cx - hw_at(y), cx + hw_at(y), y, "r")
    # gold faceplate down the centre (red temples + red crown remain)
    for y in range(9, 28):
        if y < 12:
            fw = (y - 9) * 2 + 2
        elif y < 16:
            fw = 8
        else:
            fw = max(3, int(8 - (y - 16) * 0.6))
        hline(g, cx - fw, cx + fw, y, "o")
    # angry brow notch + faint mouth vents on the plate
    hline(g, cx - 3, cx + 3, 11, "r")
    for vy in (22, 24):
        hline(g, cx - 4, cx + 4, vy, "r")
    # the tell: two glowing eye slits, slanting down toward the nose
    for i in range(6):
        put(g, cx - 9 + i, 13 + i // 2, "#")
        put(g, cx + 9 - i, 13 + i // 2, "#")
    write("iron_man", g)


# ---------------------------------------------------------------- SNOWFLAKE (Frozen)
def snowflake():
    g = grid()
    cx, cy, R = 32, 16, 13
    for k in range(6):                                 # six-fold symmetry
        a = math.radians(60 * k)
        ca, sa = math.cos(a), math.sin(a)
        ex, ey = round(cx + R * ca), round(cy + R * sa)
        thick_line(g, cx, cy, ex, ey, "~", 2)          # main spine (icy blue)
        for frac, blen in ((0.5, 4), (0.74, 3)):       # paired side branches
            bx, by = cx + R * frac * ca, cy + R * frac * sa
            for da in (55, -55):
                a2 = a + math.radians(da)
                line(g, round(bx), round(by),
                     round(bx + blen * math.cos(a2)),
                     round(by + blen * math.sin(a2)), "#")
        put(g, ex, ey, "#")                            # bright tip
    ellipse(g, cx, cy, 2, 2, "#")                      # hub
    ellipse(g, cx, cy, 1, 1, ":")
    write("snowflake", g)


# ---------------------------------------------------------------- SLINKY DOG (Toy Story)
def slinky_dog():
    g = grid()
    # front end: dachshund head + long snout facing left
    ellipse(g, 15, 14, 6, 5, "n")                      # head
    rect(g, 4, 14, 15, 17, "n")                        # long snout
    put(g, 4, 16, "N")                                 # black nose at the tip
    ellipse(g, 12, 9, 3, 4, "n")                       # floppy ear
    put(g, 17, 11, "#"); put(g, 17, 12, "N")           # eye + pupil
    put(g, 20, 11, "#"); put(g, 20, 12, "N")           # second eye
    vline(g, 21, 13, 19, "r")                          # red collar
    rect(g, 11, 19, 13, 27, "n"); rect(g, 17, 19, 19, 27, "n")   # front legs
    put(g, 11, 27, "N"); put(g, 18, 27, "N")           # paws
    # the Slinky spring body: a row of grey coil rings
    for sx in range(24, 47, 3):
        ellipse(g, sx, 17, 2, 5, "s")
        vline(g, sx + 2, 13, 21, "S")                  # darker back edge of each coil
    # rear end: haunch + back legs + tail
    ellipse(g, 52, 15, 6, 6, "n")
    rect(g, 49, 20, 51, 28, "n"); rect(g, 55, 20, 57, 28, "n")   # back legs
    put(g, 49, 28, "N"); put(g, 57, 28, "N")
    thick_line(g, 57, 12, 62, 6, "n", 2)               # tail up
    write("slinky_dog", g)


# ---------------------------------------------------------------- TOWER OF TERROR (Hollywood Tower Hotel)
def tower_of_terror():
    g = grid()
    for sx, sy in ((50, 4), (56, 10), (12, 13), (46, 2)):       # night stars
        put(g, sx, sy, "*")
    # tan tiered hotel: base block, main shaft, setback tier, rooftop box
    rect(g, 16, 24, 48, 31, "w")
    rect(g, 22, 8, 42, 31, "w")
    rect(g, 26, 4, 38, 9, "w")
    rect(g, 29, 1, 35, 4, "w")
    rect(g, 43, 24, 48, 31, "s")                       # shaded right wing
    for yy in range(8, 31):
        put(g, 41, yy, "s")                            # shaded right face
    hline(g, 22, 42, 8, "o"); hline(g, 16, 48, 24, "o")         # cornice trim
    lit = {(0, 1), (1, 3), (2, 0), (3, 2)}             # a few lit windows
    for r in range(4):
        for c in range(4):
            wx, wy = 25 + c * 4, 11 + r * 3
            rect(g, wx, wy, wx + 1, wy + 1, "y" if (r, c) in lit else "S")
    ellipse(g, 32, 30, 3, 2, "N"); rect(g, 30, 28, 34, 31, "N")  # entrance arch
    # (the old left-side lightning bolt never read at LED scale — removed; the
    # pulsing lit windows carry the Twilight Zone menace on their own)
    write("tower_of_terror", g)


# ---------------------------------------------------------------- POISON APPLE (Snow White)
def poison_apple():
    g = grid()
    cx, cy = 32, 18
    # apple body with the classic top dimple
    ellipse(g, cx, cy, 10, 8, "r")
    for dx in (-1, 0, 1):
        put(g, cx + dx, cy - 8, " ")
        put(g, cx + dx, cy - 7, " ")
    # stem into the dimple + leaf
    vline(g, cx, 7, 11, "N")
    ellipse(g, cx + 5, 8, 3, 1, "g")
    hline(g, cx + 3, cx + 7, 9, "G")
    # specular gleam upper-left (glassy skin)
    put(g, cx - 6, 13, "#"); put(g, cx - 5, 12, "#"); put(g, cx - 5, 13, "#")
    # the POISON: sickly light-green ooze running down the right side, dripping off
    put(g, cx + 4, 21, "L"); put(g, cx + 5, 21, "L")
    vline(g, cx + 5, 22, 27, "L")
    put(g, cx + 5, 29, "L")                        # falling drop below the skin
    write("poison_apple", g)


# ---------------------------------------------------------------- INDIANA JONES (fedora + whip)
def indiana_hat():
    g = grid()
    cx = 28
    # fedora crown: a creased "teardrop" — TAPERED (narrower on top than the base) with a
    # mostly flat top, NOT a smooth dome (the dome read as a turtle shell).
    for y in range(7, 16):
        t = (y - 7) / 8.0
        hw = int(6 + 4 * t)                            # 6 (top) -> 10 (base)
        hline(g, cx - hw, cx + hw, y, "n")
    hline(g, cx - 5, cx + 5, 6, "n")                   # flat-ish crown top
    # centre crease + two pinch dents — the fedora tell that breaks the shell read
    vline(g, cx, 6, 11, "N")
    vline(g, cx - 4, 6, 9, "N"); vline(g, cx + 4, 6, 9, "N")
    # dark hat band + a little gold buckle
    hline(g, cx - 10, cx + 10, 14, "N"); hline(g, cx - 10, cx + 10, 15, "N")
    put(g, cx - 6, 14, "o"); put(g, cx - 6, 15, "o")
    # wide snap brim: the dominant horizontal element, front edge dipped down in the middle
    ellipse(g, cx, 17, 19, 2, "n")
    for x in range(cx - 12, cx + 13):
        d = 1.0 - abs(x - cx) / 13.0
        if d > 0:
            vline(g, x, 17, 17 + int(3 * d), "n")
    ellipse(g, cx, 18, 17, 1, "N")                     # underbrim shadow
    put(g, cx - 19, 18, "n"); put(g, cx + 19, 18, "n")  # turned-down brim tips
    # coiled bullwhip, lower-right: ONE loose loop + a long cracking lash (not a snail spiral)
    ring(g, 52, 27, 4, "n")
    ellipse(g, 52, 27, 1, 1, "N")
    lash = ((55, 24), (59, 22), (61, 17), (58, 12), (62, 7))
    for i in range(len(lash) - 1):
        line(g, lash[i][0], lash[i][1], lash[i + 1][0], lash[i + 1][1], "n")
    write("indiana_hat", g)


# ---------------------------------------------------------------- MOUNTAIN + FALLS (Tiana's / Splash Mountain)
def mountain_falls():
    g = grid()
    cx, peak = 32, 5
    # idealized green mountain: a bold symmetric peak filling the panel to the base
    for y in range(peak, 31):
        t = (y - peak) / (30 - peak)
        hw = int(2 + 28 * t)
        hline(g, cx - hw, cx + hw, y, "g")
        for x in range(cx + hw - 4, cx + hw + 1):      # shaded right flank
            put(g, x, y, "G")
    line(g, cx, peak, cx - 16, 30, "G")                # ridge lines -> reads "mountain"
    line(g, cx, peak, cx + 16, 30, "G")
    for rx, ry in ((cx - 9, 12), (cx + 9, 14), (cx - 13, 20)):   # rocky texture flecks
        put(g, rx, ry, "G")
    # GIANT waterfall: a sheet pouring over the summit lip and fanning out to the pool.
    # Monotonic widening + horizontal cascade ripples so it reads as falling WATER, not a
    # tower (gemini called the old narrow-waisted column a "Space Needle").
    put(g, cx, peak - 1, "#")                          # water cresting the summit
    for y in range(peak, 30):
        t = (y - peak) / (30 - peak)
        w = int(2 + 5 * t)                             # narrow at top -> wide at base
        hline(g, cx - w, cx + w, y, "#")               # white water sheet
        put(g, cx - w, y, "~"); put(g, cx + w, y, "~")  # cyan edges
        if (y - peak) % 3 == 1:                        # horizontal cascade ripples
            hline(g, cx - w + 1, cx + w - 1, y, "~")
    ellipse(g, cx, 30, 13, 2, "~")                     # splash pool at the base
    for fx in (cx - 9, cx - 4, cx + 4, cx + 9):        # foam crests on the pool
        put(g, fx, 29, "#")
    for sx, sy in ((cx - 7, 13), (cx + 8, 17), (cx - 9, 22), (cx + 10, 25)):  # spray
        put(g, sx, sy, "#")
    write("mountain_falls", g)


# ================================================================ BATCH 12 (Universal)
# ---------------------------------------------------------------- MINION (Despicable Me)
def minion():
    g = grid()
    cx = 32
    for hx in (29, 32, 35):                        # a few stray hairs
        vline(g, hx, 1, 3, "K")
    line(g, 28, 3, 27, 1, "K"); line(g, 36, 3, 37, 1, "K")
    # yellow capsule body (rounded top + straight sides + rounded bottom)
    ellipse(g, cx, 11, 11, 7, "y", half="top")
    rect(g, cx - 11, 11, cx + 11, 25, "y")
    ellipse(g, cx, 25, 11, 6, "y", half="bottom")
    # single big goggle: dark strap band, silver rim, black rim, white eye, iris, pupil
    rect(g, cx - 12, 9, cx + 12, 12, "S")
    ellipse(g, cx, 11, 7, 7, "S")
    ellipse(g, cx, 11, 6, 6, "s")
    ellipse(g, cx, 11, 5, 5, "K")
    ellipse(g, cx, 11, 4, 4, "#")
    ellipse(g, cx, 11, 2, 2, "n")
    put(g, cx, 11, "K")
    put(g, cx - 1, 10, "#")                        # catch-light
    hline(g, cx - 3, cx + 3, 20, "K")              # smile
    put(g, cx - 4, 19, "K"); put(g, cx + 4, 19, "K")
    # blue overalls: bottom band + rounded hem + shoulder straps up the sides
    ellipse(g, cx, 25, 11, 6, ":", half="bottom")
    rect(g, cx - 11, 23, cx + 11, 25, ":")
    line(g, cx - 7, 23, cx - 9, 13, ":"); line(g, cx + 7, 23, cx + 9, 13, ":")
    put(g, cx - 1, 23, "K"); put(g, cx + 1, 23, "K")   # pocket studs
    put(g, cx - 5, 31, "K"); put(g, cx - 4, 31, "K")   # feet
    put(g, cx + 4, 31, "K"); put(g, cx + 5, 31, "K")
    write("minion", g)


# ---------------------------------------------------------------- DINOSAUR (Jurassic / T-rex)
def dinosaur():
    g = grid()
    thick_line(g, 3, 27, 20, 20, "g", 4)           # tail up into the body
    thick_line(g, 20, 20, 30, 18, "g", 8)
    ellipse(g, 32, 18, 11, 8, "g")                 # body
    for sx in range(22, 46, 4):                    # back-ridge spikes
        fill_tri(g, (sx, 11), (sx + 3, 11), (sx + 1, 8), "G")
    thick_line(g, 40, 15, 48, 9, "g", 6)           # neck
    ellipse(g, 52, 9, 8, 5, "g")                   # head
    rect(g, 50, 6, 61, 10, "g")                    # upper snout
    rect(g, 50, 12, 60, 14, "g")                   # lower jaw
    hline(g, 51, 60, 11, "r")                      # red mouth
    for tx in range(51, 61, 2):
        put(g, tx, 10, "#")                        # upper teeth
    for tx in range(52, 60, 2):
        put(g, tx, 12, "#")                        # lower teeth
    put(g, 55, 7, "y"); put(g, 56, 7, "K")         # eye
    put(g, 60, 8, "G")                             # nostril
    line(g, 41, 19, 45, 22, "g"); put(g, 46, 23, "w")   # tiny arm
    rect(g, 26, 24, 30, 30, "g"); rect(g, 36, 24, 40, 30, "g")   # legs
    for fx in (24, 26, 28):
        put(g, fx, 31, "w")                        # clawed feet
    for fx in (36, 38, 40):
        put(g, fx, 31, "w")
    write("dinosaur", g)


# ---------------------------------------------------------------- TRANSFORMERS (Optimus Prime head)
def transformers():
    g = grid()
    cx = 32
    fill_tri(g, (cx, 2), (cx - 2, 8), (cx + 2, 8), "s")   # crest fin
    vline(g, cx, 2, 8, "#")
    line(g, 24, 9, 21, 4, ":"); line(g, 25, 9, 22, 4, ":")   # antennae
    line(g, 40, 9, 43, 4, ":"); line(g, 39, 9, 42, 4, ":")
    ellipse(g, cx, 12, 11, 7, ":", half="top")     # blue helmet crown
    rect(g, cx - 11, 12, cx + 11, 15, ":")
    rect(g, cx - 12, 13, cx - 9, 22, "s")          # side head panels
    rect(g, cx + 9, 13, cx + 12, 22, "s")
    hline(g, cx - 9, cx + 9, 15, "S")              # brow shadow
    rect(g, cx - 8, 16, cx - 3, 18, "~")           # glowing eyes
    rect(g, cx + 3, 16, cx + 8, 18, "~")
    put(g, cx - 6, 16, "#"); put(g, cx + 6, 16, "#")
    rect(g, cx - 9, 19, cx + 9, 26, "s")           # silver faceplate / mouth guard
    for gx in (cx - 5, cx, cx + 5):
        vline(g, gx, 20, 25, "S")
    hline(g, cx - 9, cx + 9, 22, "S")              # mouth line
    ellipse(g, cx, 26, 9, 3, "s", half="bottom")   # chin
    write("transformers", g)


# ---------------------------------------------------------------- MUMMY (Revenge of the Mummy — sarcophagus)
def mummy():
    g = grid()
    cx = 32
    ellipse(g, cx, 8, 13, 6, "o", half="top")      # gold coffin, rounded top
    for y in range(8, 30):
        t = (y - 8) / 21.0
        hw = int(13 - 3 * t)
        hline(g, cx - hw, cx + hw, y, "o")
    hline(g, cx - 11, cx + 11, 5, ":")             # headband
    for y in range(6, 16):                         # nemes side lappets (blue/gold stripes)
        put(g, cx - 10, y, ":"); put(g, cx - 9, y, "o"); put(g, cx - 8, y, ":")
        put(g, cx + 10, y, ":"); put(g, cx + 9, y, "o"); put(g, cx + 8, y, ":")
    ellipse(g, cx, 11, 6, 6, "w")                  # cream face
    put(g, cx - 3, 10, "K"); put(g, cx + 3, 10, "K")           # eyes
    line(g, cx - 3, 10, cx - 6, 10, "K"); line(g, cx + 3, 10, cx + 6, 10, "K")   # kohl tails
    vline(g, cx, 11, 13, "n"); hline(g, cx - 2, cx + 2, 14, "r")   # nose + mouth
    for y in range(16, 22):                        # striped false beard
        put(g, cx - 1, y, ":"); put(g, cx, y, "o"); put(g, cx + 1, y, ":")
    for r, ch in ((7, ":"), (6, "o"), (5, ":")):   # broad collar arcs
        ring(g, cx, 17, r, ch, cond=lambda x, y: 17 <= y <= 24)
    hline(g, cx - 9, cx + 9, 25, ":"); hline(g, cx - 8, cx + 8, 26, "r")   # crossed-arm bands
    hline(g, cx - 9, cx + 9, 27, "o")
    write("mummy", g)


# ---------------------------------------------------------------- PANDA (Kung Fu Panda — Po)
def panda():
    g = grid()
    cx, cy = 32, 16
    ellipse(g, cx - 11, 6, 5, 5, "K"); ellipse(g, cx + 11, 6, 5, 5, "K")   # black ears
    ellipse(g, cx, cy, 13, 12, "#")                # white face
    ellipse(g, cx - 6, 15, 4, 5, "K"); ellipse(g, cx + 6, 15, 4, 5, "K")   # eye patches
    ellipse(g, cx - 6, 15, 2, 2, "#"); ellipse(g, cx + 6, 15, 2, 2, "#")   # eyeballs
    put(g, cx - 6, 16, "K"); put(g, cx + 6, 16, "K")           # pupils
    ellipse(g, cx, 20, 2, 1, "K")                  # nose
    line(g, cx, 21, cx - 3, 23, "K"); line(g, cx, 21, cx + 3, 23, "K")     # mouth
    write("panda", g)


# ---------------------------------------------------------------- DONUT (The Simpsons Ride)
def donut():
    g = grid()
    cx, cy = 32, 16
    outer, inner = 14, 5
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - cx, (y - cy) * 1.05)
            if inner <= d <= outer:
                drip = 3 + 2 * math.sin(x * 0.7)   # drippy lower edge of the frosting
                put(g, x, y, "p" if y <= cy + drip else "n")
    spr = [(24, 8, "r"), (30, 6, "y"), (37, 8, ":"), (41, 12, "g"),
           (22, 13, "o"), (43, 16, "r"), (26, 18, ":"), (34, 9, "#"),
           (39, 19, "y"), (20, 11, "g")]           # sprinkles
    for sx, sy, ch in spr:
        put(g, sx, sy, ch); put(g, sx + 1, sy, ch)
    write("donut", g)


# ---------------------------------------------------------------- SHARK (JAWS)
def shark():
    g = grid()
    ellipse(g, 32, 16, 20, 7, "s")                 # torpedo body, head to the right
    for y in range(16, 24):                        # white belly
        for x in range(12, 52):
            if g[y][x] == "s":
                put(g, x, y, "w")
    for y in range(9, 15):                          # darker back
        for x in range(12, 52):
            if g[y][x] == "s":
                put(g, x, y, "S")
    fill_tri(g, (26, 9), (34, 9), (30, 2), "S")    # dorsal fin
    fill_tri(g, (30, 22), (38, 22), (30, 29), "s") # pectoral fin
    fill_tri(g, (12, 16), (4, 8), (7, 16), "S")    # tail fin (upper lobe)
    fill_tri(g, (12, 16), (4, 24), (7, 16), "s")   # tail fin (lower lobe)
    for gx in (40, 42, 44):                         # gills
        vline(g, gx, 13, 19, "S")
    fill_tri(g, (50, 11), (62, 13), (52, 16), "s") # upper jaw
    fill_tri(g, (51, 15), (61, 15), (53, 19), "r") # red mouth interior
    fill_tri(g, (51, 19), (60, 17), (52, 21), "w") # lower jaw
    for tx in range(52, 61, 2):
        put(g, tx, 15, "#")                        # upper teeth
    for tx in range(53, 60, 2):
        put(g, tx, 17, "#")                        # lower teeth
    put(g, 46, 12, "K"); put(g, 47, 12, "K")       # eye
    write("shark", g)


# ---------------------------------------------------------------- YOSHI (Yoshi's Adventure — egg)
def yoshi():
    g = grid()
    cx, cy = 32, 17
    rx, ry = 12, 14
    ellipse(g, cx, cy, rx, ry, "#")                # white egg
    spots = [(22, 20), (30, 22), (39, 21), (26, 26), (35, 27), (43, 24), (21, 15)]
    for sx, sy in spots:                           # green diamond spots
        put(g, sx, sy, "g")
        put(g, sx - 1, sy, "g"); put(g, sx + 1, sy, "g")
        put(g, sx, sy - 1, "g"); put(g, sx, sy + 1, "g")
        put(g, sx - 1, sy + 1, "G"); put(g, sx + 1, sy + 1, "G")
    for y in range(H):                             # clip spots that fell outside the egg
        for x in range(W):
            if g[y][x] in ("g", "G"):
                dx = (x - cx) / rx; dy = (y - cy) / ry
                if dx * dx + dy * dy > 1.0:
                    put(g, x, y, " ")
    write("yoshi", g)


# ---------------------------------------------------------------- MOTORCYCLE + SIDECAR (Hagrid's)
def motorcycle():
    g = grid()

    def wheel(cx, cy, r):
        # hollow spoked wheel in visible grey (a solid black tire vanishes on the panel)
        ring(g, cx, cy, r, "s"); ring(g, cx, cy, r - 1, "S")     # 2-px tire
        for a in range(0, 360, 45):                             # spokes
            line(g, cx, cy, cx + round((r - 2) * math.cos(math.radians(a))),
                 cy + round((r - 2) * math.sin(math.radians(a))), "S")
        ellipse(g, cx, cy, 1, 1, "s")                           # hub

    rear, front = (15, 22), (44, 22)
    wheel(*rear, 8); wheel(*front, 8)
    # thin frame tubes between the hubs (kept clear of the wheel centres)
    thick_line(g, 15, 22, 27, 13, "S", 2)          # seat/rear tube
    thick_line(g, 44, 22, 36, 13, "S", 2)          # steering-head tube
    thick_line(g, 25, 22, 38, 22, "S", 2)          # bottom tube
    # compact engine block (between the wheels) with cooling fins
    rect(g, 26, 17, 34, 22, "s")
    for ex in range(27, 34, 2):
        vline(g, ex, 17, 22, "S")
    thick_line(g, 26, 21, 17, 25, "s", 2)          # exhaust sweeping to the rear
    # fuel tank (deep red) + glint
    ellipse(g, 25, 12, 5, 3, "r"); rect(g, 22, 12, 28, 14, "r")
    put(g, 23, 10, "#")
    # seat + tail
    rect(g, 29, 11, 38, 13, "K"); ellipse(g, 39, 12, 1, 1, "K")
    # fork + handlebars at the front
    thick_line(g, 44, 22, 48, 10, "S", 2)
    line(g, 47, 10, 52, 8, "S"); put(g, 52, 7, "S"); line(g, 47, 10, 44, 8, "S")
    ellipse(g, 50, 14, 2, 2, "o"); put(g, 51, 13, "y")          # headlight
    write("motorcycle", g)


# ================================================================ BATCH 13 (EPCOT / misc)
# ---------------------------------------------------------------- PYRAMID (Gran Fiesta Tour — Mexico pavilion)
def pyramid():
    g = grid()
    cx = 32
    # stepped stone tiers, narrowing upward (bottom -> top)
    tiers = [(26, 29, 23), (23, 26, 19), (20, 23, 15), (17, 20, 11), (14, 17, 8)]
    for (y0, y1, hw) in tiers:
        rect(g, cx - hw, y0, cx + hw, y1, "T")
        hline(g, cx - hw, cx + hw, y0, "n")        # setback shadow ledge under each step
    # temple on the summit: body, cornice, roof comb, dark doorway
    rect(g, cx - 6, 8, cx + 6, 14, "T")
    hline(g, cx - 7, cx + 7, 8, "n")               # cornice
    vline(g, cx, 6, 8, "n"); put(g, cx - 2, 7, "n"); put(g, cx + 2, 7, "n")   # roof comb
    rect(g, cx - 2, 10, cx + 2, 14, "N")           # temple doorway
    # grand central staircase down the front (lighter stone + step lines + balustrades)
    rect(g, cx - 3, 14, cx + 3, 29, "w")
    for sy in range(15, 29, 2):
        hline(g, cx - 3, cx + 3, sy, "n")
    vline(g, cx - 4, 14, 29, "S"); vline(g, cx + 4, 14, 29, "S")   # balustrade walls
    # jungle ground line
    hline(g, 3, 60, 30, "g"); rect(g, 3, 31, 60, 31, "G")
    write("pyramid", g)


# ---------------------------------------------------------------- CLOWNFISH (The Seas with Nemo)
def clownfish():
    g = grid()
    bcx, bcy = 30, 16                              # head to the left, tail to the right
    # tail fin (right) — overlaps the body so it reads as one silhouette
    fill_tri(g, (41, 16), (54, 8), (54, 24), "O")
    put(g, 53, 15, " "); put(g, 53, 16, " "); put(g, 53, 17, " ")   # forked notch
    # dorsal + anal fins
    fill_tri(g, (24, 9), (37, 9), (31, 4), "O")
    fill_tri(g, (26, 23), (37, 23), (32, 27), "O")
    # body
    ellipse(g, bcx, bcy, 15, 8, "O")
    # pectoral fin near the head
    fill_tri(g, (20, 18), (28, 18), (21, 24), "O")
    # three white bands with thin dark edges, painted onto the orange body
    def band(bx, w):
        for y in range(H):
            for x in range(bx - w, bx + w + 1):
                if 0 <= x < W and g[y][x] == "O":
                    g[y][x] = "#" if abs(x - bx) < w else "K"
    band(22, 2); band(31, 3); band(41, 2)
    # eye + mouth (head end, far left)
    ellipse(g, 18, 15, 2, 2, "#"); put(g, 18, 15, "K"); put(g, 17, 14, "#")
    hline(g, 14, 17, 18, "n")
    write("clownfish", g)


# ---------------------------------------------------------------- LIGHT BULB (Journey Into Imagination)
def light_bulb():
    g = grid()
    cx, cy = 32, 13
    for a in range(0, 360, 45):                    # radiating "idea" glow
        dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
        line(g, int(cx + 11 * dx), int(cy + 11 * dy),
             int(cx + 14 * dx), int(cy + 14 * dy), "y")
    ellipse(g, cx, cy, 9, 9, "y")                  # glass globe
    ellipse(g, cx, cy, 3, 3, "w")                  # white-hot core
    put(g, cx - 3, cy - 3, "#")                    # highlight
    fil = [(28, 16), (30, 11), (32, 15), (34, 11), (36, 16)]   # filament (orange M)
    for i in range(len(fil) - 1):
        line(g, fil[i][0], fil[i][1], fil[i + 1][0], fil[i + 1][1], "O")
    rect(g, 29, 21, 35, 22, "s")                   # neck
    rect(g, 28, 22, 36, 27, "s")                   # screw base
    for ty in (23, 25):
        hline(g, 28, 36, ty, "S")                  # threads
    rect(g, 30, 28, 34, 29, "S")                   # contact tip
    write("light_bulb", g)


# ---------------------------------------------------------------- CASSETTE (Guardians: Cosmic Rewind — Awesome Mix)
def cassette():
    g = grid()
    rect(g, 15, 4, 49, 28, "S")                    # dark-plastic body (compact ~1.5:1)
    for cxx, cyy in ((15, 4), (49, 4), (15, 28), (49, 28)):
        put(g, cxx, cyy, " ")                      # rounded corners
    rect(g, 19, 6, 45, 13, "w")                    # label panel
    hline(g, 19, 45, 7, "r"); hline(g, 19, 45, 12, ":")   # two colour stripes
    for wx in (26, 38):                            # two reel windows
        rect(g, wx - 5, 16, wx + 5, 24, "K")       # dark window
        ellipse(g, wx, 20, 4, 3, "n")              # brown tape spool
        ellipse(g, wx, 20, 2, 2, "s")              # hub
        for a in range(0, 360, 60):                # spindle teeth
            put(g, wx + round(2 * math.cos(math.radians(a))),
                20 + round(2 * math.sin(math.radians(a))), "S")
    hline(g, 26, 38, 25, "n")                      # exposed tape between the reels
    put(g, 18, 26, "s"); put(g, 46, 26, "s")       # screws
    write("cassette", g)


# ---------------------------------------------------------------- AMERICAN FLAG (The American Adventure)
def flag():
    g = grid()
    vline(g, 6, 2, 31, "s"); ellipse(g, 6, 2, 1, 1, "o")       # pole + gold finial
    x0, x1, top = 8, 57, 4
    star_cols = {11, 15, 19, 23, 27}
    star_rows = {1, 4, 7}
    for x in range(x0, x1 + 1):
        wv = int(round(2 * math.sin((x - x0) * 0.32)))         # ripple = "waving"
        for row in range(18):
            col = "r" if (row // 2) % 2 == 0 else "#"          # 2-row stripes, starts/ends red
            if x <= 28 and row < 10:                           # blue canton (upper-left)
                col = "#" if (x in star_cols and row in star_rows) else ":"
            put(g, x, top + row + wv, col)
    write("flag", g)


# ---------------------------------------------------------------- WAVES (generic water ride)
def waves():
    g = grid()
    # three stacked wavy ribbons, lighter at the top -> darker below, phase-shifted so
    # they read as a series of rolling waves (a generic "water ride" mark).
    for col, ph, base in (("~", 0.0, 8), (":", 1.2, 16), ("+", 2.4, 24)):
        for x in range(2, W - 2):
            y = base + int(round(2.0 * math.sin(x / 4.0 + ph)))
            put(g, x, y, col); put(g, x, y + 1, col)          # 2-px ribbon
    # white foam caps on the crests of the top wave
    for x in range(2, W - 2):
        s = math.sin(x / 4.0)
        if s < -0.8:
            put(g, x, 8 + int(round(2.0 * s)) - 1, "#")
    write("waves", g)


# ---------------------------------------------------------------- ROCK 'N' ROLLER COASTER
# A single Gibson Les Paul: single-cutaway solid body, cream binding, twin humbuckers,
# open-book headstock. The body is one flat fill ("R"); the rich pass paints the cherry
# sunburst onto it with a radial light (bright amber centre -> dark edge). Materials map
# to shared ramps in gen_rich_icons.rock_roller(): R=sunburst top, w=cream binding/
# pickguard/inlays, N=rosewood fretboard, s=steel frets/strings/bridge, K=ink
# (humbuckers/headstock), o=gold (tuners/knobs/pole pieces).
def rock_roller():
    g = grid()
    cy = 16                                      # horizontal centre line
    # Drawn STRAIGHT-ON (not in perspective): headstock left, neck across, body face-on
    # right, symmetric about cy. Reads far better than a 3/4 angle at 64x32.
    # ---- Open-book headstock + 3+3 gold tuners ----
    ellipse(g, 4, cy, 3, 4, "K")                 # black headstock plate
    put(g, 1, cy - 1, "K"); put(g, 1, cy + 1, "K")
    for ty in (cy - 5, cy + 5):                  # gold tuners, 3 per side
        put(g, 2, ty, "o"); put(g, 4, ty, "o"); put(g, 6, ty, "o")
    # ---- Neck / rosewood fretboard (horizontal) ----
    rect(g, 8, cy - 3, 30, cy + 3, "N")          # fretboard, 7 px tall
    for fx in (11, 14, 17, 20, 23, 26, 29):      # steel frets
        vline(g, fx, cy - 3, cy + 3, "s")
    for ix in (12, 18, 24):                      # trapezoid pearl inlays
        put(g, ix, cy - 1, "w"); put(g, ix, cy + 1, "w")
    # ---- Body: cream binding, then sunburst maple top (symmetric about cy) ----
    ellipse(g, 46, cy, 15, 13, "w")              # binding (lower/main bout)
    ellipse(g, 36, cy, 10, 11, "w")              # binding (upper bout by the neck)
    ellipse(g, 46, cy, 14, 12, "R")              # sunburst top (main)
    ellipse(g, 36, cy, 9, 10, "R")               # sunburst top (upper bout)
    ellipse(g, 31, cy - 8, 4, 4, " ")            # single-cutaway bay (upper-left)
    # ---- Strings (only over the body, nut side -> bridge) ----
    for sy in (cy - 2, cy, cy + 2):
        line(g, 31, sy, 49, sy, "s")
    # ---- Pickups + hardware ----
    ellipse(g, 38, cy + 8, 5, 2, "w")            # cream pickguard (lower/treble side)
    rect(g, 34, cy - 4, 36, cy + 4, "K")         # neck humbucker (upright bar)
    rect(g, 40, cy - 4, 42, cy + 4, "K")         # bridge humbucker
    for py in (cy - 3, cy - 1, cy + 1, cy + 3):
        put(g, 35, py, "o"); put(g, 41, py, "o")  # gold pole pieces
    vline(g, 46, cy - 4, cy + 4, "s")            # tune-o-matic bridge
    vline(g, 49, cy - 4, cy + 4, "s")            # stopbar tailpiece
    for kx, ky in ((52, cy + 6), (56, cy + 7), (54, cy + 3), (58, cy + 4)):
        put(g, kx, ky, "o")                      # 4 gold top-hat knobs
    write("rock_roller", g)


if __name__ == "__main__":
    import sys
    # `python tools/gen_ride_designs.py ostrich_walk` -> write only the walk spritesheet BMP
    # (a src/images/rides/ asset), NOT the full designs/*.txt regen below.
    if len(sys.argv) > 1 and sys.argv[1] == "ostrich_walk":
        ostrich_walk_sheet()
        sys.exit(0)
    ghost()
    pirate_ship()
    jungle_cruise()
    goat()
    # mesa()  # alternative Big Thunder design, not shipped (user chose the goat)
    # batch 2
    tea_cup()
    honey_pot()
    carousel_horse()
    bear()
    laser_blaster()
    tiki_bird()
    turtle()
    seashell()
    # batch 3
    race_car()
    locomotive()
    rocket()
    xwing()
    tree()
    # batch 4
    castle()
    spaceship_earth()
    everest()
    elephant()
    giraffe()
    tron()
    falcon()
    # batch 5
    submarine()
    riverboat()
    canoe()
    wave()
    jellyfish()
    river()
    # batch 6
    big_ben()
    magic_carpet()
    gems()
    jack_in_box()
    mop_bucket()
    # batch 7
    old_car()
    barn()
    door()
    rat()
    frog()
    volcano()
    plant()
    # batch 8
    child()
    splash()
    bobsled()
    coaster_car()
    airplane()
    hang_glider()
    # batch 9 (Efteling)
    mushroom()
    snake()
    pagoda()
    skull()
    fish()
    bird()
    dragon()
    fairy()
    # batch 10 (Chessington)
    crocodile()
    witch()
    bat()
    firetruck()
    helicopter()
    tiger()
    monkey()
    ostrich()
    # batch 11 (worldwide Disney)
    iron_man()
    snowflake()
    slinky_dog()
    tower_of_terror()
    indiana_hat()
    mountain_falls()
    # batch 12 (Universal)
    minion()
    dinosaur()
    transformers()
    mummy()
    panda()
    donut()
    shark()
    yoshi()
    motorcycle()
    # batch 13 (EPCOT / misc)
    pyramid()
    clownfish()
    light_bulb()
    cassette()
    flag()
    waves()
    # batch 14 (art-direction round 4)
    poison_apple()
    # batch 15 (Disney's Hollywood Studios)
    rock_roller()
