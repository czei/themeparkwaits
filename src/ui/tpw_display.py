"""ThemeParkDisplay — UnifiedDisplay + a scaled-text primitive (library gap).

ScrollKit's ``draw_text`` renders at the font's native size; the ride screen
needs a large (2x) wait-time number. This subclass adds ``draw_text_scaled``
backed by its own reuse pool, mirroring the library's per-frame label-pool
discipline (reuse + mutate, hide-unused-in-show, reset-index-in-clear) so the
big number stays allocation-free per frame (FR-019/020).

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

from scrollkit.display.unified import UnifiedDisplay, Label


class ThemeParkDisplay(UnifiedDisplay):
    """UnifiedDisplay plus ``draw_text_scaled`` for the large wait-time number."""

    def __init__(self, width: int = 64, height: int = 32, bit_depth: int = 4):
        super().__init__(width, height, bit_depth)
        self._scaled_pool = []
        self._scaled_idx = 0

    async def clear(self) -> None:
        await super().clear()
        self._scaled_idx = 0

    async def show(self) -> bool:
        # Hide scaled-pool labels not drawn this frame, then let the base hide its
        # own pool + refresh.
        for i in range(self._scaled_idx, len(self._scaled_pool)):
            lbl = self._scaled_pool[i]
            if hasattr(lbl, "hidden"):
                lbl.hidden = True
        return await super().show()

    async def draw_text_scaled(self, text, x=0, y=0, color=0xFFFFFF, scale=2, font=None):
        """Draw integer-scaled text, reusing a pooled scaled Label."""
        if not Label:
            return
        if font is None:
            font = self.font
        if font is None:
            return
        idx = self._scaled_idx
        if idx < len(self._scaled_pool):
            lbl = self._scaled_pool[idx]
            if lbl.text != text:
                lbl.text = text
            if lbl.color != color:
                lbl.color = color
            if getattr(lbl, "scale", scale) != scale:
                lbl.scale = scale
            lbl.x = x
            lbl.y = y
            if hasattr(lbl, "hidden"):
                lbl.hidden = False
        else:
            lbl = Label(font, text=text, color=color, scale=scale)
            lbl.x = x
            lbl.y = y
            self._scaled_pool.append(lbl)
            # Library convention: content labels live in _content_group (below the
            # effect/layer group), matching where the base draw_text appends.
            self._content_group.append(lbl)
        self._scaled_idx += 1
