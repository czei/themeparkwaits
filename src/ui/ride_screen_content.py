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

# terminalio glyphs are ~6px wide / ~8px tall. draw_text's `y` is the text
# BASELINE (top-down origin, top-left = 0,0; y=0 clips the glyph off the top), so
# these place the baseline to show each line in its zone (verified by screenshot).
_CHAR_W = 6
_NAME_Y = 5           # ride name (top zone)
_WAIT_Y = 21          # large 2x wait number (bottom zone)
_CLOSED_Y = 21        # "Closed" (single size, bottom zone)


def _to_int_color(color) -> int:
    """Accept an int or a hex string ('0x00AAFF'/'00AAFF') and return an int."""
    if isinstance(color, str):
        return int(color, 16)
    return int(color)


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
            self._name_w = len(self.ride_name) * _CHAR_W
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
    """One ride: scrolling name (top) + large centered wait number (bottom)."""

    def __init__(self, ride_name, wait_minutes, *, name_color=0x0000FF,
                 wait_color=0xFDF5E6, duration=4.0, scroll_step=1.0):
        super().__init__(ride_name, name_color=name_color, duration=duration,
                         scroll_step=scroll_step)
        self.wait_minutes = wait_minutes
        self.wait_color = _to_int_color(wait_color)

    async def render(self, display):
        await self._render_name(display)
        # --- bottom: large centered wait number (2x when the display supports it) ---
        wait_str = str(self.wait_minutes)
        if hasattr(display, "draw_text_scaled"):
            w = len(wait_str) * _CHAR_W * 2
            wx = max(0, (display.width - w) // 2)
            await display.draw_text_scaled(wait_str, wx, _WAIT_Y, self.wait_color, scale=2)
        else:
            wx = max(0, (display.width - len(wait_str) * _CHAR_W) // 2)
            await display.draw_text(wait_str, wx, _WAIT_Y, self.wait_color)

    def describe(self):
        info = super().describe()
        info.update({"ride": self.ride_name, "wait": self.wait_minutes})
        return info


class ClosedRideContent(_ScrollingNameContent):
    """A closed ride: scrolling name (top) + centered 'Closed' (bottom)."""

    def __init__(self, ride_name, *, name_color=0x0000FF, closed_color=0xFDF5E6,
                 duration=4.0, scroll_step=1.0):
        super().__init__(ride_name, name_color=name_color, duration=duration,
                         scroll_step=scroll_step)
        self.closed_color = _to_int_color(closed_color)

    async def render(self, display):
        await self._render_name(display)
        label = "Closed"
        cx = max(0, (display.width - len(label) * _CHAR_W) // 2)
        await display.draw_text(label, cx, _CLOSED_Y, self.closed_color)

    def describe(self):
        info = super().describe()
        info.update({"ride": self.ride_name, "closed": True})
        return info
