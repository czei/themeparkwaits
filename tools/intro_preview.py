# Copyright (c) 2024-2026 Michael Czeiszperger
"""Spot-check ride intro ANIMATIONS without booting the whole app.

Renders each animated ride's intro (the icon HOLD animation) to a looping GIF and writes an
``index.html`` gallery, so you can eyeball every intro at once instead of waiting on a full
boot + live API. It drives the REAL pipeline (``RideScreenContent`` intro -> the same
animators that run on the device), just headless and offline: no hardware, no network.

    # from the app repo, with the library checkout adjacent:
    PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy \
        python3 tools/intro_preview.py [filter ...]

No filter previews EVERY image that has a registered animation (``_SPECS``). A filter is a
case-insensitive filename substring, so ``tron pirates loco`` previews just those three.
Output lands in ``media-raw/intro-preview/`` (one GIF per ride + ``index.html``); open the
HTML to see them all looping, each labelled with its animation technique.

Caveat: the simulator renders finished frames, so this faithfully shows the MOTION,
technique and direction, but NOT the on-device startup timing (the "scene first" ordering
fix has to be confirmed on the panel).
"""
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(_HERE)
_LIB = "/Users/czei/Documents/Projects/ScrollKit/ScrollKit Library/src"
for _p in (_APP, _LIB):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from scrollkit.display._recording import capture_frame, encode_gif        # noqa: E402
from scrollkit.display.unified import UnifiedDisplay                       # noqa: E402
from src.ui.content_builder import _severity_color                        # noqa: E402
from src.ui.ride_animations import _SPECS                                 # noqa: E402
from src.ui.ride_screen_content import RideScreenContent                  # noqa: E402

RIDES_DIR = os.path.join(_APP, "src", "images", "rides")
OUT = os.path.join(_APP, "media-raw", "intro-preview")
PITCH = 6.0
MAX_HOLD = 200          # safety cap; a hold is ~104 frames


def technique(spec):
    """A short human label for a ride's animation spec (what to look for)."""
    kind = spec[0]
    if kind == "combo":
        return "combo(" + " + ".join(part[0] for part in spec[1]) + ")"
    kw = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if "path" in kw:
        return "%s %s" % (kind, kw["path"])
    return kind


async def _new_display():
    disp = UnifiedDisplay(64, 32, PITCH)
    await disp.initialize()
    try:
        await disp.set_brightness(1.0)
    except Exception:
        pass
    return disp


async def render_intro_gif(name, image_path, out_gif):
    """Capture one full icon-HOLD cycle for ``image_path`` and encode a looping GIF."""
    disp = await _new_display()
    content = RideScreenContent(
        name, 30,
        name_color=0x0000FF,
        wait_color=_severity_color(30),
        effect="Rain",
        intro_image=image_path,           # a direct path — no UUID / API lookup needed
        name_gradient=True,
    )
    await content.start()
    frames = []
    for _ in range(MAX_HOLD):
        await disp.clear()
        await content.render(disp)
        await disp.show()
        if content._intro_phase != "hold":    # icon animation is over; stop before the fade
            break
        f = capture_frame(disp.matrix)
        if f is not None:
            frames.append(f)
    if not frames:
        return 0
    encode_gif(frames, out_gif, fps=18, target_width=256, max_colors=64, frame_step=2)
    return len(frames)


_CSS = """<style>
body{background:#0f0f12;color:#e6e6ea;font:14px/1.4 system-ui,sans-serif;margin:24px}
h1{font-weight:600;font-size:18px}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}
figure{margin:0;background:#17171b;border:1px solid #2c2c33;border-radius:10px;padding:10px}
img{width:100%;image-rendering:pixelated;background:#000;border-radius:6px;display:block}
figcaption{margin-top:8px}figcaption b{font-weight:600}figcaption span{color:#7fb3c8}
</style>
"""


def _write_gallery(cards):
    figs = "\n".join(
        '  <figure><img src="' + gif + '" alt="' + name + '">'
        '<figcaption><b>' + name + '</b><br><span>' + tech + '</span></figcaption></figure>'
        for (name, tech, gif) in cards)
    title = "Ride intro preview &mdash; %d animation%s" % (
        len(cards), "" if len(cards) == 1 else "s")
    html = ("<!doctype html><meta charset=utf-8><title>Ride intro preview</title>\n"
            + _CSS + "<h1>" + title + "</h1>\n<main>\n" + figs + "\n</main>\n")
    idx = os.path.join(OUT, "index.html")
    with open(idx, "w") as fh:
        fh.write(html)
    return idx


def main():
    filters = [a.lower() for a in sys.argv[1:] if not a.startswith("-")]
    os.makedirs(OUT, exist_ok=True)
    targets = []
    for fname in sorted(_SPECS):
        if filters and not any(f in fname.lower() for f in filters):
            continue
        path = os.path.join(RIDES_DIR, fname)
        if os.path.exists(path):
            targets.append((fname, path))
    if not targets:
        print("no matching animated rides (filters: %s)" % (filters or "none"))
        return

    async def run():
        cards = []
        for fname, path in targets:
            slug = fname.rsplit(".", 1)[0]
            gif = os.path.join(OUT, slug + ".gif")
            try:
                n = await render_intro_gif(slug, path, gif)
            except Exception as exc:               # one bad ride never sinks the batch
                print("  %-26s ERROR %s" % (fname, exc))
                continue
            tech = technique(_SPECS[fname])
            print("  %-26s %-24s frames=%d" % (fname, tech, n))
            if n:
                cards.append((slug, tech, os.path.basename(gif)))
        if cards:
            print("\ngallery: %s  (%d rides)" % (_write_gallery(cards), len(cards)))

    asyncio.run(run())


if __name__ == "__main__":
    main()
