"""Reveal splash — ported from the original reveal_animation.py.

Every LED starts on; the non-text LEDs randomly wink off until "THEME PARK WAITS"
remains, then it holds briefly. Pixel-exact via a displayio Bitmap (raw pixels),
so the Label y-origin issue (P1) does not apply.

Faithful port of the original; the only adaptation for the ScrollKitApp model is
that it takes the ``display`` and calls ``await display.show()`` each step, so it
animates while running inside ``setup()`` (before the main display loop starts).
The pixel map + shuffle are verbatim from reveal_animation.py.

Copyright 2024 3DUPFitters LLC
"""
import asyncio
import random

from scrollkit.utils.error_handler import ErrorHandler
# Use the SAME displayio the display uses (real on CircuitPython, the simulator's
# on desktop). A bare ``import displayio`` can grab a stray Blinka 'displayio'
# PyPI package on desktop, producing TileGrids the simulator can't render.
from scrollkit.display.unified import displayio

logger = ErrorHandler("error_log")


def get_theme_park_waits_pixels():
    """(x, y) coordinates of the THEME PARK WAITS glyph pixels (verbatim)."""
    pixels = []
    # THEME PARK — line 1
    for x in range(4, 9): pixels.append((x, 3))
    for y in range(4, 11): pixels.append((6, y))
    for y in range(3, 11): pixels.append((10, y))
    for y in range(3, 11): pixels.append((14, y))
    for x in range(11, 14): pixels.append((x, 6))
    for y in range(3, 11): pixels.append((16, y))
    for x in range(16, 20): pixels.append((x, 3))
    for x in range(16, 19): pixels.append((x, 6))
    for x in range(16, 20): pixels.append((x, 10))
    for y in range(3, 11): pixels.append((22, y))
    for y in range(3, 11): pixels.append((27, y))
    pixels += [(23, 4), (24, 5), (25, 5), (26, 4)]
    for y in range(3, 11): pixels.append((29, y))
    for x in range(29, 33): pixels.append((x, 3))
    for x in range(29, 32): pixels.append((x, 6))
    for x in range(29, 33): pixels.append((x, 10))
    for y in range(3, 11): pixels.append((36, y))
    for x in range(36, 40): pixels.append((x, 3))
    for x in range(36, 40): pixels.append((x, 6))
    pixels += [(39, 4), (39, 5)]
    for y in range(4, 11): pixels.append((42, y))
    for y in range(4, 11): pixels.append((46, y))
    for x in range(43, 46): pixels.append((x, 3))
    for x in range(42, 47): pixels.append((x, 6))
    for y in range(3, 11): pixels.append((48, y))
    for x in range(48, 52): pixels.append((x, 3))
    for x in range(48, 52): pixels.append((x, 6))
    pixels += [(51, 4), (51, 5), (50, 7), (51, 8), (52, 9), (53, 10)]
    for y in range(3, 11): pixels.append((54, y))
    pixels += [(57, 3), (56, 4), (55, 5), (55, 6), (56, 7), (57, 8), (58, 9), (59, 10)]
    # WAITS — line 2
    for y in range(15, 31): pixels += [(5, y), (6, y), (13, y), (14, y)]
    for x in range(7, 9): pixels += [(x, 28), (x, 27)]
    for x in range(11, 13): pixels += [(x, 28), (x, 27)]
    for y in range(23, 27): pixels += [(9, y), (10, y)]
    for y in range(17, 31): pixels += [(16, y), (17, y), (24, y), (25, y)]
    for x in range(18, 24): pixels += [(x, 15), (x, 16)]
    for x in range(16, 26): pixels += [(x, 22), (x, 23)]
    for x in range(27, 37): pixels += [(x, 15), (x, 16), (x, 29), (x, 30)]
    for y in range(15, 31): pixels += [(31, y), (32, y)]
    for x in range(38, 48): pixels += [(x, 15), (x, 16)]
    for y in range(15, 31): pixels += [(42, y), (43, y)]
    for x in range(49, 59): pixels += [(x, 15), (x, 16)]
    for y in range(17, 22): pixels += [(49, y), (50, y)]
    for x in range(49, 59): pixels += [(x, 22), (x, 23)]
    for y in range(24, 29): pixels += [(57, y), (58, y)]
    for x in range(49, 59): pixels += [(x, 29), (x, 30)]
    return pixels


def simple_shuffle(lst):
    """Simple in-place shuffle for CircuitPython compatibility (verbatim)."""
    for i in range(len(lst)):
        j = random.randint(0, len(lst) - 1)
        lst[i], lst[j] = lst[j], lst[i]


async def show_reveal_splash(display, color=0xFFFF00, off_per_frame=14):
    """Play the reveal on ``display`` (all LEDs on -> wink off non-text -> hold)."""
    try:
        w, h = display.width, display.height
        bitmap = displayio.Bitmap(w, h, 2)
        palette = displayio.Palette(2)
        palette[0] = 0x000000
        palette[1] = color
        tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
        # Append the TileGrid directly to main_group (matches how the library's
        # draw_text adds Labels). Removed on completion below.
        display.main_group.append(tile_grid)

        target_set = set(get_theme_park_waits_pixels())

        # Every LED on via a single C fill (perf rule 2: never a per-pixel Python
        # loop; bitmap.fill is ~1600x faster than bitmap[x,y]=). Fall back to a
        # loop only if the platform's Bitmap lacks .fill.
        try:
            bitmap.fill(1)
        except (AttributeError, TypeError):
            for x in range(w):
                for y in range(h):
                    bitmap[x, y] = 1

        # The non-text LEDs to wink off, in random order (list build, no pixel writes).
        incorrect_on = [(x, y) for x in range(w) for y in range(h)
                        if (x, y) not in target_set]
        simple_shuffle(incorrect_on)

        await display.show()  # show the all-on starting frame

        while incorrect_on:
            for _ in range(min(off_per_frame, len(incorrect_on))):
                px = incorrect_on.pop()
                bitmap[px[0], px[1]] = 0
            await display.show()
            await asyncio.sleep(0.02)

        await display.show()
        await asyncio.sleep(2)
        display.main_group.remove(tile_grid)
    except Exception as e:
        logger.error(e, "Error in reveal splash animation")
