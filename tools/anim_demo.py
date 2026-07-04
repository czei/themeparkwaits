# Copyright (c) 2024-2026 Michael Czeiszperger
"""Live simulator window looping the two ANIMATED ride intros — a demo you run yourself.

Built like the ScrollKit library demos (see demos/easy/clock.py): a ScrollKitApp subclass
that returns a SimulatorDisplay, opens the window in setup(), and runs via app.run().
Fully self-contained — the two rides are built from an inline fixture, so no network AND
no import that forces SDL headless (that was the earlier bug: importing tools/intro_shots,
a screenshot tool, set SDL_VIDEODRIVER=dummy and no window could open).

    PYTHONPATH="../ScrollKit Library/src:." python3 tools/anim_demo.py          # the classic two
    PYTHONPATH="../ScrollKit Library/src:." python3 tools/anim_demo.py --all    # every animated image
    PYTHONPATH="../ScrollKit Library/src:." python3 tools/anim_demo.py dragon rocket  # by name

Default loops Spaceship Earth (twinkle) -> Turtle (swim); --all cycles EVERY image with a
registered animation (discovered from ride_animations at runtime); or name image stems to
pick specific ones. Close the window or press Esc to quit.
"""
import asyncio
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("SDL_VIDEODRIVER", None)          # ensure a visible (non-dummy) window

from scrollkit.app.base import ScrollKitApp                     # noqa: E402
from scrollkit.display.content import ContentQueue             # noqa: E402
from src.models.theme_park_list import ThemeParkList           # noqa: E402
from src.models.vacation import Vacation                        # noqa: E402
from src.settings_schema import make_settings                   # noqa: E402
from src.ui.content_builder import build_content_queue          # noqa: E402
from src.ui.ride_screen_content import RideScreenContent        # noqa: E402

MK_ID = "75ea578a-adc8-4116-a54d-dccb60765ef9"
# Default (no args): the CURRENT REVIEW SET — the images most recently changed and
# awaiting the owner's verdict. Use --all for everything, or name stems to pick.
REVIEW_STEMS = ["poison_apple", "airplane", "coaster_car", "laser_blaster"]
RIDES = [("Spaceship Earth", "480fde8f-fe58-4bfb-b3ab-052a39d4db7c"),
         ("Turtle Talk",     "57acb522-a6fc-4aa4-a80e-21f21f317250")]


def pick_rides(argv):
    """The (display name, uuid) list to cycle, from the CLI args.

    --all -> one ride per REGISTERED animated image (a manifest uuid that maps to it);
    bare stems ("dragon", "rocket") -> just those images; no args -> the classic two.
    """
    want = [a for a in argv[1:] if not a.startswith("-")]
    use_all = "--all" in argv
    if not use_all and not want:
        want = list(REVIEW_STEMS)          # bare run = the current review set
    from src.ui.ride_animations import _SPECS
    manifest = json.load(open("src/images/rides/manifest.json"))["rides"]
    by_image = {}
    for uuid, fname in sorted(manifest.items()):
        by_image.setdefault(fname, uuid)          # first uuid per image is enough
    rides = []
    for fname in sorted(_SPECS):
        stem = fname[:-4]
        if not use_all and stem not in want:
            continue
        uuid = by_image.get(fname)
        if uuid:
            rides.append((stem.replace("_", " ").title(), uuid))
    assert rides, "no animated image matches %r" % (want,)
    return rides

_PARKS = ('{"destinations":[{"name":"Walt Disney World","parks":['
          '{"id":"%s","name":"Magic Kingdom","latitude":"28.4","longitude":"-81.5"}]}]}' % MK_ID)


def _live(rides):
    items = ['{"id":"%s","name":"%s","entityType":"ATTRACTION","status":"OPERATING",'
             '"queue":{"STANDBY":{"waitTime":45}}}' % (rid, name) for name, rid in rides]
    return '{"liveData":[%s]}' % ",".join(items)


def build_ride_contents(rides):
    """The RideScreenContent list for ``rides`` from an offline fixture (no network)."""
    pl = ThemeParkList(json.loads(_PARKS))
    park = pl.get_park_by_id(MK_ID)
    park.update(json.loads(_live(rides)))
    pl.selected_parks = [park]
    sm = make_settings(os.path.join(tempfile.mkdtemp(), "settings.json"))
    sm.set("selected_park_ids", [MK_ID])
    sm.set("sort_mode", "alphabetical")
    q = ContentQueue()
    build_content_queue(q, pl, sm, Vacation(), include_splash=False, rng=random.Random(7))
    wanted = {name for name, _ in rides}
    return [c for c in q if isinstance(c, RideScreenContent)
            and getattr(c, "_tpw_ride", None) in wanted]


class AnimDemoApp(ScrollKitApp):
    """Cycles the two animated ride screens in a real simulator window."""

    def __init__(self):
        super().__init__(enable_web=False, update_interval=100000)

    async def create_display(self):
        from scrollkit.display.simulator import SimulatorDisplay
        return SimulatorDisplay(width=64, height=32, scale=12)

    async def setup(self):
        if hasattr(self.display, "create_window"):
            await self.display.create_window("ThemeParkWaits — animated intros")
        rides = pick_rides(sys.argv)
        print("cycling %d animated ride screen(s): %s"
              % (len(rides), ", ".join(n for n, _ in rides)))
        for content in build_ride_contents(rides):
            self.content_queue.add(content)

    async def update_data(self):
        return  # curated static content; nothing to refresh


if __name__ == "__main__":
    asyncio.run(AnimDemoApp().run())
