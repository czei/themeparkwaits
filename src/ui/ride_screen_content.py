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

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

from scrollkit.display.content import DisplayContent
from scrollkit.effects.drip_splash import DripReveal
from scrollkit.effects.text_render import pixels_from_font_text, font_text_width

# Wait-number reveal styles the user can pick (settings: wait_time_effect). The
# value stored is one of these labels; "Rain" is the default and the fallback for
# any unrecognized value. "Swarm" is lazily imported (heavier boids code +
# ``random``) so a board using the default never loads it.
WAIT_EFFECTS = ("Rain", "Swarm", "None")

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


class _ScrollingNameContent(DisplayContent):
    """Base for a ride screen: a name that scrolls across the top exactly once.

    Completion is keyed on the name finishing one full pass (right edge → off the
    left), so a long name is never cut off. ``duration`` is the minimum time the
    screen stays up (keeps short names from flashing by). Subclasses draw the lower
    zone (the wait number or "Closed") in ``render()`` after calling ``_render_name``.
    """

    def __init__(self, ride_name, *, name_color=0x0000FF, duration=4.0, scroll_step=1.0):
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
        self._name_x = None        # set on first render (start from right edge)
        self._name_w = None
        self._scrolled_off = False

    async def start(self):
        await super().start()
        self._name_x = None        # restart the name scroll each time shown
        self._scrolled_off = False

    async def _render_name(self, display):
        """Draw + advance the scrolling name; mark complete after one full pass."""
        if self._name_x is None:
            self._name_x = display.width
            self._name_w = _text_width(display, self.ride_name)
        await display.draw_text(self.ride_name, int(self._name_x), _NAME_Y, self.name_color)
        self._name_x -= self._scroll_step
        if self._name_x <= -self._name_w:
            # One full pass done: park it off-screen (don't loop) and let
            # is_complete advance to the next ride.
            self._scrolled_off = True
            self._name_x = -self._name_w

    @property
    def is_complete(self):
        if self._is_complete:
            return True
        # Advance once the name has scrolled fully across, never before the minimum.
        return self._scrolled_off and self.elapsed >= self._min_duration


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
                 wait_color=0xFDF5E6, duration=4.0, scroll_step=1.0, effect="Rain"):
        super().__init__(ride_name, name_color=name_color, duration=duration,
                         scroll_step=scroll_step)
        self.wait_minutes = wait_minutes
        self.wait_color = _to_int_color(wait_color)
        self._wait_str = str(wait_minutes)
        self.effect = effect if effect in WAIT_EFFECTS else "Rain"
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
        """The reveal effect for ``self.effect``, holding ``pixels`` as its target.

        "Swarm" is imported lazily so the default ("Rain") board never loads the
        heavier flocking code. "None" reuses the drip object but is fast-forwarded
        to its settled frame in render() (so the number just appears). Any
        unrecognized value already fell back to "Rain" in __init__.
        """
        if self.effect == "Swarm":
            from scrollkit.effects.swarm_reveal import SwarmReveal
            # Swarm is built for the boot splash; for a per-ride number we push the
            # flock to the on-device ceiling (num_birds<=~20, ~34 ms/frame — under
            # the 50 ms budget, and only during the ~2-4 s assembly) so the number
            # forms before the screen advances. The digits are readable once
            # captured, before the brief disperse tail finishes.
            return SwarmReveal(pixels, text_color=self.wait_color,
                               bird_color=self.wait_color, num_birds=20,
                               bird_speed=4.0)
        return DripReveal(pixels, color=self.wait_color, fall_speed=2, stagger=1)

    async def render(self, display):
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
                    if self.effect == "None":
                        # No animation: paint straight to the assembled number.
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
    """A closed ride: scrolling name (top) + centered 'Closed' (bottom)."""

    def __init__(self, ride_name, *, name_color=0x0000FF, closed_color=0xFDF5E6,
                 duration=4.0, scroll_step=1.0):
        super().__init__(ride_name, name_color=name_color, duration=duration,
                         scroll_step=scroll_step)
        self.closed_color = _to_int_color(closed_color)
        self._closed_x = None        # centered x; measured once on first render

    async def render(self, display):
        await self._render_name(display)
        label = "Closed"
        if self._closed_x is None:
            self._closed_x = max(0, (display.width - _text_width(display, label)) // 2)
        await display.draw_text(label, self._closed_x, _CLOSED_Y, self.closed_color)

    def describe(self):
        info = super().describe()
        info.update({"ride": self.ride_name, "closed": True})
        return info
