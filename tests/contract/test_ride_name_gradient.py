# Copyright (c) 2024-2026 Michael Czeiszperger
"""Ride-name vertical gradient (re-enabled after the library baseline-align fix).

The gradient was reverted because the old top-aligning rasteriser clipped cap tops
on mixed-case names with descenders. ``pixels_from_font_text`` now baseline-aligns
glyphs (library 4acc2ba), so the name renders as a two-tone vertical gradient via a
moving ``_GradientTextLayer`` (built once, scrolled by moving its TileGrid). These
pin: (1) no cap-clipping — the raster spans cap-top..descender; (2) the layer is
built ONCE, not per frame (zero per-frame pixel writes); (3) the scroll still
completes; (4) ``name_gradient=False`` keeps the flat ``draw_text`` fallback.
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


async def _display():
    from scrollkit.display.simulator import SimulatorDisplay
    disp = SimulatorDisplay(64, 32)
    await disp.initialize()
    return disp


async def _render_once(content, disp):
    await disp.clear()
    await content.render(disp)
    await disp.show()


async def test_gradient_name_no_cap_clipping():
    """A mixed-case name with descenders rasterises from the cap top (row 0) down
    through the descender — the clipping that forced the revert is gone."""
    from src.ui.ride_screen_content import RideScreenContent
    disp = await _display()
    c = RideScreenContent("Space Mountain", 45, name_gradient=True, effect="None")
    await c.start()
    await _render_once(c, disp)                 # builds the gradient layer
    grad = c._name_grad
    assert grad is not None, "gradient layer was not built (fell back to flat)"
    bmp = grad._bitmap
    lit_rows = [y for x in range(bmp.width) for y in range(bmp.height) if bmp[x, y]]
    assert min(lit_rows) == 0, "cap top is clipped (raster does not start at row 0)"
    # 'p'/'n' descenders make the run ~9 rows tall; all-caps would be ~7.
    assert max(lit_rows) >= 8, "descenders missing (run too short — top-aligned?)"
    await c.stop()


async def test_gradient_layer_built_once_then_only_moved():
    """The layer is built once and SCROLLED by moving its TileGrid — no per-frame
    rebuild (zero per-frame pixel writes, the feasibility invariant)."""
    from src.ui.ride_screen_content import RideScreenContent
    disp = await _display()
    c = RideScreenContent("Big Thunder Mountain", 30, name_gradient=True, effect="None")
    await c.start()
    await _render_once(c, disp)
    layer = c._name_grad
    bitmap = layer._bitmap
    xs = []
    for _ in range(20):
        await _render_once(c, disp)
        assert c._name_grad is layer, "gradient layer was rebuilt mid-scroll"
        assert c._name_grad._bitmap is bitmap, "bitmap was re-rasterised mid-scroll"
        xs.append(layer.x)
    assert xs[-1] < xs[0], "the name did not scroll (TileGrid x never moved)"
    await c.stop()


async def test_gradient_name_scroll_completes():
    """Completion still fires once the (gradient) name scrolls fully off."""
    from src.ui.ride_screen_content import RideScreenContent
    disp = await _display()
    c = RideScreenContent("Jungle Cruise", 20, name_gradient=True, duration=0.0,
                          effect="None")
    await c.start()
    done = False
    for _ in range(500):
        await _render_once(c, disp)
        if c.is_complete:
            done = True
            break
    assert done, "gradient name never completed its scroll"
    await c.stop()


async def test_flat_fallback_when_gradient_disabled():
    """``name_gradient=False`` keeps the flat single-colour path (no gradient layer)."""
    from src.ui.ride_screen_content import RideScreenContent
    disp = await _display()
    c = RideScreenContent("Space Mountain", 45, name_gradient=False, effect="None")
    await c.start()
    await _render_once(c, disp)
    assert c._name_grad is None, "a gradient layer was built with name_gradient=False"
    await c.stop()
