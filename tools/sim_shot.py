# Copyright (c) 2024-2026 Michael Czeiszperger
"""Dev helper: render a ScrollKit content/app headlessly and save a scaled PNG.

Lets us iterate on the LED layout from screenshots without hardware or a window.
Usage (from repo root):
    PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy \
        python3 tools/sim_shot.py
Edit ``build_app()`` to render whatever content you're working on.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def save_matrix_png(display, path, scale=10):
    """Save the simulator's 64x32 LED surface to a scaled PNG."""
    import pygame
    surf = display.matrix.get_surface() if hasattr(display.matrix, "get_surface") else None
    if surf is None:
        print("no matrix surface to save")
        return None
    big = pygame.transform.scale(surf, (surf.get_width() * scale, surf.get_height() * scale))
    pygame.image.save(big, path)
    print("saved", path, big.get_size())
    return path


async def render_and_shot(app, frames, path, scale=10):
    """Run app.setup() + N frames headless, then save the final LED frame."""
    from scrollkit.dev.harness import run_headless_async
    res = await run_headless_async(app, frames=frames, hardware=False)
    save_matrix_png(app.display, path, scale=scale)
    return res
