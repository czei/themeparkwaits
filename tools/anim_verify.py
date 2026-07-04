# Copyright (c) 2024-2026 Michael Czeiszperger
"""Headless verifier for per-ride intro animations (see src/ui/ride_animations.py).

Renders ONE image's intro through the real RideScreenContent + SimulatorDisplay (SDL
dummy), then writes a contact sheet of evenly-spread HOLD frames and prints metrics:

    PYTHONPATH="../ScrollKit Library/src:." python3 tools/anim_verify.py <name.bmp> <outdir>

Prints (machine-readable):
    animator=<ClassName|None>       resolved from the registry (None = static image)
    phases hold=<n> fade=<n> normal=<n>
    motion=<mean px changed between consecutive hold frames>  (0.0 => nothing moves)
    sheet=<path to contact-sheet PNG>  (10 hold frames left->right in time order)
A reviewer then LOOKS at the sheet: does the motion read? is the art intact?
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame                                                    # noqa: E402
from PIL import Image                                            # noqa: E402
from scrollkit.display.simulator import SimulatorDisplay        # noqa: E402
from src.ui.ride_screen_content import RideScreenContent        # noqa: E402
from src.ui.ride_animations import for_image                    # noqa: E402

IMAGES_DIR = "src/images/rides"
NFRAMES = 170
COLS = 10
CELL_W = 180


async def grab(display):
    await display.show()
    surf = display.matrix.get_surface()
    w, h = surf.get_size()
    return Image.frombytes("RGB", (w, h), pygame.image.tobytes(surf, "RGB"))


async def main():
    name = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/tpw_anim_verify"
    os.makedirs(outdir, exist_ok=True)
    path = name if os.path.exists(name) else os.path.join(IMAGES_DIR, name)
    assert os.path.exists(path), "no such image: %s" % path

    anim = for_image(path)
    print("animator=%s" % (type(anim).__name__ if anim else "None"))

    ride = RideScreenContent("Test Ride", 45, intro_image=path, effect="None")
    display = SimulatorDisplay(64, 32, pitch=3.0)
    await display.initialize()
    try:
        await display.set_brightness(1.0)
    except Exception:
        pass

    await ride.start()
    frames, phases = [], []
    for _ in range(NFRAMES):
        await display.clear()
        await ride.render(display)
        frames.append(await grab(display))
        phases.append(ride._intro_phase)
        if phases[-1] is None and len(phases) > 8 and phases[-8] is None:
            break                                 # well into NORMAL; enough captured
    await ride.stop()

    hold = [i for i, p in enumerate(phases) if p == "hold"]
    fade = [i for i, p in enumerate(phases) if p == "fade"]
    normal = [i for i, p in enumerate(phases) if p is None]
    print("phases hold=%d fade=%d normal=%d" % (len(hold), len(fade), len(normal)))

    # Motion metric: mean # of pixels differing between consecutive hold frames.
    diffs = []
    for a, b in zip(hold, hold[1:]):
        pa, pb = frames[a].tobytes(), frames[b].tobytes()
        diffs.append(sum(1 for i in range(0, len(pa), 3) if pa[i:i+3] != pb[i:i+3]))
    print("motion=%.1f" % (sum(diffs) / len(diffs) if diffs else 0.0))

    pick = ([hold[round(i * (len(hold) - 1) / (COLS - 1))] for i in range(COLS)]
            if len(hold) >= COLS else hold)
    w, h = frames[0].size
    cw, ch, pad = CELL_W, int(CELL_W * h / w), 4
    sheet = Image.new("RGB", (len(pick) * cw + (len(pick) + 1) * pad, ch + 2 * pad), (40, 40, 40))
    for c, i in enumerate(pick):
        sheet.paste(frames[i].resize((cw, ch), Image.LANCZOS), (pad + c * (cw + pad), pad))
    out = os.path.join(outdir, os.path.basename(path).replace(".bmp", "_hold.png"))
    sheet.save(out)
    print("sheet=%s" % out)


if __name__ == "__main__":
    asyncio.run(main())
