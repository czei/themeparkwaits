"""Dual-zone ride screen content for ThemeParkWaits (library gap — T020).

ScrollKit has no multi-region layout or font scaling, so the product-specific
ride screen (scrolling ride NAME on top + large centered wait NUMBER on the
bottom, or "Closed") is a custom ``DisplayContent``. Per the verified API
(research.md): ``render()`` is async and the framework owns the per-frame
``clear()``/``show()`` — so ``render()`` only draws via ``display.draw_text``.

Advancing: each ride stays until its NAME has scrolled fully across once (so long
names are never cut off mid-scroll), with ``duration`` kept as a *minimum* on-screen
time so short names don't flash past. The scroll-complete check is frame-based, so a
slower device still shows the whole name — it just takes longer in wall-clock.

Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""
from __future__ import annotations

import gc
import math

from scrollkit.display.content import DisplayContent, StaticText
from scrollkit.display.colors import depth_palette
from scrollkit.effects.drip_splash import DripReveal
from scrollkit.effects.text_render import pixels_from_font_text, font_text_width
# Use the SAME displayio the display uses (real on CircuitPython, the simulator's on
# desktop). A bare ``import displayio`` can grab a stray Blinka PyPI package on desktop.
from scrollkit.display.unified import displayio

# Wait-number reveal styles the user can pick (settings: wait_time_effect). The
# value stored is one of these labels; "Rain" is the default and the fallback for
# any unrecognized value. "Rain" drips the digits into place (from a RANDOM edge —
# see DRIP_DIRECTIONS), "Swarm" flies a flock in (lazily imported — heavier boids
# code + ``random`` — so a board using the default never loads it), "SplitFlap"
# flips each digit through a few glyphs before it lands, "None" shows it instantly.
WAIT_EFFECTS = ("Rain", "Swarm", "SplitFlap", "None")

# Edges the "Rain" drip can enter from. Sourced from the library's DripReveal so the
# app stays in lockstep if that set ever changes; the per-ride direction is chosen at
# random in content_builder (never hardcoded to one edge).
DRIP_DIRECTIONS = getattr(DripReveal, "_DIRECTIONS", ("top", "bottom", "left", "right"))

# terminalio glyphs are ~6px wide / ~8px tall. draw_text's `y` is the text
# BASELINE (top-down origin, top-left = 0,0; y=0 clips the glyph off the top), so
# these place the baseline to show each line in its zone (verified by screenshot).
_CHAR_W = 6
_NAME_Y = 5           # ride name (top zone)
_WAIT_Y = 21          # large 2x wait number (bottom zone)
_CLOSED_Y = 21        # "Closed" (single size, bottom zone)

# The wait number drips into a band below the name. We compose it at scale 2 from
# the SAME font/pixels that stay on screen, so the dripped image IS the live image
# (no font/position mismatch, no snap when the drip finishes). The lit pixels are
# vertically centered in [_WAIT_BAND_TOP .. display height].
_WAIT_SCALE = 2
_WAIT_BAND_TOP = 11

# Optional per-ride intro image (see ride_images): a 64x32 silhouette HOLDS, then
# FADES out while the ride name scrolls in; the wait number is gated until NORMAL.
# Frame-counted (not wall-clock) so the fade stays locked to the frame-paced name
# scroll on a slow device (~20fps -> ~1.6s hold, ~1.3s fade).
_INTRO_HOLD_FRAMES = 32
_INTRO_FADE_FRAMES = 26

# Ride-NAME scroll styles (settings: per-ride, chosen in content_builder). "plain"
# is the normal constant-speed scroll; "wave" rides each character on a sine path
# (like WaveRider) so roller-coaster names visibly undulate like a coaster track.
NAME_EFFECTS = ("plain", "wave")

# Wave parameters, reusing WaveRider's integer-sine-table math. Amplitude is kept
# small and the oscillation is centered at _NAME_Y + amplitude so the wavy name
# stays inside the top zone (never above the known-good _NAME_Y baseline, never
# down into the wait-number band at _WAIT_BAND_TOP). Table built once at import.
_WAVE_AMPLITUDE = 2
_WAVE_WAVELENGTH = 16
_WAVE_PHASE_STEP = 8                       # phase advance/frame (full cycle ~32 frames)
_WAVE = tuple(int(round(_WAVE_AMPLITUDE * math.sin(2.0 * math.pi * i / 256.0)))
              for i in range(256))
_WAVE_X_SCALE = 256 // _WAVE_WAVELENGTH
_WAVE_CENTER = _NAME_Y + _WAVE_AMPLITUDE   # oscillates in [_NAME_Y, _NAME_Y + 2*amp]


def _to_int_color(color, default=0xFFFFFF) -> int:
    """Coerce a color to a 24-bit int.

    Tolerates '0x00AAFF', '00AAFF', '#00AAFF' and a stray URL-encoded '%23'
    prefix (an undecoded '#'). Falls back to ``default`` on anything unparseable
    so one malformed setting can't raise out of ``build_content_queue`` — which
    clears the queue first, so a crash there blanks the display (frozen screen).
    """
    if not isinstance(color, str):
        try:
            return int(color)
        except (TypeError, ValueError):
            return default
    s = color.strip()
    if s.startswith("%23"):      # URL-encoded '#'
        s = s[3:]
    elif s.startswith("#"):
        s = s[1:]
    try:
        return int(s, 16)
    except ValueError:
        return default


def _text_width(display, text, scale=1):
    """Rendered width via the library's measure_text (real glyph advances),
    falling back to the fixed-cell estimate if the display lacks it."""
    measure = getattr(display, "measure_text", None)
    if measure is not None:
        return measure(text) * scale
    return len(text) * _CHAR_W * scale


def _name_gradient_stops(color):
    """Two distinct vertical-gradient stops (lighter TOP -> deeper BOTTOM) derived
    from the ride-name colour.

    The single-hue ``depth_palette()`` used for "Closed" is too subtle for the
    scrolling name at this glyph size, so this lifts the top ~45% toward white and
    drops the bottom to ~45% of the base — same hue, but with enough separation to
    survive the panel's RGB444 truncation (every channel stays well over 0x20
    apart). Returned as ``(top, bottom)`` to hand straight to a two-stop palette.
    """
    r, g, b = (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF
    top = (((r + (255 - r) * 45 // 100) << 16)
           | ((g + (255 - g) * 45 // 100) << 8)
           | (b + (255 - b) * 45 // 100))
    bottom = ((r * 45 // 100) << 16) | ((g * 45 // 100) << 8) | (b * 45 // 100)
    return top, bottom


class _ScrollingNameContent(DisplayContent):
    """Base for a ride screen: a name that scrolls across the top exactly once.

    Completion is keyed on the name finishing one full pass (right edge → off the
    left), so a long name is never cut off. ``duration`` is the minimum time the
    screen stays up (keeps short names from flashing by). Subclasses draw the lower
    zone (the wait number or "Closed") in ``render()`` after calling ``_render_name``.
    """

    def __init__(self, ride_name, *, name_color=0x0000FF, duration=4.0, scroll_step=1.0,
                 name_effect="plain", name_content=None, intro_image=None,
                 name_gradient=False):
        # We own completion (see is_complete), so the base never times us out
        # mid-scroll; duration becomes the minimum on-screen time.
        super().__init__(duration=None, priority=2)
        self._min_duration = duration
        # Pixels the name moves per displayed frame: >1 faster, <1 slower. The
        # Scroll Speed setting maps to this (see content_builder). Position is kept
        # as a float so sub-1px/frame ("Slow") scrolls genuinely slower.
        self._scroll_step = scroll_step if scroll_step and scroll_step > 0 else 1.0
        self.ride_name = ride_name
        self.name_color = _to_int_color(name_color)
        self.name_effect = name_effect if name_effect in NAME_EFFECTS else "plain"
        # Vertical two-tone gradient on the scrolling name (lighter top -> deeper
        # bottom), drawn as a moving TileGrid layer built once (zero per-frame pixel
        # writes). Off -> the flat draw_text fallback. Skipped in "wave" mode and
        # when an embedded catalog effect owns the name. Relies on the library's
        # baseline-aligned pixels_from_font_text (4acc2ba) so mixed-case names with
        # descenders place correctly; if the gradient layer can't be built it falls
        # back to the flat path (see _render_name_gradient).
        self._name_gradient = bool(name_gradient)
        self._name_grad = None          # the _GradientTextLayer (built on 1st render)
        self._name_grad_failed = False  # build failed once -> stay flat (no retry/frame)
        # Optional embedded scrolling-effect content (chosen at random from the live
        # ScrollKit catalog) that renders the NAME in the top zone. When set it OWNS
        # the name scroll + completion; the built-in plain/wave path is the fallback.
        # The wait NUMBER below is rendered by the subclass either way — untouched.
        self._name_content = name_content
        self._name_x = None        # set on first render (start from right edge)
        self._name_w = None
        self._scrolled_off = False
        self._char_offsets = None  # cumulative per-char x offsets (wave mode), measured once
        self._wave_phase = 0
        # Optional intro image: a transparent overlay that holds then fades while the
        # name scrolls in. Loaded lazily on the first HOLD frame; only the on-screen
        # ride's image is ever resident (released in stop()).
        self._intro_image = intro_image
        self._intro_phase = None       # "hold" | "fade" | None (None = normal screen)
        self._intro_frame = 0
        self._intro_tile = None
        self._intro_palette = None
        self._intro_base_colors = None
        self._intro_odb = None
        self._display = None

    async def start(self):
        await super().start()
        self._name_x = None        # restart the name scroll each time shown
        self._scrolled_off = False
        self._char_offsets = None
        self._wave_phase = 0
        self._detach_name_grad()   # rebuild the moving gradient layer on (re)show
        # Replay the intro each time the screen is shown (every display cycle).
        self._intro_phase = "hold" if self._intro_image else None
        self._intro_frame = 0
        if self._name_content is not None:
            await self._name_content.start()

    async def stop(self):
        await super().stop()
        if self._name_content is not None:
            await self._name_content.stop()
        self._detach_name_grad()
        # Detach the intro overlay so a mid-intro teardown can't strand it on screen,
        # and free the bitmap/palette promptly (on-device RAM hygiene).
        self._detach_intro()
        self._intro_phase = None
        self._intro_frame = 0
        gc.collect()

    async def _intro_step(self, display):
        """Advance the intro for this frame.

        Returns ``True`` while the intro owns the frame (the caller must return without
        drawing the normal screen), ``False`` once the screen should render normally.
        HOLD shows the still image; FADE darkens it WHILE the name scrolls in; when the
        fade finishes the overlay is detached and the next frame is NORMAL — at which
        point the existing ``_need_reveal`` path builds the wait-number reveal (so the
        number is gated to land exactly as the image clears).
        """
        if self._intro_phase is None:
            return False
        if self._intro_phase == "hold":
            if self._intro_tile is None and self._intro_image:
                self._load_intro(display)            # lazy: load on the first hold frame
                if self._intro_phase is None:        # load failed -> normal screen now
                    return False
            self._intro_frame += 1
            if self._intro_frame >= _INTRO_HOLD_FRAMES:
                self._intro_phase = "fade"
                self._intro_frame = 0
            return True
        # "fade": darken the image while the name scrolls in (concurrent)
        denom = _INTRO_FADE_FRAMES - 1 if _INTRO_FADE_FRAMES > 1 else 1
        f = 1.0 - self._intro_frame / denom
        if f < 0.0:
            f = 0.0
        self._fade_intro(f)
        await self._render_name(display)
        self._intro_frame += 1
        if self._intro_frame >= _INTRO_FADE_FRAMES:
            self._detach_intro()                     # free the layer the instant it's gone
            self._intro_phase = None                 # next frame renders the normal screen
        return True

    def _load_intro(self, display):
        """Load the intro bitmap as a transparent overlay layer (lazy, defensive).

        On any failure (missing/corrupt file, or a non-indexed BMP whose pixel_shader
        is not a writable Palette we can fade) it abandons the intro and falls straight
        through to the normal screen — never blanks.
        """
        try:
            odb = displayio.OnDiskBitmap(self._intro_image)
            pal = odb.pixel_shader
            # We fade by rewriting palette entries, so we need a mutable, indexable
            # Palette. Probe it FUNCTIONALLY, not with hasattr: on CircuitPython native
            # types implement len()/subscription via C type-slots, so
            # hasattr(pal, "__len__"/"__setitem__") is False on-device even though they
            # work. A non-indexed BMP yields a ColorConverter (no len/subscript) which
            # raises here -> the outer except falls through to the normal screen.
            len(pal)
            pal[0]
            pal.make_transparent(0)                  # index 0 = sky (authoring keeps it slot 0)
            # Capture the un-faded colors as RGB888 so _scale_color is correct on both
            # platforms: CircuitPython's Palette[i] is already RGB888, but the simulator
            # stores RGB565 internally and exposes the true color via get_rgb888().
            get888 = getattr(pal, "get_rgb888", None)
            if get888 is not None:                   # simulator: ints may be np.uint8
                self._intro_base_colors = [
                    (int(c[0]) << 16) | (int(c[1]) << 8) | int(c[2])
                    for c in (get888(i) for i in range(len(pal)))]
            else:
                self._intro_base_colors = [pal[i] for i in range(len(pal))]
            # CircuitPython: the OnDiskBitmap IS the bitmap. Simulator: the Bitmap is
            # at odb.bitmap (the OnDiskBitmap shim isn't subscriptable).
            bmp = getattr(odb, "bitmap", odb)
            tile = displayio.TileGrid(bmp, pixel_shader=pal)
            display.add_layer(tile)
            self._display = display
            self._intro_odb = odb
            self._intro_tile = tile
            self._intro_palette = pal
        except Exception:
            self._detach_intro()
            self._intro_phase = None

    def _fade_intro(self, f):
        """Scale every non-sky palette entry to ``f`` of its original color."""
        pal, base = self._intro_palette, self._intro_base_colors
        if pal is None or base is None:
            return
        for i in range(1, len(base)):
            pal[i] = _scale_color(base[i], f)

    def _detach_intro(self):
        """Remove the overlay layer and drop refs (idempotent)."""
        if self._intro_tile is not None and self._display is not None:
            try:
                self._display.remove_layer(self._intro_tile)
            except Exception:
                pass
        self._intro_tile = None
        self._intro_palette = None
        self._intro_base_colors = None
        self._intro_odb = None

    async def _render_name(self, display):
        """Draw + advance the scrolling name; mark complete after one full pass."""
        if self._name_content is not None:
            # The embedded catalog effect draws the name in the top zone and tracks
            # its own scroll position / completion (see is_complete).
            await self._name_content.render(display)
            return
        if self._name_x is None:
            self._name_x = display.width
            self._name_w = _text_width(display, self.ride_name)
        if self.name_effect == "wave":
            await self._render_name_wave(display)
        elif self._name_gradient:
            await self._render_name_gradient(display)
        else:
            # Flat single-colour fallback (gradient off). The gradient-text
            # rasteriser used to top-align every glyph, which clipped cap tops on
            # mixed-case names with descenders ("Space Mountain") — so the name was
            # forced flat. pixels_from_font_text now baseline-aligns glyphs
            # (library 4acc2ba), so the gradient path is correct and default; this
            # stays as the off/fallback path.
            await display.draw_text(self.ride_name, int(self._name_x), _NAME_Y, self.name_color)
        self._name_x -= self._scroll_step
        if self._name_x <= -self._name_w:
            # One full pass done: park it off-screen (don't loop) and let
            # is_complete advance to the next ride.
            self._scrolled_off = True
            self._name_x = -self._name_w

    async def _render_name_wave(self, display):
        """Draw the name with each character riding a sine path (coaster-like).

        Reuses WaveRider's integer-table math (``_WAVE``), but centered so the
        undulation stays in the top zone. Per-char x offsets are measured once
        (they don't change as the whole name scrolls); only the visible window is
        drawn. ``draw_text`` per glyph is heavier than one whole-string call, but
        it's a short name and well within the per-frame budget (verified headless).
        """
        if self._char_offsets is None:
            offs = []
            cum = 0
            measure = getattr(display, "measure_text", None)
            for ch in self.ride_name:
                offs.append(cum)
                cum += (measure(ch) if measure is not None else _CHAR_W) or _CHAR_W
            self._char_offsets = offs
        base_x = int(self._name_x)
        w = display.width
        phase = self._wave_phase
        name = self.ride_name
        for i in range(len(name)):
            x = base_x + self._char_offsets[i]
            if x <= -_CHAR_W or x >= w:
                continue                       # off-screen glyph: skip
            yy = _WAVE_CENTER + _WAVE[(x // _WAVE_X_SCALE + phase) & 255]
            await display.draw_text(name[i], x, yy, self.name_color)
        self._wave_phase = (self._wave_phase + _WAVE_PHASE_STEP) & 255

    async def _render_name_gradient(self, display):
        """Draw the scrolling name as a vertical two-tone gradient.

        The name is rasterised ONCE into the library's ``_GradientTextLayer`` (an
        indexed bitmap + TileGrid that the layer's own ``tile.y = y + 4 - ascent``
        baseline-aligns to the flat ``draw_text`` path), then SCROLLED by moving the
        TileGrid each frame — zero per-frame pixel writes, the same model
        ``StaticText``/``ScrollingText`` use. Its width drives completion (kept in
        lockstep with ``_name_w``). If the layer can't be built (older library
        without the baseline fix, or no font headless) it falls back to a flat
        ``draw_text`` once and stays flat — never blanks the name.
        """
        if self._name_grad is None and not self._name_grad_failed:
            try:
                from scrollkit.display.gradient_text import _GradientTextLayer
                top, bottom = _name_gradient_stops(self.name_color)
                grad = _GradientTextLayer(self.ride_name, _NAME_Y,
                                          palette=(top, bottom), direction="vertical")
                grad.build(display)
                self._name_grad = grad
                self._display = display          # for _detach_name_grad in stop()
                self._name_w = grad.width        # completion in lockstep with the layer
            except Exception:
                self._name_grad_failed = True
        if self._name_grad is not None:
            self._name_grad.x = int(self._name_x)
        else:
            await display.draw_text(self.ride_name, int(self._name_x), _NAME_Y, self.name_color)

    def _detach_name_grad(self):
        """Remove the scrolling-name gradient layer and drop its ref (idempotent)."""
        if self._name_grad is not None and self._display is not None:
            try:
                self._name_grad.detach(self._display)
            except Exception:
                pass
        self._name_grad = None

    @property
    def is_complete(self):
        if self._is_complete:
            return True
        if self._intro_phase is not None:
            return False        # never advance while the intro is still playing
        # Advance once the name has scrolled fully across, never before the minimum.
        if self._name_content is not None:
            return self._name_content.is_complete and self.elapsed >= self._min_duration
        return self._scrolled_off and self.elapsed >= self._min_duration


# Wait-number colour-animation styles — both KEEP the severity colour: a highlight
# band SWEEPS across the digits ("sheen") or the whole number BREATHES dim<->bright
# ("pulse"). Size/position never change (layout-safe).
NUMBER_STYLES = ("sheen", "pulse")
_NUM_RAMP = 6          # animated brightness shades per depth band
_NUM_PERIOD = 2        # advance the animation every N frames (calmer motion)
_NUM_DEPTH_STRENGTH = 0.35   # top (lit) -> bottom (shadow) depth, same depth_palette
                              # "lit from above" look gradient text uses elsewhere


def _scale_color(color, f):
    """Scale a 24-bit color toward black by factor ``f`` (1.0 = full, 0.0 = black)."""
    r = int(((color >> 16) & 0xFF) * f)
    g = int(((color >> 8) & 0xFF) * f)
    b = int((color & 0xFF) * f)
    return (r << 16) | (g << 8) | b


def _color_shades(color, n):
    """``n`` shades of ``color`` from dim to full (a brightness ramp of one hue)."""
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    shades = []
    for i in range(n):
        f = 0.30 + 0.70 * (i / (n - 1) if n > 1 else 1.0)
        shades.append((int(r * f) << 16) | (int(g * f) << 8) | int(b * f))
    return shades


class _PaletteNumberReveal:
    """Shows the wait-number pixels assembled with a static TWO-BAND vertical depth
    (top band lit, bottom band shadowed — the same depth_palette() "lit from above"
    look gradient text uses) and ANIMATES COLOUR ON TOP OF IT while KEEPING the
    severity colour: "sheen" sends a bright band sweeping across the digits in both
    depth bands at once; "pulse" breathes the whole number dim<->bright. Same
    ``start()/step()/detach()`` contract as ``DripReveal`` — the number sits in the
    SAME place at the SAME 2x size, only the colour moves (layout untouched).

    Pure palette rewrites (<= 2*_NUM_RAMP entries/frame), no per-frame pixel writes.
    """

    def __init__(self, pixels, color, style="sheen"):
        self.pixels = pixels
        self.color = color
        self.style = style if style in NUMBER_STYLES else "sheen"
        self._display = None
        self._tile = None
        self._palette = None
        self._shades_top = None
        self._shades_bottom = None
        self._phase = 0
        self._tick = 0
        self._started = False

    def start(self, display):
        gfx = display.gfx
        w, h = display.width, display.height
        n = _NUM_RAMP
        top_color, bottom_color = depth_palette(self.color, strength=_NUM_DEPTH_STRENGTH)
        self._shades_top = _color_shades(top_color, n)
        self._shades_bottom = _color_shades(bottom_color, n)
        bitmap = gfx.Bitmap(w, h, 2 * n + 1)
        palette = gfx.Palette(2 * n + 1)
        palette.make_transparent(0)              # composite over the name below
        for i in range(n):
            palette[1 + i] = self._shades_top[i]
            palette[1 + n + i] = self._shades_bottom[i]
        # "pulse": every lit pixel shares one slot per band (uniform breathe);
        # "sheen": index by column so rotating the ramp sweeps a highlight across
        # the digits — in both depth bands at once, same phase.
        uniform = self.style == "pulse"
        ys = [py for (_px, py) in self.pixels]
        mid_y = (min(ys) + max(ys)) / 2.0 if ys else 0
        for (x, y) in self.pixels:
            if 0 <= x < w and 0 <= y < h:
                band = 0 if y <= mid_y else n
                ramp_i = 0 if uniform else (x % n)
                bitmap[x, y] = band + ramp_i + 1
        tile = gfx.TileGrid(bitmap, pixel_shader=palette)
        display.add_layer(tile)
        self._display = display
        self._tile = tile
        self._palette = palette
        self._started = True

    @property
    def has_pixels(self):
        return bool(self.pixels)

    @property
    def is_complete(self):
        return False        # the colour animates every frame until the ride advances

    def step(self):
        if not self._started:
            return False
        self._tick += 1
        if self._tick < _NUM_PERIOD:
            return False
        self._tick = 0
        self._phase += 1
        n = _NUM_RAMP
        if self.style == "pulse":
            t = self._phase % (2 * n)            # triangle wave dim->bright->dim
            idx = t if t < n else (2 * n - 1 - t)
            self._palette[1] = self._shades_top[idx]
            self._palette[1 + n] = self._shades_bottom[idx]
        else:
            for i in range(n):                   # rotate the ramp -> sweeping sheen
                self._palette[1 + i] = self._shades_top[(i + self._phase) % n]
                self._palette[1 + n + i] = self._shades_bottom[(i + self._phase) % n]
        return False

    def detach(self):
        if self._display is not None and self._tile is not None:
            self._display.remove_layer(self._tile)
        self._tile = None
        self._display = None
        self._palette = None
        self._started = False


# Split-flap reveal tuning. Each digit cycles through _FLAP_STEPS random glyphs,
# successive digits start _FLAP_STAGGER frames apart, and a flip advances every
# _FLAP_PERIOD display frames (a readable departure-board cadence, not a blur).
_FLAP_STEPS = 4
_FLAP_STAGGER = 3
_FLAP_PERIOD = 2
_FLAP_ALPHABET = "0123456789"


class _SplitFlapNumberReveal:
    """Assembles the 2x wait NUMBER like a split-flap board: each digit flips through
    a few random digits before LANDING on its real value, staggered left-to-right.

    Same ``start()/step()/is_complete/detach()`` contract as ``DripReveal`` — once
    every digit has landed the overlay holds the real number (the landed pixels ARE
    the live number, so nothing is swapped in). The glyphs are composed from the SAME
    font/scale and centered in the SAME wait band as ``_number_pixels``/the other
    reveals, so the final number is identical in place + size (layout untouched).

    Per-glyph pixels are precomputed in ``start()`` (no per-frame allocation); each
    advanced frame clears the bitmap and writes only the currently-shown glyphs —
    bounded, hardware-safe like ``DripReveal``.
    """

    def __init__(self, text, color, *, seed=1):
        self.text = text
        self.color = color
        self.seed = seed
        self._display = None
        self._bitmap = None
        self._tile = None
        self._w = 0
        self._h = 0
        self._cells = ()           # per digit: tuple of pixel-lists (steps... then final)
        self._frame = 0
        self._tick = 0
        self._last_land = 0
        self._started = False

    def start(self, display):
        gfx = display.gfx
        w, h = display.width, display.height
        self._w, self._h = w, h
        bitmap = gfx.Bitmap(w, h, 2)
        palette = gfx.Palette(2)
        palette.make_transparent(0)            # composite over the name below
        palette[1] = self.color
        tile = gfx.TileGrid(bitmap, pixel_shader=palette)
        display.add_layer(tile)
        self._display = display
        self._bitmap = bitmap
        self._tile = tile
        self._frame = 0
        self._tick = 0
        self._started = True

        font = getattr(display, "font", None)
        if font is None or not self.text:
            self._cells = ()
            self._last_land = 0
            return
        # Center the whole number; derive the vertical placement from the FINAL string
        # so every (equal-height) digit glyph aligns in the wait band.
        total_w = font_text_width(font, self.text, scale=_WAIT_SCALE)
        x0 = max(0, (w - total_w) // 2)
        final_raw = pixels_from_font_text(font, self.text, x=x0, y=0, scale=_WAIT_SCALE)
        if final_raw:
            min_y = min(p[1] for p in final_raw)
            ink_h = max(p[1] for p in final_raw) - min_y + 1
            center = (_WAIT_BAND_TOP + h) // 2
            top = center - ink_h // 2
            if top < _WAIT_BAND_TOP:
                top = _WAIT_BAND_TOP
            if top + ink_h > h:
                top = h - ink_h
            dy = top - min_y
        else:
            dy = 0
        # Deterministic intermediate digits from a seeded LCG (no per-frame random).
        state = (self.seed * 2654435761 + 1) & 0x7FFFFFFF
        cells = []
        cell_x = x0
        for ch in self.text:
            seq = []
            for _ in range(_FLAP_STEPS):
                state = (state * 1103515245 + 12345) & 0x7FFFFFFF
                seq.append(_FLAP_ALPHABET[state % len(_FLAP_ALPHABET)])
            frames = []
            for glyph in tuple(seq) + (ch,):       # intermediates, then the real digit
                px = pixels_from_font_text(font, glyph, x=cell_x, y=0, scale=_WAIT_SCALE)
                frames.append([(x, py + dy) for (x, py) in px])
            cells.append(tuple(frames))
            cell_x += font_text_width(font, ch, scale=_WAIT_SCALE)
        self._cells = tuple(cells)
        # Last digit starts at (n-1)*stagger and lands _FLAP_STEPS frames later.
        self._last_land = (len(cells) - 1) * _FLAP_STAGGER + _FLAP_STEPS if cells else 0

    @property
    def has_pixels(self):
        return bool(self._cells)

    @property
    def is_complete(self):
        return self._started and self._frame > self._last_land

    def step(self):
        if not self._started or self.is_complete:
            return True
        self._tick += 1
        if self._tick < _FLAP_PERIOD:
            return False                       # hold the current glyphs (cadence)
        self._tick = 0
        b = self._bitmap
        try:
            b.fill(0)
        except (AttributeError, TypeError):
            for xx in range(self._w):
                for yy in range(self._h):
                    b[xx, yy] = 0
        f = self._frame
        for i, frames in enumerate(self._cells):
            local = f - i * _FLAP_STAGGER
            if local < 0:
                continue                       # this digit hasn't started flipping yet
            idx = local if local < _FLAP_STEPS else _FLAP_STEPS   # then land on final
            for (x, y) in frames[idx]:
                if 0 <= x < self._w and 0 <= y < self._h:
                    b[x, y] = 1
        self._frame += 1
        return self.is_complete

    def detach(self):
        if self._display is not None and self._tile is not None:
            self._display.remove_layer(self._tile)
        self._tile = None
        self._display = None
        self._bitmap = None
        self._started = False


class RideScreenContent(_ScrollingNameContent):
    """One ride: scrolling name (top) + large wait number revealed into place.

    The wait number is revealed (animated into its target pixels) the first time
    the screen is shown, then the assembled overlay stays up as the live number
    while the name finishes scrolling. The reveal and the live number are the same
    composed pixels — there is no separate "draw the number" step and so no
    visible change when the reveal lands.

    The reveal style is the ``effect`` argument (see ``WAIT_EFFECTS``):
    ``"Rain"`` drips each column down (default), ``"Swarm"`` flies a flock in to
    assemble it, ``"None"`` shows it instantly. All three land the SAME pixels in
    the SAME place — only the animation differs.
    """

    def __init__(self, ride_name, wait_minutes, *, name_color=0x0000FF,
                 wait_color=0xFDF5E6, duration=4.0, scroll_step=1.0, effect="Rain",
                 name_effect="plain", name_content=None, number_style=None,
                 drip_direction="top", intro_image=None, name_gradient=False):
        super().__init__(ride_name, name_color=name_color, duration=duration,
                         scroll_step=scroll_step, name_effect=name_effect,
                         name_content=name_content, intro_image=intro_image,
                         name_gradient=name_gradient)
        self.wait_minutes = wait_minutes
        self.wait_color = _to_int_color(wait_color)
        self._wait_str = str(wait_minutes)
        self.effect = effect if effect in WAIT_EFFECTS else "Rain"
        # Edge the "Rain" drip enters from (top/bottom/left/right); ignored by the
        # other reveals. Defaults to the classic top; randomized in content_builder.
        self._drip_direction = drip_direction if drip_direction in DRIP_DIRECTIONS else "top"
        # A colour-animation style ("sheen"/"pulse") -> the big 2x number is shown
        # assembled and its COLOUR animates IN ITS SEVERITY COLOUR (wait_color); the
        # layout is unchanged. When set it takes precedence over the Rain/Swarm reveal.
        self._number_style = number_style
        self._reveal = None          # the reveal effect (built on 1st render)
        self._need_reveal = True     # (re)build the reveal on (re)show

    async def start(self):
        await super().start()
        # Replay the reveal each time the screen is shown. The old overlay (if any)
        # is detached on the previous stop(); here we just flag a rebuild.
        self._need_reveal = True

    def _number_pixels(self, display):
        """Composed wait-number pixels, centered and dropped into the wait band."""
        font = getattr(display, "font", None)
        if font is None:
            return None
        w = font_text_width(font, self._wait_str, scale=_WAIT_SCALE)
        x = max(0, (display.width - w) // 2)
        raw = pixels_from_font_text(font, self._wait_str, x=x, y=0, scale=_WAIT_SCALE)
        if not raw:
            return None
        min_y = min(p[1] for p in raw)
        max_y = max(p[1] for p in raw)
        ink_h = max_y - min_y + 1
        # Vertically center the inked rows in the band below the name.
        center = (_WAIT_BAND_TOP + display.height) // 2
        top = center - ink_h // 2
        if top < _WAIT_BAND_TOP:
            top = _WAIT_BAND_TOP
        if top + ink_h > display.height:
            top = display.height - ink_h
        dy = top - min_y
        return [(px, py + dy) for (px, py) in raw]

    def _build_reveal(self, pixels):
        """The reveal effect holding ``pixels`` as its target.

        A ``number_style`` ("sheen"/"pulse") takes precedence: the number appears
        assembled and its colour animates IN ITS SEVERITY COLOUR (layout-safe).
        Otherwise "Swarm" is imported lazily (heavier flocking), "SplitFlap" flips
        each digit through a few glyphs before landing, and "Rain" drips the digits
        in from a RANDOM edge (``self._drip_direction``); "None" is fast-forwarded to
        settled in render(). All land the SAME pixels in the SAME place.
        """
        if self._number_style is not None:
            return _PaletteNumberReveal(pixels, self.wait_color, self._number_style)
        if self.effect == "Swarm":
            from scrollkit.effects.swarm_reveal import SwarmReveal
            # Swarm is built for the boot splash; for a per-ride number we push the
            # flock to the on-device ceiling (num_birds<=~20, ~34 ms/frame — under
            # the 50 ms budget, and only during the ~2-4 s assembly) so the number
            # forms before the screen advances. The digits are readable once
            # captured, before the brief disperse tail finishes.
            #
            # Assemble the digits in a vertical depth ramp of the severity colour
            # (full at the top fading toward a darker shade at the bottom) — the
            # same "lit from above" gradient-text look used elsewhere on the board,
            # generated rather than hand-picked, while STILL encoding severity
            # (every stop is the same green/yellow/red hue, only darker). The fade
            # floors at 0.60 so the bottom rows stay legible.
            ramp = depth_palette(self.wait_color, strength=0.40, steps=_NUM_RAMP)
            return SwarmReveal(pixels, text_color=self.wait_color,
                               text_colors=ramp, color_axis="vertical",
                               bird_color=self.wait_color, num_birds=20,
                               bird_speed=4.0)
        if self.effect == "SplitFlap":
            # Composes its own per-digit glyphs from the wait string (it flips through
            # intermediate digits, so the pre-composed `pixels` aren't the whole story).
            return _SplitFlapNumberReveal(self._wait_str, self.wait_color)
        return DripReveal(pixels, color=self.wait_color, fall_speed=2, stagger=1,
                          direction=self._drip_direction)

    async def render(self, display):
        if await self._intro_step(display):
            return                       # intro owns the frame (hold / fade+scroll)
        await self._render_name(display)
        # --- bottom: large wait number, revealed into place then held ---
        if self._need_reveal:
            if self._reveal is not None:
                self._reveal.detach()
                self._reveal = None
            try:
                pixels = self._number_pixels(display)
                if pixels:
                    self._reveal = self._build_reveal(pixels)
                    self._reveal.start(display)
                    if self._number_style is None and self.effect == "None":
                        # No animation: paint straight to the assembled number.
                        # (Never fast-forward a colour animation — it never "settles".)
                        while not self._reveal.step():
                            pass
            except Exception:
                self._reveal = None      # never let the number blank the screen
            self._need_reveal = False
        if self._reveal is not None and not self._reveal.is_complete:
            self._reveal.step()          # advance one frame; overlay persists when done

    async def stop(self):
        await super().stop()
        if self._reveal is not None:
            self._reveal.detach()
            self._reveal = None
        self._need_reveal = True

    def describe(self):
        info = super().describe()
        info.update({"ride": self.ride_name, "wait": self.wait_minutes,
                     "effect": self.effect})
        return info


class ClosedRideContent(_ScrollingNameContent):
    """A closed ride: scrolling name (top) + centered 'Closed' (bottom).

    "Closed" is the one status word in the ride screen that always reads the same
    way (the wait NUMBER already has its own severity-colour reveal animations), so
    it's the deliberate, consistent spot for the new gradient text fill rather than
    one more randomized effect: a subtle vertical depth_palette ramp off the
    configured closed colour ("lit from above"), not a flat fill.
    """

    def __init__(self, ride_name, *, name_color=0x0000FF, closed_color=0xFDF5E6,
                 duration=4.0, scroll_step=1.0, name_effect="plain", name_content=None,
                 intro_image=None, name_gradient=False):
        super().__init__(ride_name, name_color=name_color, duration=duration,
                         scroll_step=scroll_step, name_effect=name_effect,
                         name_content=name_content, intro_image=intro_image,
                         name_gradient=name_gradient)
        self.closed_color = _to_int_color(closed_color)
        self._closed_x = None        # centered x; measured once on first render
        self._closed = StaticText("Closed", y=_CLOSED_Y,
                                  palette=depth_palette(self.closed_color))

    async def start(self):
        await super().start()
        self._closed_x = None        # re-measure + rebuild the gradient layer on re-show
        await self._closed.start()

    async def stop(self):
        await super().stop()
        await self._closed.stop()

    async def render(self, display):
        if await self._intro_step(display):
            return                       # intro owns the frame (hold / fade+scroll)
        await self._render_name(display)
        if self._closed_x is None:
            self._closed_x = max(0, (display.width - _text_width(display, self._closed.text)) // 2)
            self._closed.x = self._closed_x
        await self._closed.render(display)

    def describe(self):
        info = super().describe()
        info.update({"ride": self.ride_name, "closed": True})
        return info
