# Copyright (c) 2024-2026 Michael Czeiszperger
"""Per-ride intro ANIMATIONS — app data + policy over the library's image animators.

The ENGINE lives in the library now: ``scrollkit.effects.image_animators`` provides the
thirteen generic per-frame primitives (extracted up from this app, 2026-07; this module is
the back-compat/rollback seam, same pattern as ``src/diagnostics.py``). What stays here
is exactly the theme-park domain:

  * ``_SPECS`` — which ride IMAGE gets which animation, one data line per image,
    owner-art-directed across four review rounds. Unlisted images stay still.
  * ``SwimAnimator`` — the turtle's hand-tuned swim (traverse + bob + flipper flap),
    approved as-is and kept bespoke.
  * ``for_image()`` — filename -> fresh animator, defensively (any error = still image).
  * ``copy_to_writable(src, w, h, n)`` — the historical 4-arg signature, partially
    applying this app's platform ``displayio`` as the library's gfx handle.

Rollback: restore this file from git history (pre-shim revision) and the app is fully
self-contained again; the library module can stay, unused.
"""
from scrollkit.effects.image_animators import (       # noqa: F401 — re-exports
    IntroAnimator,
    TwinkleAnimator,
    MotionAnimator,
    EmitterAnimator,
    PalettePulseAnimator,
    RegionShiftAnimator,
    RegionRotateAnimator,
    OrbiterAnimator,
    BlinkAnimator,
    SpriteLiftAnimator,
    CoverAnimator,
    VanishAnimator,
    FrameCycleAnimator,
    CelWalkAnimator,
    ComboAnimator,
)
from scrollkit.effects.image_animators import copy_to_writable as _lib_copy_to_writable
from scrollkit.effects.image_animators import read_indexed_bmp as _lib_read_indexed_bmp
import math

# The library builds bitmaps via display.gfx; this app's platform displayio module
# (real on CircuitPython, the simulator's on desktop) duck-types as that gfx handle.
from scrollkit.display.unified import displayio as _displayio


def copy_to_writable(src, width, height, ncolors):
    """Historical 4-arg wrapper over the library's gfx-first copy (see module doc)."""
    return _lib_copy_to_writable(_displayio, src, width, height, ncolors)


def read_indexed_bmp(path):
    """Decode a ride intro BMP into a writable Bitmap (CircuitPython's OnDiskBitmap
    is not subscriptable, so animators cannot read pixels through it on-device)."""
    return _lib_read_indexed_bmp(_displayio, path)


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

    def start(self, display, tile, bitmap, palette, base_colors):
        super().start(display, tile, bitmap, palette, base_colors)
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
        bmp = self.bitmap
        h = bmp.height if hasattr(bmp, "height") else self.display.height
        x1 = min(self._FLAP_X1, bmp.width if hasattr(bmp, "width") else self.display.width)
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
        self.tile.x = int(round(self._X_START + (self._X_END - self._X_START) * t))
        # Gentle vertical bob (glide through the water).
        self.tile.y = int(round(self._BOB_AMP * math.sin(frame * 0.30)))
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


class SheenAnimator(IntroAnimator):
    """A soft specular highlight sweeping across a glossy surface — a guitar's finish
    catching a moving stage light (Rock 'n' Roller Coaster's Les Paul). Overlay-only:
    ``start`` captures the surface pixels (non-sky inside ``box``) and projects each onto
    the sweep axis; each frame lights a moving band, brightest along its centre, that
    travels across the surface and then rests dark for ``gap`` of the cycle before the
    next pass. Bespoke (like SwimAnimator): ``box``/``angle`` are tuned to the body of
    rock_roller.bmp, so the glint rakes down the sunburst top and skips the neck.
    """

    HOLD_FRAMES = 108

    def __init__(self, box, angle=1.02, period=88, width=1.3, gap=0.55,
                 colors=(0xFFCD6E, 0xFFEEAF)):
        self._box = box
        self._angle = angle          # travel direction of the band (radians)
        self._period = max(8, period)
        self._width = width          # half-width of the lit band, in pixels
        self._gap = min(0.95, max(0.0, gap))   # fraction of the cycle spent dark
        self._colors = tuple(colors)

    def start(self, display, tile, bitmap, palette, base_colors):
        super().start(display, tile, bitmap, palette, base_colors)
        self._make_overlay(display, self._colors)
        x0, y0, x1, y1 = self._box
        ca, sa = math.cos(self._angle), math.sin(self._angle)
        pts = []
        smin, smax = 1e9, -1e9
        for y in range(max(0, y0), min(display.height, y1 + 1)):
            for x in range(max(0, x0), min(display.width, x1 + 1)):
                if bitmap[x, y] != 0:                  # surface pixel (not sky)
                    s = x * ca + y * sa
                    pts.append((x, y, s))
                    if s < smin:
                        smin = s
                    if s > smax:
                        smax = s
        self._pts = pts
        self._smin, self._smax = smin, smax

    def step(self, frame):
        overlay = self._overlay
        overlay.fill(0)                                # one C fill, no per-pixel clear
        if not self._pts:
            return
        active = 1.0 - self._gap
        cyc = (frame % self._period) / self._period
        if cyc >= active:                              # dark rest between passes
            return
        t = cyc / active if active else 0.0
        w = self._width
        center = self._smin - w + t * ((self._smax - self._smin) + 2 * w)
        n = len(self._colors)
        for (x, y, s) in self._pts:
            d = abs(s - center)
            if d < w:
                overlay[x, y] = n if d < w * 0.5 else 1   # bright core, soft flank

    def detach(self):
        self._drop_overlay()
        self._pts = None


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
    "region_rotate": RegionRotateAnimator,
    "orbiter": OrbiterAnimator,
    "blink": BlinkAnimator,
    "lift": SpriteLiftAnimator,
    "cover": CoverAnimator,
    "vanish": VanishAnimator,
    "frames": FrameCycleAnimator,
    "swim": SwimAnimator,
    "cel_walk": CelWalkAnimator,
    "sheen": SheenAnimator,
}

_SPECS = {
    "spaceship_earth.bmp": ("twinkle", dict()),
    "turtle.bmp": ("swim", dict()),
    "airplane.bmp": ("motion", dict(path='traverse_lr', bob_amp=1)),
    "barn.bmp": ("orbiter", dict(cx=32, cy=9, rx=26, ry=6, period=60, clockwise=True, sprite=((0, 0, 0xEEEEEE), (-1, 0, 0xBBBBBB), (-2, 0, 0x777777), (0, -1, 0xEEEEEE)))),
    "bat.bmp": ("combo", (("motion", dict(path='traverse_lr', amp=1, bob_amp=0, delay=0)), ("region_shift", dict(box=(2, 6, 27, 21), axis='y', amp=4, period=14, wave='hinge', hinge='right')), ("region_shift", dict(box=(37, 6, 62, 21), axis='y', amp=4, period=14, wave='hinge', hinge='left')))),
    "bear.bmp": ("blink", dict(box=(23, 11, 29, 19), color=0xBB6633, period=96, duty=8, delay=40)),
    "big_ben.bmp": ("orbiter", dict(cx=11, cy=8, rx=9, ry=6, period=80, clockwise=True, sprite=((0, 0, 0xFFFFFF), (-1, 0, 0xFFEE99), (-2, -1, 0xAA8833)))),
    # Goat nods: a TRUE rotation of the head about the neck joint, so the head TILTS
    # (nose dips as poll rises) instead of shearing straight up/down. The body is the
    # same cream fill the head attaches to, so it's EXCLUDED (stays static, never
    # holed); the pivot sits at the head/body split (~col 22, the merge row) so the
    # muzzle + lit fuse swing most and the shoulder barely moves.
    "big_thunder_goat.bmp": ("region_rotate", dict(box=(3, 8, 27, 20), pivot=(22, 14), amp_deg=13, period=44, exclude=(23, 14, 43, 22))),
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
    # T-rex roar: a TRUE rotation of the head about the neck base, clamped up-only
    # (half='pos') so it always reads as rearing back to roar, never pecking; the body,
    # spikes and tail are excluded and hold still. One spec animates all 15 Jurassic rides.
    "dinosaur.bmp": ("region_rotate", dict(box=(45, 3, 63, 15), pivot=(46, 13), amp_deg=9, period=64, half='pos', exclude=(0, 8, 44, 31))),
    "donut.bmp": ("vanish", dict(boxes=((40, 5, 46, 9), (38, 10, 46, 14), (40, 15, 46, 17)), start=35, interval=16)),
    "door.bmp": ("combo", (("region_shift", dict(box=(32, 5, 41, 29), axis='x', amp=-9, period=30, wave='ramp', delay=12)), ("orbiter", dict(cx=35, cy=13, rx=0, ry=0, period=32, delay=55, sprite=((0, 0, 0xFFFFFF), (3, 0, 0xFFFFFF)))))),
    "dragon.bmp": ("combo", (("cover", dict(box=(22, 18, 31, 19), dx=0, dy=-3, until=35, blank=True)), ("region_shift", dict(box=(0, 6, 16, 24), axis='x', amp=0, period=96, wave='sine', delay=35, hide_before=True)), ("emitter", dict(box=(12, 12, 18, 18), vx=-0.9, vy=0, jitter=0.3, rate=3, life=16, max_live=6, colors=(0xFFFFCC, 0xFFEE66, 0xFFBB22, 0xCC4411), delay=35)))),
    "elephant.bmp": ("combo", (("region_shift", dict(box=(13, 9, 23, 25), axis='y', amp=1, period=10, wave='sine', phase=0)), ("region_shift", dict(box=(41, 9, 51, 25), axis='y', amp=1, period=10, wave='sine', phase=5)))),
    "everest.bmp": ("combo", (("emitter", dict(box=(26, 5, 28, 7), vx=0.7, vy=-0.15, rate=3, life=16, colors=(0xFFFFFF, 0xCCDDEE, 0x667788), max_live=4, jitter=0.25)), ("emitter", dict(box=(33, 5, 35, 7), vx=0.7, vy=-0.15, rate=3, life=16, colors=(0xFFFFFF, 0xCCDDEE, 0x667788), max_live=4, jitter=0.25, delay=5)))),
    "fairy.bmp": ("combo", (("motion", dict(path='traverse_rl', amp=0, bob_amp=1, delay=40)), ("region_shift", dict(box=(9, 3, 22, 17), axis='x', amp=1, period=6, wave='sine', half='neg')), ("region_shift", dict(box=(36, 3, 45, 17), axis='x', amp=1, period=6, wave='sine', half='pos')))),
    "falcon.bmp": ("combo", (("motion", dict(path='traverse_lr', amp=1, bob_amp=1)), ("palette_pulse", dict(match=(0x3399FF, 0x2288EE, 0x2277DD, 0xEEEEDD, 0xFFEEEE), tol=16, lo=0.6, hi=1.35, period=30)))),
    "firetruck.bmp": ("combo", (("motion", dict(path='traverse_lr', amp=1, bob_amp=1)), ("palette_pulse", dict(match=(0xFFEE55,), tol=24, lo=0.4, hi=1.6, period=26)))),
    "fish.bmp": ("combo", (("motion", dict(path='traverse_lr', bob_amp=1)), ("region_shift", dict(box=(6, 6, 12, 26), axis='y', amp=2, period=20)))),
    "flag.bmp": ("frames", dict(box=(8, 2, 57, 23), nframes=6, amp=2, wavelength=14, period=3)),
    "frog.bmp": ("motion", dict(path='traverse_lr', bob_amp=2)),
    "gems.bmp": ("twinkle", dict(colors=(0x333344, 0xAAAACC, 0xFFFFFF), count=14)),
    # Kilimanjaro Safaris: the giraffe stands and swings its long neck. A true rotation
    # about the shoulder joint, so the far-away head bobs a lot while the neck base stays
    # planted; the body/legs/ground are excluded and hold still (Animal Kingdom's signature
    # animal, and the one silhouette that survives 64x32).
    "giraffe.bmp": ("region_rotate", dict(box=(10, 0, 30, 17), pivot=(27, 16), amp_deg=10, period=84, exclude=(28, 14, 52, 31))),
    "hang_glider.bmp": ("lift", dict(boxes=((11, 5, 53, 15), (26, 16, 39, 23)), exclude_colors=(), tol=28, path='lr', bob_amp=1, slope=-0.08, loop=True)),
    "haunted_mansion.bmp": ("combo", (("region_shift", dict(box=(15, 10, 22, 20), axis='y', amp=1, period=22, phase=0, wave='sine')), ("region_shift", dict(box=(42, 10, 49, 20), axis='y', amp=1, period=22, phase=3.14, wave='sine')))),
    "helicopter.bmp": ("combo", (("motion", dict(path='traverse_rl', amp=1, bob_amp=1)), ("blink", dict(box=(5, 4, 60, 7), color=0, period=6, duty=3, delay=0)))),
    "honey_pot.bmp": ("orbiter", dict(cx=32, cy=19, rx=15, ry=10, period=50, wobble=1, clockwise=True, sprite=((0, 0, 0xFFCC00), (1, 0, 0x442200), (2, 0, 0xFFCC00)))),
    # Indy tips his hat: the fedora lifts up to 2px (half='neg' = up-only) after a beat
    # while the coiled whip stays planted, so it reads as a doff, not a floating icon.
    "indiana_hat.bmp": ("region_shift", dict(box=(8, 6, 49, 20), axis='y', amp=2, period=44, wave='sine', half='neg', delay=16)),
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
    "ostrich.bmp": ("cel_walk", dict(period=6, bob=0)),
    "pagoda.bmp": ("palette_pulse", dict(match=(0xFFEEAA, 0xFFEE99, 0xFFDD77, 0xFFDD66, 0xEEBB33), tol=12, lo=0.5, hi=1.5, period=44)),
    "panda.bmp": ("blink", dict(box=(23, 12, 29, 18), color=0x555555, period=48, duty=9, delay=28)),
    # Living with the Land: each leaf rotates INDEPENDENTLY about its own stem joint
    # (pivot at the inner base of each blade), on five different periods so no two move
    # together — the crown rosette turns gentlest and slowest. Stem and soil never move.
    "plant.bmp": ("combo", (("region_rotate", dict(box=(22, 14, 30, 18), pivot=(30, 16), amp_deg=8, period=40)), ("region_rotate", dict(box=(34, 14, 42, 18), pivot=(34, 16), amp_deg=8, period=46)), ("region_rotate", dict(box=(23, 19, 31, 22), pivot=(31, 20), amp_deg=7, period=52)), ("region_rotate", dict(box=(33, 19, 41, 22), pivot=(33, 20), amp_deg=7, period=44)), ("region_rotate", dict(box=(27, 9, 38, 13), pivot=(32, 13), amp_deg=6, period=58)))),
    "poison_apple.bmp": ("palette_pulse", dict(match=(0x88DD55, 0x88CC55, 0x77BB55), tol=20, lo=0.5, hi=1.55, period=36)),
    "pirates.bmp": ("lift", dict(boxes=((1, 4, 62, 27),), exclude_colors=(0x88DDFF, 0x66BBEE, 0x4499EE, 0x2277CC, 0x1166BB, 0x1155AA), tol=28, path='rl', bob_amp=0, slope=0, loop=True)),
    # Gran Fiesta Tour: a tiny red bird (Panchito, yellow crest, fading tail) loops the
    # temple summit — the barn.bmp swallow idiom over the Mexico pavilion pyramid.
    "pyramid.bmp": ("orbiter", dict(cx=32, cy=9, rx=20, ry=6, period=64, clockwise=True, sprite=((0, 0, 0xEE3333), (-1, 0, 0xBB2222), (-2, 0, 0x771111), (0, -1, 0xFFEE55)))),
    "race_car.bmp": ("motion", dict(path='traverse_lr', bob_amp=1)),
    "rat.bmp": ("region_shift", dict(box=(4, 7, 14, 21), axis='y', amp=2, period=18, wave='sine')),
    "river.bmp": ("twinkle", dict(colors=(0x112233, 0x3388AA, 0xCCFFFF), count=18)),
    "riverboat.bmp": ("lift", dict(boxes=((4, 0, 59, 26),), exclude_colors=(0x2288EE, 0x2277CC, 0x2266BB, 0x1155AA, 0x114488, 0x112244), tol=28, path='lr', bob_amp=0, slope=0, loop=True)),
    "rocket.bmp": ("combo", (("motion", dict(path='rise', delay=40)), ("emitter", dict(box=(29, 27, 37, 29), vx=0, vy=0.5, rate=2, life=10, colors=(0xFFEE44, 0xFFAA22, 0xEE4411, 0x662211), max_live=8, jitter=0.3)))),
    "rock_roller.bmp": ("sheen", dict(box=(26, 3, 61, 30), angle=1.35, period=88, width=1.3, gap=0.55)),
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
    # Both eyes blink at once; each blink part covers its eye with the fur gold local to
    # that side of the face (the right side is shaded darker).
    "tiger.bmp": ("combo", (("blink", dict(box=(24, 11, 29, 14), color=0xFFDD55, period=52, duty=8, delay=32)), ("blink", dict(box=(34, 11, 40, 14), color=0xFFCC44, period=52, duty=8, delay=32)))),
    "tiki_bird.bmp": ("region_shift", dict(box=(43, 10, 50, 19), axis='y', amp=1, period=20, wave='sine')),
    "tower_of_terror.bmp": ("palette_pulse", dict(match=(0xFFEE55, 0xFFDD55, 0xFFCC44, 0xFFFF66), tol=20, lo=0.4, hi=1.5, period=28)),
    "transformers.bmp": ("palette_pulse", dict(match=(0xCCEEFF, 0xBBDDFF, 0xBBEEFF), tol=8, lo=0.5, hi=1.6, period=40)),
    "tree.bmp": ("twinkle", dict(colors=(0x224422, 0x88AA44, 0xFFEE88), count=10, box=(14, 1, 50, 19))),
    "tron.bmp": ("lift", dict(boxes=((0, 0, 63, 29),), path='lr', loop=True)),
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
        anim = _build(spec[0], spec[1])
        # Animators that load sibling assets (e.g. a cel-walk spritesheet) need the resolved
        # image path; opt in via ``wants_image_path`` so the 5-arg start() contract is untouched.
        if getattr(anim, "wants_image_path", False):
            anim.image_path = image_path
        return anim
    except Exception:
        return None
