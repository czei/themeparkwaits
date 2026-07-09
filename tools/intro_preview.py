# Copyright (c) 2024-2026 Michael Czeiszperger
"""Play ride intro ANIMATIONS in the desktop simulator, one after another.

A fast spot-check loop for the ride icon intros without booting the whole app (no live
API, no boot sequence). It drives the REAL pipeline (``RideScreenContent`` intro -> the
same animators that run on the device) and shows each ride's icon animation in the
simulator window; when the animation finishes it advances to the next ride.

    # from the app repo, with the library checkout adjacent (NOTE: no SDL dummy driver,
    # so a real window opens):
    PYTHONPATH="../ScrollKit Library/src:." python3 tools/intro_preview.py [filter ...]

Keys:  Right / Space = next    Left = previous    R = replay    Esc / Q = quit

No filter plays EVERY image that has a registered animation (``_SPECS``). A filter is a
case-insensitive filename substring, so ``tron pirates loco`` plays just those three.

    # optional: write a looping GIF per ride + index.html instead of a window (headless)
    PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy \
        python3 tools/intro_preview.py --gif [filter ...]

Caveat: the simulator renders finished frames, so it faithfully shows the motion,
technique and direction, but NOT the on-device startup timing (the "scene first" ordering
fix still has to be confirmed on the panel).
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
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from scrollkit.display.unified import UnifiedDisplay                       # noqa: E402
from src.ui.content_builder import _severity_color                        # noqa: E402
from src.ui.ride_animations import _SPECS                                 # noqa: E402
from src.ui.ride_screen_content import RideScreenContent                  # noqa: E402

RIDES_DIR = os.path.join(_APP, "src", "images", "rides")
OUT = os.path.join(_APP, "media-raw", "intro-preview")
PITCH = 10.0            # LED px per dot: a comfortably sized preview window
FRAME_DT = 1.0 / 30     # playback frame rate
HOLD_CAP = 220          # safety cap on a single ride's hold, in frames


def technique(spec):
    """A short human label for a ride's animation spec (what to watch for)."""
    kind = spec[0]
    if kind == "combo":
        return "combo(" + " + ".join(part[0] for part in spec[1]) + ")"
    kw = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    return "%s %s" % (kind, kw["path"]) if "path" in kw else kind


def _collect(filters):
    targets = []
    for fname in sorted(_SPECS):
        if filters and not any(f in fname.lower() for f in filters):
            continue
        path = os.path.join(RIDES_DIR, fname)
        if os.path.exists(path):
            targets.append((fname, path))
    return targets


def _make_content(slug, path):
    return RideScreenContent(
        slug, 30,
        name_color=0x0000FF,
        wait_color=_severity_color(30),
        effect="Rain",
        intro_image=path,                 # a direct path — no UUID / API lookup needed
        name_gradient=True,
    )


async def _new_display():
    disp = UnifiedDisplay(64, 32, PITCH)
    await disp.initialize()
    try:
        await disp.set_brightness(1.0)
    except Exception:
        pass
    return disp


# --------------------------------------------------------------------------- window
async def _play_hold(disp, content):
    """Play one ride's icon-HOLD animation; return 'next' | 'prev' | 'auto' | 'quit'."""
    import pygame
    await content.start()
    guard = 0
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "quit"
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    return "quit"
                if e.key in (pygame.K_RIGHT, pygame.K_SPACE):
                    return "next"
                if e.key == pygame.K_LEFT:
                    return "prev"
                if e.key == pygame.K_r:
                    try:
                        content._detach_intro()
                    except Exception:
                        pass
                    await content.start()
                    guard = 0
        await disp.clear()
        await content.render(disp)
        if await disp.show() is False:        # window closed / Esc caught inside show()
            return "quit"
        guard += 1
        if content._intro_phase != "hold" or guard > HOLD_CAP:
            return "auto"                     # icon animation done -> advance
        await asyncio.sleep(FRAME_DT)


async def run_window(targets):
    import pygame
    disp = await _new_display()
    try:
        await disp.create_window("Ride intro preview")
    except Exception as exc:
        print("could not open a window (%s).\nRun without SDL_VIDEODRIVER=dummy, or use "
              "--gif for headless output." % exc)
        return
    print("Playing %d intros.  Right/Space=next  Left=prev  R=replay  Esc/Q=quit\n"
          % len(targets))
    idx = 0
    while 0 <= idx < len(targets):
        fname, path = targets[idx]
        slug = fname.rsplit(".", 1)[0]
        tech = technique(_SPECS[fname])
        pygame.display.set_caption("[%d/%d]  %s  -  %s" % (idx + 1, len(targets), slug, tech))
        print("  [%2d/%2d] %-22s %s" % (idx + 1, len(targets), slug, tech))
        content = _make_content(slug, path)
        action = await _play_hold(disp, content)
        try:
            content._detach_intro()           # drop this ride's layers before the next
        except Exception:
            pass
        if action == "quit":
            break
        # Wrap around so the player loops continuously (Esc/Q to quit). With a single
        # target this simply replays it, which is what you want for a close look.
        step = -1 if action == "prev" else 1
        idx = (idx + step) % len(targets)
    print("\ndone.")


# ----------------------------------------------------------------------------- gifs
async def run_gifs(targets):
    from scrollkit.display._recording import capture_frame, encode_gif
    os.makedirs(OUT, exist_ok=True)
    cards = []
    for fname, path in targets:
        slug = fname.rsplit(".", 1)[0]
        disp = await _new_display()
        content = _make_content(slug, path)
        await content.start()
        frames = []
        for _ in range(HOLD_CAP):
            await disp.clear()
            await content.render(disp)
            await disp.show()
            if content._intro_phase != "hold":
                break
            f = capture_frame(disp.matrix)
            if f is not None:
                frames.append(f)
        if not frames:
            continue
        gif = os.path.join(OUT, slug + ".gif")
        encode_gif(frames, gif, fps=18, target_width=256, max_colors=64, frame_step=2)
        tech = technique(_SPECS[fname])
        print("  %-26s %-24s frames=%d" % (fname, tech, len(frames)))
        cards.append((slug, tech, os.path.basename(gif)))
    if cards:
        print("\ngallery: %s  (%d rides)" % (_write_gallery(cards), len(cards)))


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
    args = sys.argv[1:]
    gif_mode = ("--gif" in args) or ("--gifs" in args)
    filters = [a.lower() for a in args if not a.startswith("-")]
    targets = _collect(filters)
    if not targets:
        print("no matching animated rides (filters: %s)" % (filters or "none"))
        return
    asyncio.run(run_gifs(targets) if gif_mode else run_window(targets))


if __name__ == "__main__":
    main()
