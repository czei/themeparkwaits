# Copyright (c) 2024-2026 Michael Czeiszperger
"""Per-ride intro ANIMATIONS — optional motion layered onto a ride's still intro image.

The intro flow (see ``ride_screen_content``) is HOLD -> FADE -> normal screen. For rides
whose real-world counterpart is *dynamic*, an ``IntroAnimator`` turns the static HOLD into
a short animation before the usual fade: Spaceship Earth twinkles, the turtle swims across
the panel, a rocket blasts off, a dragon breathes fire.

Design goals mirror the intro itself: **additive** and **defensive**.

  * An animator is looked up by image FILENAME (``for_image``), so every ride whose
    manifest entry points at e.g. ``turtle.bmp`` animates from one definition.
  * A missing entry, a failed ``attach``, or ANY per-frame error silently falls back to
    the plain still HOLD — an animation can never blank or wedge a ride screen.
  * Everything composites through the SAME ``displayio`` the display uses, so it renders
    on the Matrix Portal and the desktop simulator identically. Only ``math``/``random``
    are used, so it's CircuitPython-safe.

The engine is a small set of parameterized primitives; per-image behavior is DATA (the
``_SPECS`` registry at the bottom), so adding/tuning an image's motion is a one-line edit:

  * ``TwinkleAnimator``     — points flare on/off over the silhouette's own lit pixels
  * ``MotionAnimator``      — move the whole tile (traverse / rise / bob / jiggle)
  * ``EmitterAnimator``     — short-lived 1px particles (smoke, exhaust, bubbles, fire)
  * ``PalettePulseAnimator``— breathe the brightness of chosen palette colors (glows)
  * ``RegionShiftAnimator`` — sine-shift a captured region (wing flap, tail wag)
  * ``OrbiterAnimator``     — a tiny sprite loops an ellipse (a bee round the honey pot)
  * ``ComboAnimator``       — compose two of the above (rise + exhaust = blast-off)

Three motion levers, all proven in this codebase: move a ``TileGrid`` (the name-gradient
layer scrolls this way), rewrite pixels of a writable ``Bitmap`` (``reveal_splash``), and
rewrite ``Palette`` entries per frame (the intro fade).
"""
import math
import random

# Use the SAME displayio the display uses (real on CircuitPython, the simulator's on
# desktop). A bare ``import displayio`` can grab a stray Blinka PyPI package on desktop.
from scrollkit.display.unified import displayio


def copy_to_writable(src, width, height, ncolors):
    """A writable ``Bitmap`` copy of ``src`` (an OnDiskBitmap's bitmap or a Bitmap).

    Animators that MODIFY the image pixels (vs. only overlaying) need a writable target —
    an ``OnDiskBitmap`` is read-only. Copied once at attach (2048 reads for a 64x32), never
    per frame.
    """
    dst = displayio.Bitmap(width, height, ncolors)
    for y in range(height):
        for x in range(width):
            dst[x, y] = src[x, y]
    return dst


def _scale_color(color, f):
    """Scale a 24-bit color by ``f`` (clamped 0..255 per channel; f may exceed 1)."""
    r = int(((color >> 16) & 0xFF) * f)
    g = int(((color >> 8) & 0xFF) * f)
    b = int((color & 0xFF) * f)
    if r > 255:
        r = 255
    if g > 255:
        g = 255
    if b > 255:
        b = 255
    return (r << 16) | (g << 8) | b


class IntroAnimator:
    """Base: animate a ride's intro during the HOLD phase.

    Lifecycle mirrors the intro: ``attach()`` once (build overlays / capture pixels),
    ``step(frame)`` each HOLD frame, ``detach()`` to settle to a rest pose and free any
    layers. Subclasses set ``HOLD_FRAMES`` (how long to animate before the fade) and, if
    they need to REWRITE the base image pixels rather than just overlay a layer on top,
    ``wants_writable_bitmap = True`` so the loader hands them a writable copy.
    """

    HOLD_FRAMES = 96                 # ~5 s at the ~20 fps display loop
    wants_writable_bitmap = False

    def attach(self, display, tile, bitmap, palette, base_colors):
        """Store references and build any overlay layers. Raise to abort (falls back)."""
        self._display = display
        self._tile = tile
        self._bitmap = bitmap
        self._palette = palette
        self._base_colors = base_colors

    def step(self, frame):
        """Advance the animation to ``frame`` (0-based). Called once per HOLD frame."""

    def detach(self):
        """Settle to a rest pose and remove/free anything ``attach`` created (idempotent)."""

    # -- shared overlay helper (Twinkle / Emitter / Orbiter) ------------------------
    def _make_overlay(self, display, colors):
        """A transparent overlay Bitmap+TileGrid above the image; palette = [sky]+colors."""
        bmp = displayio.Bitmap(display.width, display.height, len(colors) + 1)
        pal = displayio.Palette(len(colors) + 1)
        pal[0] = 0x000000
        for i, c in enumerate(colors):
            pal[i + 1] = c
        pal.make_transparent(0)
        tile = displayio.TileGrid(bmp, pixel_shader=pal)
        display.add_layer(tile)
        self._overlay = bmp
        self._overlay_tile = tile
        return bmp

    def _drop_overlay(self):
        tile = getattr(self, "_overlay_tile", None)
        if tile is not None and getattr(self, "_display", None) is not None:
            try:
                self._display.remove_layer(tile)
            except Exception:
                pass
        self._overlay_tile = None
        self._overlay = None


class TwinkleAnimator(IntroAnimator):
    """Sparkling lights scattered across a silhouette (Spaceship Earth's light show).

    Overlays points sampled from the image's own lit pixels, each flaring on its own sine
    phase so they shimmer independently. Overlay-only — the base image never changes.
    """

    HOLD_FRAMES = 96

    def __init__(self, colors=(0x223355, 0x8899BB, 0xFFFFFF), count=34, box=None):
        self._colors = tuple(colors)
        self._count = count
        self._box = box

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        self._make_overlay(display, self._colors)
        w, h = display.width, display.height
        if self._box:
            x0, y0, x1, y1 = self._box
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(w, x1 + 1), min(h, y1 + 1)
        else:
            x0, y0, x1, y1 = 0, 0, w, h
        candidates = [(x, y) for y in range(y0, y1) for x in range(x0, x1)
                      if bitmap[x, y] != 0]
        random.shuffle(candidates)
        self._points = [(x, y, random.uniform(0.0, 6.28), random.uniform(0.15, 0.35))
                        for x, y in candidates[:min(self._count, len(candidates))]]

    def step(self, frame):
        overlay = self._overlay
        overlay.fill(0)                          # one C fill, never a per-pixel clear loop
        n = len(self._colors)
        for x, y, phase, speed in self._points:
            b = (math.sin(frame * speed + phase) + 1.0) * 0.5
            if b < 0.55:
                continue                         # mostly dark, brief flares -> a twinkle
            shade = n if b > 0.9 else (n - 1 if b > 0.72 and n > 1 else 1)
            overlay[x, y] = shade

    def detach(self):
        self._drop_overlay()
        self._points = None


class MotionAnimator(IntroAnimator):
    """Move the whole image tile: traverse across, blast off, bob, or jiggle.

    ``traverse_lr``/``traverse_rl`` cross the panel starting and ending fully off-screen;
    ``rise`` launches upward off the top after ``delay`` frames (with a tiny pre-launch
    shudder); ``bob``/``jiggle`` oscillate in place and recenter at detach. Traverse/rise
    deliberately do NOT recenter — the subject has left, and the fade shows empty sky.
    """

    def __init__(self, path="bob", amp=2, bob_amp=0, delay=0):
        self._path = path
        self._amp = amp
        self._bob_amp = bob_amp
        self._delay = delay
        if path in ("traverse_lr", "traverse_rl"):
            self.HOLD_FRAMES = 104
        elif path == "rise":
            self.HOLD_FRAMES = 84

    def step(self, frame):
        tile = self._tile
        p = self._path
        if p == "traverse_lr" or p == "traverse_rl":
            span = self.HOLD_FRAMES - 1
            t = frame / span if span else 1.0
            if t > 1.0:
                t = 1.0
            x0, x1 = (-66, 66) if p == "traverse_lr" else (66, -66)
            tile.x = int(round(x0 + (x1 - x0) * t))
            if self._bob_amp:
                tile.y = int(round(self._bob_amp * math.sin(frame * 0.3)))
        elif p == "rise":
            if frame < self._delay:
                tile.x = 1 if (frame // 3) & 1 else 0      # pre-launch shudder
            else:
                tile.x = 0
                t = (frame - self._delay) / float(max(1, self.HOLD_FRAMES - self._delay))
                tile.y = -int(round(40 * t * t))           # ease-in launch, exits the top
        elif p == "bob":
            tile.y = int(round(self._amp * math.sin(frame * 0.25)))
        elif p == "jiggle":
            tile.x = int(round(self._amp * math.sin(frame * 0.9)))
            tile.y = int(round((self._amp * 0.5) * math.sin(frame * 1.3)))

    def detach(self):
        if self._path in ("bob", "jiggle"):      # in-place motions settle back to center
            try:
                self._tile.x = 0
                self._tile.y = 0
            except Exception:
                pass


class EmitterAnimator(IntroAnimator):
    """Short-lived drifting particles from a spawn box (smoke, exhaust, bubbles, fire).

    Particles are single overlay pixels colored by age along ``colors`` (young -> old).
    Capped at ``max_live`` so the per-frame cost stays a few dozen writes + one C fill.
    """

    HOLD_FRAMES = 96

    def __init__(self, box, vx=0.0, vy=-0.5, rate=4, life=16,
                 colors=(0xFFFFFF, 0xBBBBBB, 0x777777), max_live=6, jitter=0.0,
                 delay=0, follow_tile=False):
        self._boxk = box
        self._vx = vx
        self._vy = vy
        self._rate = max(1, rate)
        self._life = life
        self._colors = tuple(colors)
        self._max = min(8, max_live)
        self._jitter = jitter
        self._delay = delay
        # follow_tile: spawn relative to the (moving) image tile, so a traversing
        # locomotive puffs smoke from its own stack and the puffs trail behind it.
        self._follow = follow_tile

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        self._make_overlay(display, self._colors)
        self._parts = []                          # [x, y, vx, vy, age] per particle

    def step(self, frame):
        overlay = self._overlay
        overlay.fill(0)
        if frame < self._delay:
            return
        if frame % self._rate == 0 and len(self._parts) < self._max:
            x0, y0, x1, y1 = self._boxk
            ox = oy = 0
            if self._follow:
                ox, oy = self._tile.x, self._tile.y
            j = self._jitter
            self._parts.append([random.uniform(x0, x1) + ox, random.uniform(y0, y1) + oy,
                                self._vx + (random.uniform(-j, j) if j else 0.0),
                                self._vy + (random.uniform(-j, j) if j else 0.0), 0])
        w, h = overlay.width, overlay.height
        ncol = len(self._colors)
        alive = []
        for part in self._parts:
            part[0] += part[2]
            part[1] += part[3]
            part[4] += 1
            if part[4] >= self._life:
                continue
            xi, yi = int(part[0]), int(part[1])
            if 0 <= xi < w and 0 <= yi < h:
                ci = 1 + min(ncol - 1, (part[4] * ncol) // self._life)
                overlay[xi, yi] = ci
                alive.append(part)
        self._parts = alive

    def detach(self):
        self._drop_overlay()
        self._parts = None


class PalettePulseAnimator(IntroAnimator):
    """Breathe the brightness of the palette entries matching given colors (a glow).

    Nearly free per frame (a handful of palette writes). The registry spec must only
    match colors exclusive to the glowing feature — validated at design time.
    """

    HOLD_FRAMES = 96

    def __init__(self, match, tol=24, lo=0.6, hi=1.25, period=48):
        self._match = tuple(match)
        self._tol = tol
        self._lo = lo
        self._hi = hi
        self._period = max(8, period)

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        t = self._tol
        idx = []
        for i in range(1, len(base_colors)):
            c = base_colors[i]
            r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
            for m in self._match:
                mr, mg, mb = (m >> 16) & 0xFF, (m >> 8) & 0xFF, m & 0xFF
                if abs(r - mr) <= t and abs(g - mg) <= t and abs(b - mb) <= t:
                    idx.append(i)
                    break
        self._idx = idx                           # empty -> harmless no-op

    def step(self, frame):
        f = self._lo + (self._hi - self._lo) * (math.sin(6.2832 * frame / self._period) + 1.0) * 0.5
        pal, base = self._palette, self._base_colors
        for i in self._idx:
            pal[i] = _scale_color(base[i], f)

    def detach(self):
        pal, base = getattr(self, "_palette", None), getattr(self, "_base_colors", None)
        if pal is None or base is None:
            return
        try:
            for i in self._idx:
                pal[i] = base[i]                  # restore, so the fade starts clean
        except Exception:
            pass


class RegionShiftAnimator(IntroAnimator):
    """Move the lit pixels inside a box (wing flap, tail wag, jaw, door slide, flag wave).

    The captured pixels re-stamp at an offset each frame; only the PREVIOUSLY stamped
    pixels are erased (tracked, not a whole-box clear), and frames where the offset didn't
    change cost nothing. The design-time rule: the box expanded by the travel along
    ``axis`` contains only this feature plus sky.

    Waveforms (``wave``): "sine" oscillates; "ramp" moves once from 0 to ``amp`` over
    ``period`` frames and holds (a door sliding open, a head popping up); "ripple" gives
    each COLUMN its own sine phase (a flag waving — y-axis only, small regions); "hinge"
    rotates the region about one fixed edge (``hinge``="left"/"right"): amplitude grows
    linearly from 0 at the shoulder to ``amp`` at the tip — a WHOLE wing beating.
    ``half`` clamps a sine to one side ("pos"/"neg": a jaw only opens downward).
    ``delay`` holds rest (or, with ``hide_before``, keeps the region ERASED — invisible)
    until that frame: a dragon's flame that appears mid-hold, a jack popping out.
    """

    HOLD_FRAMES = 96
    wants_writable_bitmap = True

    def __init__(self, box, axis="y", amp=2, period=24, phase=0.0,
                 wave="sine", half=None, delay=0, hide_before=False, wavelength=12,
                 hinge="left"):
        self._boxk = box
        self._axis = axis
        self._amp = amp
        self._period = max(4, period)
        self._phase = phase
        self._wave = wave
        self._half = half
        self._delay = delay
        self._hide = hide_before
        self._wl = max(4, wavelength)
        self._hinge = hinge

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        x0, y0, x1, y1 = self._boxk
        pix = []
        for y in range(max(0, y0), min(bitmap.height, y1 + 1)):
            for x in range(max(0, x0), min(bitmap.width, x1 + 1)):
                ci = bitmap[x, y]
                if ci != 0:
                    pix.append((x, y, ci))
        cap = 240 if self._wave in ("ripple", "hinge") else 320   # these restamp every frame
        if not pix or len(pix) > cap:             # too big = over budget -> fall back
            raise ValueError("region_shift: %d lit px" % len(pix))
        self._pix = pix
        self._x0 = x0
        self._x1 = max(x0 + 1, x1)
        self._stamped = [(x, y) for x, y, _ in pix]   # currently drawn positions
        self._last_off = 0
        self._hidden = False
        if self._hide:
            self._erase()                          # invisible until delay

    def _erase(self):
        bmp = self._bitmap
        for x, y in self._stamped:
            bmp[x, y] = 0
        self._stamped = []
        self._hidden = True

    def _stamp(self, off):
        bmp = self._bitmap
        w, h = bmp.width, bmp.height
        for x, y in self._stamped:                # erase only what we last drew
            bmp[x, y] = 0
        dx, dy = (off, 0) if self._axis == "x" else (0, off)
        stamped = []
        for x, y, ci in self._pix:
            xx, yy = x + dx, y + dy
            if 0 <= xx < w and 0 <= yy < h:
                bmp[xx, yy] = ci
                stamped.append((xx, yy))
        self._stamped = stamped
        self._last_off = off
        self._hidden = False

    def _stamp_ripple(self, frame):
        bmp = self._bitmap
        w, h = bmp.width, bmp.height
        for x, y in self._stamped:
            bmp[x, y] = 0
        k = 6.2832 / self._wl
        t = 6.2832 * frame / self._period
        stamped = []
        for x, y, ci in self._pix:
            yy = y + int(round(self._amp * math.sin(k * (x - self._x0) - t)))
            if 0 <= yy < h and 0 <= x < w:
                bmp[x, yy] = ci
                stamped.append((x, yy))
        self._stamped = stamped
        self._hidden = False

    def _stamp_hinge(self, frame):
        bmp = self._bitmap
        w, h = bmp.width, bmp.height
        for x, y in self._stamped:
            bmp[x, y] = 0
        s = math.sin(6.2832 * frame / self._period + self._phase)
        x0, x1 = self._x0, self._x1
        span = float(x1 - x0)
        stamped = []
        for x, y, ci in self._pix:
            wgt = (x1 - x) / span if self._hinge == "right" else (x - x0) / span
            yy = y + int(round(self._amp * s * wgt))
            if 0 <= yy < h:
                bmp[x, yy] = ci
                stamped.append((x, yy))
        self._stamped = stamped
        self._hidden = False

    def step(self, frame):
        if frame < self._delay:
            return                                # resting (or hidden) until the cue
        f = frame - self._delay
        if self._wave == "ripple":
            self._stamp_ripple(f)
            return
        if self._wave == "hinge":
            self._stamp_hinge(f)
            return
        if self._wave == "ramp":
            t = f / float(self._period)
            off = int(round(self._amp * (t if t < 1.0 else 1.0)))
        else:
            off = int(round(self._amp * math.sin(6.2832 * f / self._period + self._phase)))
            if self._half == "pos":
                off = abs(off)
            elif self._half == "neg":
                off = -abs(off)
        if off != self._last_off or self._hidden:  # unchanged offset -> zero cost
            self._stamp(off)

    def detach(self):
        try:
            if getattr(self, "_pix", None):
                self._stamp(0)                    # settle at rest (and un-hide) for the fade
        except Exception:
            pass


class OrbiterAnimator(IntroAnimator):
    """A tiny sprite loops an ellipse over the image (a bee circling the honey pot)."""

    HOLD_FRAMES = 96

    def __init__(self, cx, cy, rx, ry, period=64, sprite=((0, 0, 0xFFCC00),),
                 clockwise=True, delay=0, wobble=0):
        self._cx, self._cy = cx, cy
        self._rx, self._ry = rx, ry
        self._period = max(16, period)
        self._sprite = tuple(sprite)
        self._dir = 1.0 if clockwise else -1.0
        self._delay = delay                       # hidden until this frame (rx=ry=0 +
        self._wobble = wobble                     # delay = eyes appearing in a doorway)

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        colors = []
        self._cmap = {}
        for _, _, c in self._sprite:
            if c not in self._cmap:
                colors.append(c)
                self._cmap[c] = len(colors)       # overlay palette index (1-based)
        self._make_overlay(display, colors)

    def step(self, frame):
        overlay = self._overlay
        overlay.fill(0)
        if frame < self._delay:
            return
        th = 6.2832 * frame / self._period * self._dir
        px = self._cx + self._rx * math.cos(th)
        py = self._cy + self._ry * math.sin(th)
        if self._wobble:                          # erratic buzz on top of the orbit (a bee)
            px += self._wobble * math.sin(frame * 1.7)
            py += self._wobble * math.sin(frame * 2.3)
        w, h = overlay.width, overlay.height
        for dx, dy, c in self._sprite:
            xi, yi = int(px) + dx, int(py) + dy
            if 0 <= xi < w and 0 <= yi < h:
                overlay[xi, yi] = self._cmap[c]

    def detach(self):
        self._drop_overlay()


class BlinkAnimator(IntroAnimator):
    """Periodically cover a feature's lit pixels with a color (a wink, a rotor flicker).

    Overlay-only: during the "covered" window the captured pixels are painted ``color`` on
    the overlay (e.g. the fur color closes an eye — a wink; black over spinning rotor
    blades flickers them against the night sky). ``duty`` frames covered every ``period``.
    """

    HOLD_FRAMES = 96

    def __init__(self, box, color, period=70, duty=10, delay=28):
        self._boxk = box
        self._color = color
        self._period = max(8, period)
        self._duty = max(1, duty)
        self._delay = delay

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        self._make_overlay(display, (self._color,))
        x0, y0, x1, y1 = self._boxk
        self._cover = [(x, y)
                       for y in range(max(0, y0), min(display.height, y1 + 1))
                       for x in range(max(0, x0), min(display.width, x1 + 1))
                       if bitmap[x, y] != 0]

    def step(self, frame):
        overlay = self._overlay
        covered = frame >= self._delay and ((frame - self._delay) % self._period) < self._duty
        overlay.fill(0)
        if covered:
            for x, y in self._cover:
                overlay[x, y] = 1

    def detach(self):
        self._drop_overlay()
        self._cover = None


class SpriteLiftAnimator(IntroAnimator):
    """Lift a SUBJECT off the scene onto its own layer and move it; the scene stays fixed.

    The owner's scene-division rule: a canoe crosses the water, the water does not move.
    At attach, the subject's pixels (lit pixels inside ``boxes``, minus any near
    ``exclude_colors`` — e.g. the water blues) are copied onto an overlay tile, and the
    hole they leave in the base image is ROW-INPAINTED (each erased pixel takes the color
    of the nearest surviving pixel in its row — water bands and rails continue behind the
    subject automatically). The overlay then traverses: off-screen -> across -> off-screen,
    with optional bob and a ``slope`` (dy per dx) so a coaster car rides its drawn rail.
    Per-frame cost is two attribute writes — the cheapest mover in the engine.
    """

    HOLD_FRAMES = 104
    wants_writable_bitmap = True

    def __init__(self, boxes, exclude_colors=(), tol=28, path="lr", bob_amp=0,
                 slope=0.0, loop=False):
        self._boxes = boxes
        self._excl = tuple(exclude_colors)
        self._tol = tol
        self._path = path
        self._bob_amp = bob_amp
        self._slope = slope
        self._loop = loop

    def _is_excluded(self, rgb):
        t = self._tol
        r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
        for e in self._excl:
            if (abs(r - ((e >> 16) & 0xFF)) <= t and abs(g - ((e >> 8) & 0xFF)) <= t
                    and abs(b - (e & 0xFF)) <= t):
                return True
        return False

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        w, h = bitmap.width, bitmap.height
        lifted = {}
        for bx in self._boxes:
            x0, y0, x1, y1 = bx
            for y in range(max(0, y0), min(h, y1 + 1)):
                for x in range(max(0, x0), min(w, x1 + 1)):
                    ci = bitmap[x, y]
                    if ci != 0 and (x, y) not in lifted \
                            and not self._is_excluded(base_colors[ci]):
                        lifted[(x, y)] = ci
        if not lifted:
            raise ValueError("lift: nothing captured")
        # Subject copy on its own layer (cloned palette, sky transparent).
        opal = displayio.Palette(len(base_colors))
        for i, c in enumerate(base_colors):
            opal[i] = c
        opal.make_transparent(0)
        obmp = displayio.Bitmap(w, h, len(base_colors))
        for (x, y), ci in lifted.items():
            obmp[x, y] = ci
        otile = displayio.TileGrid(obmp, pixel_shader=opal)
        display.add_layer(otile)
        self._overlay = obmp
        self._overlay_tile = otile
        # Erase the subject from the scene, inpainting each hole pixel with the nearest
        # surviving pixel's color in its ROW (water bands / rails continue behind it).
        for (x, y), _ci in lifted.items():
            fill = 0
            for d in range(1, w):
                hit = False
                for xx in (x - d, x + d):
                    if 0 <= xx < w and (xx, y) not in lifted:
                        fill = bitmap[xx, y]
                        hit = True
                        break
                if hit:
                    break
            bitmap[x, y] = fill
        xs = [x for x, _ in lifted]
        self._span_lo = -(max(xs) + 2)            # tile.x that fully hides the subject left
        self._span_hi = (w + 2) - min(xs)         # ... and off the right edge

    def step(self, frame):
        span = self.HOLD_FRAMES - 1
        t = (frame % span) / float(span) if self._loop else min(1.0, frame / float(span))
        lo, hi = self._span_lo, self._span_hi
        if self._path == "rl":
            lo, hi = hi, lo
        x = lo + (hi - lo) * t
        self._overlay_tile.x = int(round(x))
        y = self._slope * x
        if self._bob_amp:
            y += self._bob_amp * math.sin(frame * 0.3)
        self._overlay_tile.y = int(round(y))

    def detach(self):
        self._drop_overlay()


class CoverAnimator(IntroAnimator):
    """A multi-color patch that hides/repositions part of the art until a cue frame.

    Copies the lit pixels in ``box``, draws them on an overlay at (dx, dy) — and blanks
    their home position — so a dragon's painted-open mouth reads CLOSED (jaw drawn shifted
    up, the opening masked) until ``until``, when the overlay clears in one shot and the
    painted art (and whatever effect starts then) takes over. Zero per-frame cost.
    """

    HOLD_FRAMES = 96

    def __init__(self, box, dx=0, dy=-2, until=35, blank=True):
        self._boxk = box
        self._dx, self._dy = dx, dy
        self._until = until
        self._blank = blank

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        x0, y0, x1, y1 = self._boxk
        pix = [(x, y, bitmap[x, y])
               for y in range(max(0, y0), min(display.height, y1 + 1))
               for x in range(max(0, x0), min(display.width, x1 + 1))
               if bitmap[x, y] != 0]
        colors = [0x000000]                       # overlay palette: [sky, black, ...]
        idx = {}
        for _x, _y, ci in pix:
            c = base_colors[ci]
            if c not in idx:
                colors.append(c)
                idx[c] = len(colors)              # 1-based overlay index (0 transparent)
        overlay = self._make_overlay(display, colors)
        w, h = display.width, display.height
        if self._blank:
            for x, y, _ci in pix:                 # mask the painted (open) position
                overlay[x, y] = 1                 # black
        for x, y, ci in pix:                      # draw the shifted (closed) copy
            xx, yy = x + self._dx, y + self._dy
            if 0 <= xx < w and 0 <= yy < h:
                overlay[xx, yy] = idx[base_colors[ci]]
        self._cleared = False

    def step(self, frame):
        if not self._cleared and frame >= self._until:
            self._overlay.fill(0)                 # one-shot reveal of the painted art
            self._cleared = True

    def detach(self):
        self._drop_overlay()


class VanishAnimator(IntroAnimator):
    """Lit pixels in successive boxes disappear at staged times (a bite out of a donut).

    Each box's pixels erase in order starting at ``start``, ``interval`` frames apart.
    The bites persist through the fade — the donut stays bitten. Cost is a one-shot erase
    per bite frame; nothing per-frame otherwise.
    """

    HOLD_FRAMES = 96
    wants_writable_bitmap = True

    def __init__(self, boxes, start=40, interval=16):
        self._boxes = boxes
        self._start = start
        self._interval = max(1, interval)

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        self._done = [False] * len(self._boxes)

    def step(self, frame):
        for k, bx in enumerate(self._boxes):
            if self._done[k] or frame < self._start + k * self._interval:
                continue
            x0, y0, x1, y1 = bx
            bmp = self._bitmap
            for y in range(max(0, y0), min(bmp.height, y1 + 1)):
                for x in range(max(0, x0), min(bmp.width, x1 + 1)):
                    bmp[x, y] = 0
            self._done[k] = True

    def detach(self):
        pass                                       # bites persist; the copy is discarded


class FrameCycleAnimator(IntroAnimator):
    """Pre-baked displacement frames cycled by layer swap (a WHOLE flag waving).

    Large-region ripples cost too much restamped per frame in Python, so the owner's
    'several frames' approach is baked at attach: the region's pixels render into
    ``nframes`` bitmaps, each displaced by a different ripple phase, and step() just swaps
    which one is on the display — O(1) per frame. RAM: nframes small bitmaps while the
    ride is on screen (freed at detach).
    """

    HOLD_FRAMES = 96
    wants_writable_bitmap = True

    def __init__(self, box, nframes=5, amp=2, wavelength=14, period=3,
                 exclude_colors=(), tol=28):
        self._boxk = box
        self._n = max(2, nframes)
        self._amp = amp
        self._wl = max(4, wavelength)
        self._period = max(1, period)
        self._excl = tuple(exclude_colors)
        self._tol = tol

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        x0, y0, x1, y1 = self._boxk
        w, h = bitmap.width, bitmap.height
        pix = [(x, y, bitmap[x, y])
               for y in range(max(0, y0), min(h, y1 + 1))
               for x in range(max(0, x0), min(w, x1 + 1))
               if bitmap[x, y] != 0]
        if not pix:
            raise ValueError("frames: nothing captured")
        self._pix = pix
        opal = displayio.Palette(len(base_colors))
        for i, c in enumerate(base_colors):
            opal[i] = c
        opal.make_transparent(0)
        k = 6.2832 / self._wl
        self._frames = []
        for p in range(self._n):
            fb = displayio.Bitmap(w, h, len(base_colors))
            ph = 6.2832 * p / self._n
            for x, y, ci in pix:
                yy = y + int(round(self._amp * math.sin(k * (x - x0) - ph)))
                if 0 <= yy < h:
                    fb[x, yy] = ci
            self._frames.append(displayio.TileGrid(fb, pixel_shader=opal))
        for x, y, _ci in pix:                      # the cloth lives on the overlays now
            bitmap[x, y] = 0
        self._cur = 0
        display.add_layer(self._frames[0])

    def step(self, frame):
        idx = (frame // self._period) % self._n
        if idx != self._cur:
            try:
                self._display.remove_layer(self._frames[self._cur])
            except Exception:
                pass
            self._display.add_layer(self._frames[idx])
            self._cur = idx

    def detach(self):
        try:
            self._display.remove_layer(self._frames[self._cur])
        except Exception:
            pass
        try:                                       # restore the cloth for the fade
            for x, y, ci in self._pix:
                self._bitmap[x, y] = ci
        except Exception:
            pass
        self._frames = None
        self._pix = None


class ComboAnimator(IntroAnimator):
    """Compose two primitives (e.g. rocket = rise + exhaust emitter)."""

    def __init__(self, parts):
        self._parts = parts
        self.HOLD_FRAMES = max(p.HOLD_FRAMES for p in parts)
        self.wants_writable_bitmap = any(p.wants_writable_bitmap for p in parts)

    def attach(self, display, tile, bitmap, palette, base_colors):
        for p in self._parts:
            p.attach(display, tile, bitmap, palette, base_colors)

    def step(self, frame):
        for p in self._parts:
            p.step(frame)

    def detach(self):
        for p in self._parts:
            try:
                p.detach()
            except Exception:
                pass


class SwimAnimator(IntroAnimator):
    """The turtle: swims in from off-screen left, across, and out off-screen right,
    bobbing and paddling its front flipper (Turtle Talk / Crush). Approved as-is.

    Kept bespoke (not a Combo) because the flipper capture is tuned to turtle.bmp and the
    traverse + bob + flap phasing was hand-dialed; see RegionShiftAnimator for the
    generalized flap.
    """

    HOLD_FRAMES = 104
    wants_writable_bitmap = True
    # Lower-left flipper bounding box (over sky background), tuned to turtle.bmp.
    _FLAP_X0, _FLAP_X1 = 2, 26
    _FLAP_Y0, _FLAP_Y1 = 22, 32
    _BOB_AMP = 2                 # vertical bob, pixels
    _FLAP_AMP = 2               # flipper stroke, pixels
    # Swim traverse: start/end fully off-screen (the panel is 64 wide and the turtle
    # spans nearly all of it, so +/-66 clears it completely at both ends).
    _X_START = -66
    _X_END = 66

    def attach(self, display, tile, bitmap, palette, base_colors):
        super().attach(display, tile, bitmap, palette, base_colors)
        self._can_flap = False
        h = display.height
        x1 = min(self._FLAP_X1, display.width)
        y1 = min(self._FLAP_Y1, h)
        pix = []
        try:
            for y in range(self._FLAP_Y0, y1):
                for x in range(self._FLAP_X0, x1):
                    ci = bitmap[x, y]
                    if ci != 0:
                        pix.append((x, y, ci))
            self._flap_pixels = pix
            self._can_flap = bool(pix)
        except Exception:
            self._flap_pixels = []
            self._can_flap = False

    def _stamp_flipper(self, dy):
        """Erase the flap box to sky, then draw the captured flipper shifted by ``dy``."""
        bmp = self._bitmap
        h = bmp.height if hasattr(bmp, "height") else self._display.height
        x1 = min(self._FLAP_X1, bmp.width if hasattr(bmp, "width") else self._display.width)
        y1 = min(self._FLAP_Y1, h)
        for y in range(self._FLAP_Y0, y1):
            for x in range(self._FLAP_X0, x1):
                bmp[x, y] = 0
        for x, y, ci in self._flap_pixels:
            yy = y + dy
            if 0 <= yy < h:
                bmp[x, yy] = ci

    def step(self, frame):
        # Swim left -> right: translate across the full width, off-screen at both ends.
        span = self.HOLD_FRAMES - 1 if self.HOLD_FRAMES > 1 else 1
        t = frame / span
        if t > 1.0:
            t = 1.0
        self._tile.x = int(round(self._X_START + (self._X_END - self._X_START) * t))
        # Gentle vertical bob (glide through the water).
        self._tile.y = int(round(self._BOB_AMP * math.sin(frame * 0.30)))
        # Flap the front flipper on its own (faster) clock.
        if self._can_flap:
            dy = -int(round((self._FLAP_AMP * (math.sin(frame * 0.5) + 1.0)) * 0.5))
            self._stamp_flipper(dy)

    def detach(self):
        # Settle the flipper to rest, but DO NOT recenter the tile: by the last HOLD frame
        # the turtle has swum off-screen right, and snapping it back to centre would flash
        # it during the fade. Leave tile.x/.y where the swim left them.
        try:
            if getattr(self, "_can_flap", False):
                self._stamp_flipper(0)
        except Exception:
            pass


# ------------------------------------------------------------------------------------
# Registry: image filename -> (type, kwargs). Data, not code — one line per image, so
# tuning a ride's motion is a spec edit. Unlisted images animate nothing (perfectly fine:
# not every icon should move). "combo" kwargs is a tuple of (type, kwargs) parts.
# ------------------------------------------------------------------------------------
_CLASSES = {
    "twinkle": TwinkleAnimator,
    "motion": MotionAnimator,
    "emitter": EmitterAnimator,
    "palette_pulse": PalettePulseAnimator,
    "region_shift": RegionShiftAnimator,
    "orbiter": OrbiterAnimator,
    "blink": BlinkAnimator,
    "lift": SpriteLiftAnimator,
    "cover": CoverAnimator,
    "vanish": VanishAnimator,
    "frames": FrameCycleAnimator,
    "swim": SwimAnimator,
}

_SPECS = {
    "spaceship_earth.bmp": ("twinkle", dict()),
    "turtle.bmp": ("swim", dict()),
    "airplane.bmp": ("motion", dict(path='traverse_lr', bob_amp=1)),
    "barn.bmp": ("orbiter", dict(cx=32, cy=9, rx=26, ry=6, period=60, clockwise=True, sprite=((0, 0, 0xEEEEEE), (-1, 0, 0xBBBBBB), (-2, 0, 0x777777), (0, -1, 0xEEEEEE)))),
    "bat.bmp": ("combo", (("motion", dict(path='traverse_lr', amp=1, bob_amp=0, delay=0)), ("region_shift", dict(box=(2, 6, 27, 21), axis='y', amp=4, period=14, wave='hinge', hinge='right')), ("region_shift", dict(box=(37, 6, 62, 21), axis='y', amp=4, period=14, wave='hinge', hinge='left')))),
    "bear.bmp": ("blink", dict(box=(23, 11, 29, 19), color=0xBB6633, period=96, duty=8, delay=40)),
    "big_ben.bmp": ("orbiter", dict(cx=11, cy=8, rx=9, ry=6, period=80, clockwise=True, sprite=((0, 0, 0xFFFFFF), (-1, 0, 0xFFEE99), (-2, -1, 0xAA8833)))),
    "bird.bmp": ("combo", (("motion", dict(path='traverse_lr', amp=1, bob_amp=0, delay=0)), ("region_shift", dict(box=(4, 6, 28, 17), axis='y', amp=2, period=12, phase=0, wave='sine')), ("region_shift", dict(box=(36, 6, 60, 17), axis='y', amp=2, period=12, phase=0, wave='sine')))),
    "bobsled.bmp": ("lift", dict(boxes=((15, 13, 49, 25),), exclude_colors=(0xBBBBCC, 0x777788, 0x9999AA, 0xCCCCDD), tol=28, path='lr', bob_amp=0, slope=0, loop=False)),
    "canoe.bmp": ("lift", dict(boxes=((8, 10, 57, 25),), exclude_colors=(0x1166BB, 0x3388DD, 0x4499EE, 0x55AAEE, 0x88DDFF), tol=28, path='lr', bob_amp=1, slope=0, loop=True)),
    "carousel_horse.bmp": ("motion", dict(path='traverse_rl', amp=2, bob_amp=2)),
    "cassette.bmp": ("combo", (("orbiter", dict(cx=26, cy=21, rx=3, ry=3, period=40, sprite=((0, 0, 0xFFFFFF),), clockwise=True)), ("orbiter", dict(cx=38, cy=21, rx=3, ry=3, period=40, sprite=((0, 0, 0xFFFFFF),), clockwise=True)))),
    "castle.bmp": ("combo", (("region_shift", dict(box=(20, 4, 22, 6), axis='y', amp=1, period=14, wave='ripple', wavelength=4)), ("region_shift", dict(box=(44, 4, 46, 6), axis='y', amp=1, period=14, wave='ripple', wavelength=4, phase=0.5)), ("palette_pulse", dict(match=(0xFF6655, 0xEE5544), tol=16, lo=0.6, hi=1.35, period=26)))),
    "child.bmp": ("motion", dict(path='bob', amp=1)),
    "clownfish.bmp": ("combo", (("motion", dict(path='traverse_rl', amp=1, bob_amp=1)), ("region_shift", dict(box=(44, 6, 56, 27), axis='y', amp=1, period=20)))),
    "coaster_car.bmp": ("lift", dict(boxes=((22, 6, 38, 16),), exclude_colors=(0xAABBCC, 0x888899, 0x444455), tol=28, path='lr', bob_amp=0, slope=0.4, loop=True)),
    "crocodile.bmp": ("combo", (("motion", dict(path='traverse_rl', bob_amp=1)), ("region_shift", dict(box=(3, 20, 24, 23), axis='y', amp=2, period=32, wave='sine', half='pos')))),
    "donut.bmp": ("vanish", dict(boxes=((40, 5, 46, 9), (38, 10, 46, 14), (40, 15, 46, 17)), start=35, interval=16)),
    "door.bmp": ("combo", (("region_shift", dict(box=(32, 5, 41, 29), axis='x', amp=-9, period=30, wave='ramp', delay=12)), ("orbiter", dict(cx=35, cy=13, rx=0, ry=0, period=32, delay=55, sprite=((0, 0, 0xFFFFFF), (3, 0, 0xFFFFFF)))))),
    "dragon.bmp": ("combo", (("cover", dict(box=(22, 18, 31, 19), dx=0, dy=-3, until=35, blank=True)), ("region_shift", dict(box=(0, 6, 16, 24), axis='x', amp=0, period=96, wave='sine', delay=35, hide_before=True)), ("emitter", dict(box=(12, 12, 18, 18), vx=-0.9, vy=0, jitter=0.3, rate=3, life=16, max_live=6, colors=(0xFFFFCC, 0xFFEE66, 0xFFBB22, 0xCC4411), delay=35)))),
    "elephant.bmp": ("combo", (("region_shift", dict(box=(13, 9, 23, 25), axis='y', amp=1, period=10, wave='sine', phase=0)), ("region_shift", dict(box=(41, 9, 51, 25), axis='y', amp=1, period=10, wave='sine', phase=5)))),
    "fairy.bmp": ("combo", (("motion", dict(path='traverse_rl', amp=0, bob_amp=1, delay=40)), ("region_shift", dict(box=(9, 3, 22, 17), axis='x', amp=1, period=6, wave='sine', half='neg')), ("region_shift", dict(box=(36, 3, 45, 17), axis='x', amp=1, period=6, wave='sine', half='pos')))),
    "falcon.bmp": ("combo", (("motion", dict(path='traverse_lr', amp=1, bob_amp=1)), ("palette_pulse", dict(match=(0x3399FF, 0x2288EE, 0x2277DD, 0xEEEEDD, 0xFFEEEE), tol=16, lo=0.6, hi=1.35, period=30)))),
    "firetruck.bmp": ("combo", (("motion", dict(path='traverse_lr', amp=1, bob_amp=1)), ("palette_pulse", dict(match=(0xFFEE55,), tol=24, lo=0.4, hi=1.6, period=26)))),
    "fish.bmp": ("combo", (("motion", dict(path='traverse_lr', bob_amp=1)), ("region_shift", dict(box=(6, 6, 12, 26), axis='y', amp=2, period=20)))),
    "flag.bmp": ("frames", dict(box=(8, 2, 57, 23), nframes=6, amp=2, wavelength=14, period=3)),
    "frog.bmp": ("motion", dict(path='traverse_lr', bob_amp=2)),
    "gems.bmp": ("twinkle", dict(colors=(0x333344, 0xAAAACC, 0xFFFFFF), count=14)),
    "glass_slipper.bmp": ("palette_pulse", dict(match=(0xFFFFFF, 0xAAEEFF, 0x66AADD), tol=24, lo=0.7, hi=1.5, period=44)),
    "hang_glider.bmp": ("lift", dict(boxes=((11, 5, 53, 15), (26, 16, 39, 23)), exclude_colors=(), tol=28, path='lr', bob_amp=1, slope=-0.08, loop=True)),
    "haunted_mansion.bmp": ("combo", (("region_shift", dict(box=(15, 10, 22, 20), axis='y', amp=1, period=22, phase=0, wave='sine')), ("region_shift", dict(box=(42, 10, 49, 20), axis='y', amp=1, period=22, phase=3.14, wave='sine')))),
    "helicopter.bmp": ("combo", (("motion", dict(path='traverse_rl', amp=1, bob_amp=1)), ("blink", dict(box=(5, 4, 60, 7), color=0, period=6, duty=3, delay=0)))),
    "honey_pot.bmp": ("orbiter", dict(cx=32, cy=19, rx=15, ry=10, period=50, wobble=1, clockwise=True, sprite=((0, 0, 0xFFCC00), (1, 0, 0x442200), (2, 0, 0xFFCC00)))),
    "iron_man.bmp": ("palette_pulse", dict(match=(0xFFFFFF, 0xEEEEEE, 0xDDDDDD), tol=24, lo=0.45, hi=1.2, period=40)),
    "jack_in_box.bmp": ("region_shift", dict(box=(27, 0, 37, 12), axis='y', amp=2, period=14, wave='sine', half='neg', delay=40, hide_before=True)),
    "jellyfish.bmp": ("region_shift", dict(box=(21, 16, 43, 29), axis='x', amp=1, period=24, phase=0, wave='ripple', wavelength=7)),
    "jungle_cruise.bmp": ("lift", dict(boxes=((13, 1, 53, 25),), exclude_colors=(0x2288EE, 0x2277CC, 0x2266BB, 0x1155AA, 0x114488, 0x112244), tol=28, path='rl', bob_amp=0, slope=0, loop=True)),
    "laser_blaster.bmp": ("combo", (("emitter", dict(box=(47, 15, 48, 16), vx=3, vy=0, rate=2, life=20, colors=(0xFFEE99, 0xEE4444, 0xCC3333), max_live=8, jitter=0)), ("palette_pulse", dict(match=(0x775511, 0x776622), tol=16, lo=0.6, hi=1.6, period=20)))),
    "light_bulb.bmp": ("palette_pulse", dict(match=(0xFFEE55, 0xFFDD44, 0xFFFF66, 0xEECC44, 0xCCAA33), tol=24, lo=0.6, hi=1.35, period=44)),
    "locomotive.bmp": ("lift", dict(boxes=((0, 0, 63, 29),), path='lr', loop=True)),
    "magic_carpet.bmp": ("motion", dict(path='traverse_lr', bob_amp=2)),
    "minion.bmp": ("motion", dict(path='jiggle', amp=1)),
    "monkey.bmp": ("region_shift", dict(box=(24, 23, 40, 28), axis='y', amp=2, period=48, wave='sine', half='pos')),
    "mop_bucket.bmp": ("palette_pulse", dict(match=(0x2288EE, 0x1166CC, 0x1155AA), tol=24, lo=0.5, hi=1.5, period=40)),
    "motorcycle.bmp": ("motion", dict(path='traverse_lr', bob_amp=1)),
    "mountain_falls.bmp": ("combo", (("emitter", dict(box=(28, 4, 37, 11), vx=0, vy=0.8, rate=2, life=22, jitter=0.3, max_live=8, colors=(0x88CCFF, 0x44A0EE, 0x1166CC))), ("emitter", dict(box=(27, 15, 38, 25), vx=0, vy=0.8, rate=2, life=18, jitter=0.3, delay=8, max_live=8, colors=(0x88CCFF, 0x44A0EE, 0x1166CC))))),
    "mummy.bmp": ("twinkle", dict(colors=(0x443300, 0xBB8833, 0xFFEEBB), count=10)),
    "mushroom.bmp": ("twinkle", dict(colors=(0x663333, 0xEE9988, 0xFFFFFF), count=8, box=(12, 3, 54, 16))),
    "old_car.bmp": ("motion", dict(path='traverse_lr', bob_amp=1)),
    "ostrich.bmp": ("motion", dict(path='traverse_lr', bob_amp=1)),
    "panda.bmp": ("blink", dict(box=(23, 12, 29, 18), color=0x555555, period=48, duty=9, delay=28)),
    "poison_apple.bmp": ("palette_pulse", dict(match=(0x88DD55, 0x88CC55, 0x77BB55), tol=20, lo=0.5, hi=1.55, period=36)),
    "pirates.bmp": ("lift", dict(boxes=((9, 4, 62, 27),), exclude_colors=(0x88DDFF, 0x66BBEE, 0x4499EE, 0x2277CC, 0x1166BB, 0x1155AA), tol=28, path='lr', bob_amp=0, slope=0, loop=True)),
    "race_car.bmp": ("motion", dict(path='traverse_lr', bob_amp=1)),
    "rat.bmp": ("region_shift", dict(box=(4, 7, 14, 21), axis='y', amp=2, period=18, wave='sine')),
    "river.bmp": ("twinkle", dict(colors=(0x112233, 0x3388AA, 0xCCFFFF), count=18)),
    "riverboat.bmp": ("lift", dict(boxes=((4, 0, 59, 26),), exclude_colors=(0x2288EE, 0x2277CC, 0x2266BB, 0x1155AA, 0x114488, 0x112244), tol=28, path='lr', bob_amp=0, slope=0, loop=True)),
    "rocket.bmp": ("combo", (("motion", dict(path='rise', delay=40)), ("emitter", dict(box=(29, 27, 37, 29), vx=0, vy=0.5, rate=2, life=10, colors=(0xFFEE44, 0xFFAA22, 0xEE4411, 0x662211), max_live=8, jitter=0.3)))),
    "seashell.bmp": ("twinkle", dict(colors=(0x443311, 0xBB9944, 0xFFFFEE), count=12)),
    "shark.bmp": ("motion", dict(path='traverse_lr', bob_amp=1)),
    "skull.bmp": ("combo", (("emitter", dict(box=(25, 12, 29, 15), vx=0, vy=-0.1, rate=2, life=10, colors=(0xEE3311, 0xBB1111, 0x550000), max_live=4, jitter=0.2)), ("emitter", dict(box=(35, 12, 39, 15), vx=0, vy=-0.1, rate=2, life=10, colors=(0xEE3311, 0xBB1111, 0x550000), max_live=4, jitter=0.2)))),
    "slinky_dog.bmp": ("region_shift", dict(box=(49, 5, 63, 29), axis='x', amp=1, period=28, wave='sine', half='neg')),
    "snake.bmp": ("palette_pulse", dict(match=(0xFF4444, 0xEE3333), tol=48, lo=0.4, hi=1.4, period=26)),
    "snowflake.bmp": ("twinkle", dict(colors=(0x223366, 0x7799CC, 0xFFFFFF), count=14)),
    "space_mountain.bmp": ("combo", (("twinkle", dict(colors=(0x223355, 0x8899BB, 0xFFFFFF), count=4, box=(0, 0, 15, 13))), ("twinkle", dict(colors=(0x223355, 0x8899BB, 0xFFFFFF), count=5, box=(46, 0, 63, 10))))),
    "splash.bmp": ("emitter", dict(box=(18, 22, 47, 25), vx=0, vy=-1, rate=2, life=12, colors=(0xFFFFFF, 0x99CCEE, 0x3377BB), max_live=8, jitter=0.3)),
    "submarine.bmp": ("emitter", dict(box=(46, 4, 54, 12), vx=0.1, vy=-0.45, rate=4, life=16, colors=(0xAADDFF, 0x88AACC, 0x445577), max_live=6, jitter=0.2)),
    "tea_cup.bmp": ("emitter", dict(box=(24, 8, 42, 11), vx=0, vy=-0.4, rate=4, life=18, colors=(0xFFFFEE, 0xCCCCCC, 0x777777), max_live=6, jitter=0.2)),
    "tiki_bird.bmp": ("region_shift", dict(box=(43, 10, 50, 19), axis='y', amp=1, period=20, wave='sine')),
    "tower_of_terror.bmp": ("palette_pulse", dict(match=(0xFFEE55, 0xFFDD55, 0xFFCC44, 0xFFFF66), tol=20, lo=0.4, hi=1.5, period=28)),
    "transformers.bmp": ("palette_pulse", dict(match=(0xCCEEFF, 0xBBDDFF, 0xBBEEFF), tol=8, lo=0.5, hi=1.6, period=40)),
    "tree.bmp": ("twinkle", dict(colors=(0x224422, 0x88AA44, 0xFFEE88), count=10, box=(14, 1, 50, 19))),
    "tron.bmp": ("combo", (("motion", dict(path='traverse_lr', amp=2, bob_amp=0)), ("palette_pulse", dict(match=(0xCCFFFF, 0xAADDEE, 0xBBEEFF, 0x99DDEE), tol=20, lo=0.6, hi=1.5, period=32)))),
    "volcano.bmp": ("combo", (("emitter", dict(box=(26, 11, 30, 13), vx=-0.2, vy=0.5, rate=5, life=28, colors=(0xFFEE55, 0xFFAA33, 0xEE4444, 0x992211), max_live=4, jitter=0.2)), ("emitter", dict(box=(34, 11, 38, 13), vx=0.2, vy=0.5, rate=5, life=28, colors=(0xFFEE55, 0xFFAA33, 0xEE4444, 0x992211), max_live=4, jitter=0.2, delay=6)))),
    "waves.bmp": ("combo", (("region_shift", dict(box=(0, 4, 63, 12), axis='x', amp=2, period=36)), ("region_shift", dict(box=(0, 13, 63, 21), axis='x', amp=2, period=48)))),
    "witch.bmp": ("motion", dict(path='traverse_lr', amp=1, bob_amp=1)),
    "xwing.bmp": ("motion", dict(path='rise', delay=20)),
    "yoshi.bmp": ("motion", dict(path='jiggle', amp=2)),
}


def _build(kind, kwargs):
    if kind == "combo":
        return ComboAnimator([_build(k, kw) for k, kw in kwargs])
    return _CLASSES[kind](**kwargs)


def for_image(image_path):
    """A fresh ``IntroAnimator`` for the intro image at ``image_path``, or ``None``.

    Matched on the trailing filename so a full path or a bare name both resolve. Returns a
    NEW instance each call (animators hold per-play state), or ``None`` for images with no
    registered animation. Any construction error yields ``None`` (still image, never a
    crash) — same defensive posture as the rest of the intro pipeline.
    """
    if not image_path:
        return None
    name = image_path.replace("\\", "/").rsplit("/", 1)[-1]
    spec = _SPECS.get(name)
    if spec is None:
        return None
    try:
        return _build(spec[0], spec[1])
    except Exception:
        return None
