"""Dual-zone ride screen content for ThemeParkWaits (library gap — T020).

ScrollKit has no multi-region layout or font scaling, so the product-specific
ride screen (scrolling ride NAME on top + large centered wait NUMBER on the
bottom, or "Closed") is a custom ``DisplayContent``. Per the verified API
(research.md): ``render()`` is async and the framework owns the per-frame
``clear()``/``show()`` — so ``render()`` only draws via ``display.draw_text``.

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


class RideScreenContent(DisplayContent):
    """One ride: scrolling name (top) + large centered wait number (bottom)."""

    def __init__(self, ride_name, wait_minutes, *, name_color=0x0000FF,
                 wait_color=0xFDF5E6, duration=4.0):
        super().__init__(duration=duration, priority=2)
        self.ride_name = ride_name
        self.wait_minutes = wait_minutes
        self.name_color = _to_int_color(name_color)
        self.wait_color = _to_int_color(wait_color)
        self._name_x = None       # set on first render (start from right edge)
        self._name_w = None

    async def start(self):
        await super().start()
        self._name_x = None       # restart the name scroll each time shown

    async def render(self, display):
        # --- top: scrolling ride name ---
        if self._name_x is None:
            self._name_x = display.width
            self._name_w = len(self.ride_name) * _CHAR_W
        await display.draw_text(self.ride_name, self._name_x, _NAME_Y, self.name_color)
        self._name_x -= 1
        if self._name_x < -self._name_w:
            self._name_x = display.width

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


class ClosedRideContent(DisplayContent):
    """A closed ride: scrolling name (top) + centered 'Closed' (bottom)."""

    def __init__(self, ride_name, *, name_color=0x0000FF, closed_color=0xFDF5E6,
                 duration=4.0):
        super().__init__(duration=duration, priority=2)
        self.ride_name = ride_name
        self.name_color = _to_int_color(name_color)
        self.closed_color = _to_int_color(closed_color)
        self._name_x = None
        self._name_w = None

    async def start(self):
        await super().start()
        self._name_x = None

    async def render(self, display):
        if self._name_x is None:
            self._name_x = display.width
            self._name_w = len(self.ride_name) * _CHAR_W
        await display.draw_text(self.ride_name, self._name_x, _NAME_Y, self.name_color)
        self._name_x -= 1
        if self._name_x < -self._name_w:
            self._name_x = display.width

        label = "Closed"
        cx = max(0, (display.width - len(label) * _CHAR_W) // 2)
        await display.draw_text(label, cx, _CLOSED_Y, self.closed_color)

    def describe(self):
        info = super().describe()
        info.update({"ride": self.ride_name, "closed": True})
        return info
