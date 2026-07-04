# Copyright (c) 2024-2026 Michael Czeiszperger
"""Engine tests for the per-ride intro animations (src/ui/ride_animations.py).

Every REGISTRY entry is exercised against its real shipped BMP through the same
load path ``_load_intro`` uses (OnDiskBitmap -> palette -> optional writable copy ->
attach/step/detach on a real headless display). This catches bad kwargs (boxes out of
range, palette matches that hit nothing, oversized region_shift captures) the moment a
spec is added — sim-green here means the device path at least constructs and steps.
"""
import os

import pytest

from scrollkit.display.unified import UnifiedDisplay, displayio
from src.ui import ride_animations as ra

IMAGES_DIR = "src/images/rides"


@pytest.fixture
async def display():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    d = UnifiedDisplay(64, 32, 4)
    await d.initialize()
    return d


def _load(path):
    """Mirror _load_intro's bitmap/palette/base-colors extraction."""
    odb = displayio.OnDiskBitmap(path)
    pal = odb.pixel_shader
    pal.make_transparent(0)
    get888 = getattr(pal, "get_rgb888", None)
    if get888 is not None:
        base = [(int(c[0]) << 16) | (int(c[1]) << 8) | int(c[2])
                for c in (get888(i) for i in range(len(pal)))]
    else:
        base = [pal[i] for i in range(len(pal))]
    bmp = getattr(odb, "bitmap", odb)
    return bmp, pal, base


@pytest.mark.parametrize("fname", sorted(ra._SPECS.keys()))
async def test_registry_entry_attaches_and_steps(display, fname):
    path = os.path.join(IMAGES_DIR, fname)
    assert os.path.exists(path), "registry names a missing image: %s" % fname

    anim = ra.for_image(path)
    assert anim is not None, "for_image returned None for a registered image"

    bmp, pal, base = _load(path)
    if anim.wants_writable_bitmap:
        bmp = ra.copy_to_writable(bmp, 64, 32, len(pal))
    tile = displayio.TileGrid(bmp, pixel_shader=pal)
    display.add_layer(tile)
    try:
        anim.attach(display, tile, bmp, pal, base)
        for frame in range(0, anim.HOLD_FRAMES, max(1, anim.HOLD_FRAMES // 16)):
            anim.step(frame)
    finally:
        anim.detach()
        display.remove_layer(tile)

    # detach() must have released any overlay layer it added
    assert getattr(anim, "_overlay_tile", None) is None


def test_unknown_image_returns_none():
    assert ra.for_image("no_such_image.bmp") is None
    assert ra.for_image(None) is None


def test_instances_are_fresh():
    a = ra.for_image("spaceship_earth.bmp")
    b = ra.for_image("spaceship_earth.bmp")
    assert a is not b


def test_bad_spec_falls_back_to_none(monkeypatch):
    monkeypatch.setitem(ra._SPECS, "broken.bmp", ("twinkle", {"nope": 1}))
    assert ra.for_image("broken.bmp") is None
