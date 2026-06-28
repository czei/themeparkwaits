# Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""Sim e2e for the per-ride intro image: build a REAL content queue with Space
Mountain (whose UUID is in src/images/rides/manifest.json), render the actual
RideScreenContent through the simulator, and save the HOLD->FADE+scroll->number GIF.

Also asserts the wiring (Space Mountain gets an intro; a ride with no manifest
entry does not) and the phase progression (image layer attached during the intro,
gone once the number reveals).

    PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy \
        python3 tools/intro_shots.py [outdir]   # default outdir: /tmp/tpw_intro
"""
import asyncio
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame                                                    # noqa: E402
from PIL import Image                                            # noqa: E402
from scrollkit.display.content import ContentQueue              # noqa: E402
from scrollkit.display.unified import UnifiedDisplay            # noqa: E402
from src.models.theme_park_list import ThemeParkList           # noqa: E402
from src.models.vacation import Vacation                        # noqa: E402
from src.settings_schema import make_settings                   # noqa: E402
from src.ui.content_builder import build_content_queue          # noqa: E402
from src.ui.ride_screen_content import RideScreenContent        # noqa: E402

MK_ID = "75ea578a-adc8-4116-a54d-dccb60765ef9"
SPACE_MTN_ID = "b2260923-9315-40fd-9c6b-44dd811dbe64"   # in the manifest -> has an intro
NO_IMAGE_ID = "00000000-0000-0000-0000-000000000000"   # not in the manifest -> no intro

PARKS = ('{"destinations":[{"name":"Walt Disney World","parks":['
         '{"id":"%s","name":"Magic Kingdom","latitude":"28.4","longitude":"-81.5"}]}]}' % MK_ID)
RIDES = ('{"liveData":['
         '{"id":"%s","name":"Space Mountain","entityType":"ATTRACTION","status":"OPERATING",'
         '"queue":{"STANDBY":{"waitTime":45}}},'
         '{"id":"%s","name":"Astro Orbiter","entityType":"ATTRACTION","status":"OPERATING",'
         '"queue":{"STANDBY":{"waitTime":10}}}]}'
         % (SPACE_MTN_ID, NO_IMAGE_ID))


def build_queue():
    pl = ThemeParkList(json.loads(PARKS))
    park = pl.get_park_by_id(MK_ID)
    park.update(json.loads(RIDES))
    pl.selected_parks = [park]
    sm = make_settings(os.path.join(tempfile.mkdtemp(), "settings.json"))
    sm.set("selected_park_ids", [MK_ID])
    sm.set("sort_mode", "alphabetical")
    q = ContentQueue()
    build_content_queue(q, pl, sm, Vacation(), include_splash=False, rng=random.Random(7))
    return list(q)


def find_ride(items, name):
    for c in items:
        if isinstance(c, RideScreenContent) and getattr(c, "_tpw_ride", None) == name:
            return c
    return None


async def cap(display, frames):
    await display.show()
    surf = display.matrix.get_surface()
    w, h = surf.get_size()
    img = Image.frombytes("RGB", (w, h), pygame.image.tobytes(surf, "RGB"))
    frames.append(img.resize((w // 2, h // 2), Image.LANCZOS))


async def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/tpw_intro"
    os.makedirs(outdir, exist_ok=True)

    items = build_queue()
    sm_ride = find_ride(items, "Space Mountain")
    ao_ride = find_ride(items, "Astro Orbiter")

    # --- wiring assertions ---
    assert sm_ride is not None, "Space Mountain RideScreenContent not built"
    assert sm_ride._tpw_intro_image and sm_ride._tpw_intro_image.endswith("space_mountain.bmp"), \
        "Space Mountain should have an intro image, got %r" % (sm_ride._tpw_intro_image,)
    assert ao_ride is not None and ao_ride._tpw_intro_image is None, \
        "Astro Orbiter (no manifest entry) must have no intro, got %r" % (ao_ride._tpw_intro_image,)
    print("wiring OK: Space Mountain intro=%s | Astro Orbiter intro=%s"
          % (os.path.basename(sm_ride._tpw_intro_image), ao_ride._tpw_intro_image))

    # --- render the real RideScreenContent through the simulator ---
    display = UnifiedDisplay(64, 32, 4)
    await display.initialize()
    try:
        await display.set_brightness(1.0)
    except Exception:
        pass

    await sm_ride.start()
    frames = []
    phases = []          # (frame, phase, layer_attached, reveal_built)
    for i in range(150):
        await display.clear()
        await sm_ride.render(display)
        await cap(display, frames)
        phases.append((i, sm_ride._intro_phase, sm_ride._intro_tile is not None,
                       getattr(sm_ride, "_reveal", None) is not None))
        if sm_ride._intro_phase is None and getattr(sm_ride, "_reveal", None) is not None \
                and sm_ride._scrolled_off:
            break
    await sm_ride.stop()

    gif = os.path.join(outdir, "intro_flow.gif")
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=50, loop=0, optimize=True)

    # --- phase-progression assertions ---
    holds = [p for p in phases if p[1] == "hold"]
    fades = [p for p in phases if p[1] == "fade"]
    normals = [p for p in phases if p[1] is None]
    assert holds and all(p[2] for p in holds), "HOLD must show the image layer"
    assert fades and all(p[2] for p in fades), "FADE must keep the image layer while name scrolls"
    assert normals, "must reach NORMAL"
    assert not normals[-1][2], "image layer must be detached by NORMAL"
    assert any(p[3] for p in normals), "wait-number reveal must be built in NORMAL"
    # the reveal must NOT exist during the intro (gated)
    assert not any(p[3] for p in holds + fades), "number must be gated until after the fade"

    print("phases: hold=%d fade=%d normal=%d  (image layer detaches at NORMAL, number gated)"
          % (len(holds), len(fades), len(normals)))
    print("saved", gif, len(frames), "frames")


if __name__ == "__main__":
    asyncio.run(main())
