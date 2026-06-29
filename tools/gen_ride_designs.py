"""Programmatic generator for the ride-intro ASCII designs (64x32) — desktop dev tool.

Draws clean shapes into a char grid via primitives, then writes ``designs/<name>.txt``
for every ride icon. This is the reproducible source for the designs/*.txt files; after
editing a shape, re-run this then ``tools/make_ride_image.py`` to rebuild the BMP.
Row 0 / top-left stays sky (' ') per the BMP sky=index-0 rule.

    python tools/gen_ride_designs.py      # regenerate every designs/*.txt

Copyright (c) 2024-2026 Michael Winslow Czeiszperger
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


def write(name, g):
    path = os.path.join(DESIGNS, name + ".txt")
    with open(path, "w") as f:
        for row in g:
            f.write("".join(row).rstrip() + "\n")
    print("wrote", path)


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
    # ray-gun body pointing right (green/white, Buzz palette)
    rect(g, 14, 14, 40, 20, "g")          # body
    rect(g, 40, 15, 50, 18, "w")          # barrel
    rect(g, 14, 14, 40, 15, "w")          # top highlight
    # fin / sight
    line(g, 20, 13, 26, 9, "g"); line(g, 21, 13, 27, 9, "g")
    rect(g, 22, 9, 28, 11, "G")
    # grip
    rect(g, 16, 20, 22, 28, "G")
    # laser bolt firing right
    hline(g, 51, 62, 16, "r"); hline(g, 51, 62, 17, "y")
    put(g, 57, 14, "y"); put(g, 60, 19, "y")   # spark
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
    g = grid()
    # flippers
    ellipse(g, 22, 24, 5, 3, "G")
    ellipse(g, 44, 24, 5, 3, "G")
    ellipse(g, 24, 13, 4, 3, "G")
    ellipse(g, 43, 13, 4, 3, "G")
    # shell (green dome)
    ellipse(g, 33, 18, 14, 9, "g")
    # shell plates (darker outline scutes)
    ring(g, 33, 18, 7, "G")
    hline(g, 22, 44, 18, "G")
    vline(g, 33, 11, 25, "G")
    # head
    ellipse(g, 52, 17, 4, 3, "g")
    put(g, 54, 16, "N")                   # eye
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


# ---------------------------------------------------------------- GLASS SLIPPER
# glass_slipper is NOT generated here: it is TRACED from a user reference image via
#   python tools/trace_ref_outline.py <ref>.jpg --name glass_slipper --crop 180,175,590,480
# (white-filled silhouette + thin blue outline). Re-running this generator must not
# overwrite that traced designs/glass_slipper.txt, so there is no glass_slipper() here.


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
    for sx, sy in ((16, 9), (40, 24)):             # supports
        vline(g, sx, sy, 30, "S")
    rect(g, 22, 10, 34, 15, "r")                   # red coaster car at the crest
    line(g, 34, 10, 38, 14, "r")                   # nose
    for hx in (25, 29, 32):                        # riders + raised arms
        put(g, hx, 8, "w"); line(g, hx, 8, hx - 1, 6, "w"); line(g, hx, 8, hx + 1, 6, "w")
    put(g, 24, 16, "o"); put(g, 32, 16, "o")       # wheels
    write("coaster_car", g)


# ---------------------------------------------------------------- AIRPLANE (Soarin' EPCOT)
def airplane():
    g = grid()
    ellipse(g, 9, 7, 3, 2, "s"); ellipse(g, 55, 23, 3, 2, "s")             # clouds
    rect(g, 12, 15, 46, 19, "w")                   # fuselage tube
    line(g, 46, 14, 53, 17, "w"); line(g, 46, 20, 53, 17, "w"); rect(g, 46, 15, 52, 19, "w")  # nose cone
    # TALL vertical tail fin at the back (the clearest plane cue)
    line(g, 12, 15, 8, 6, "w"); line(g, 17, 15, 13, 6, "w"); rect(g, 8, 6, 17, 8, "w")
    line(g, 11, 17, 5, 14, "w")                    # horizontal stabiliser
    # swept main wing as a filled triangle below the belly
    for x in range(20, 38):
        y0 = 19 + (x - 20) // 2
        vline(g, x, 19, min(y0, 27), "s")
    for wx in range(16, 44, 3):
        put(g, wx, 17, ":")                        # window row
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


if __name__ == "__main__":
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
    # glass_slipper() is traced separately (tools/trace_ref_outline.py) — not generated here
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
