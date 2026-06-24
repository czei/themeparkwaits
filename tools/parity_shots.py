"""Render the unverified visual-parity cases to PNGs + print their queues.

Closed ride / closed-park message, vacation countdown (3 variants), and multi-park
grouping are built through the REAL models + real ``build_content_queue`` (not
hand-faked content), then rendered headlessly so we can eyeball layout/colour and
confirm wording/ordering (tasks.md T034/T040).

    PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy \
        python3 tools/parity_shots.py [outdir]   # default outdir: /tmp/tpw_parity

Each scrolling line is pinned to a deterministic frame: text that fits the 64px
panel is centred; longer text is shown from its start (the most identifying part).
The full string is printed for each item, since the panel only shows ~10 chars.
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrollkit.display.content import ContentQueue, ScrollingText           # noqa: E402
from src.models.theme_park_list import ThemeParkList                        # noqa: E402
from src.models.vacation import Vacation                                    # noqa: E402
from src.settings_schema import make_settings                              # noqa: E402
from src.ui.content_builder import build_content_queue                      # noqa: E402
from src.ui.ride_screen_content import RideScreenContent, ClosedRideContent # noqa: E402
from src.ui.tpw_display import ThemeParkDisplay                             # noqa: E402
from tools.sim_shot import save_matrix_png                                  # noqa: E402

# --- canned data (WDW: Magic Kingdom id 6, Epcot id 5) ----------------------
PARKS_JSON = ('[{"id":1,"name":"Walt Disney World","parks":['
              '{"id":6,"name":"Magic Kingdom","latitude":"28.4","longitude":"-81.5"},'
              '{"id":5,"name":"Epcot","latitude":"28.3","longitude":"-81.5"}]}]')
MK_RIDES = ('{"lands":[{"id":1,"name":"Tomorrowland","rides":['
            '{"id":101,"name":"Space Mountain","is_open":true,"wait_time":45},'
            '{"id":102,"name":"Astro Orbiter","is_open":true,"wait_time":0},'
            '{"id":103,"name":"Buzz Lightyear","is_open":false,"wait_time":0}]}],'
            '"rides":[{"id":104,"name":"Mickey Meet & Greet","is_open":true,"wait_time":15}]}')
EPCOT_OPEN = ('{"lands":[{"id":2,"name":"World Discovery","rides":['
              '{"id":201,"name":"Test Track","is_open":true,"wait_time":60},'
              '{"id":202,"name":"Guardians of the Galaxy","is_open":true,"wait_time":75}]}]}')
EPCOT_CLOSED = ('{"lands":[{"id":2,"name":"World Discovery","rides":['
                '{"id":201,"name":"Test Track","is_open":false,"wait_time":0}]}]}')


def settings(**overrides):
    sm = make_settings(os.path.join(tempfile.mkdtemp(), "settings.json"))
    for k, v in overrides.items():
        sm.set(k, v)
    return sm


def park_list(populate):
    """populate: list of (park_id, rides_json). Returns a list with those parks selected."""
    pl = ThemeParkList(json.loads(PARKS_JSON))
    selected = []
    for pid, rides_json in populate:
        park = pl.get_park_by_id(pid)
        park.update(json.loads(rides_json))
        selected.append(park)
    pl.selected_parks = selected
    return pl


def describe(c):
    if isinstance(c, ScrollingText):
        return "ScrollingText   %r" % c.text
    if isinstance(c, RideScreenContent):
        return "RideScreen      name=%r  wait=%s" % (c.ride_name, c.wait_minutes)
    if isinstance(c, ClosedRideContent):
        return "ClosedRide      name=%r  -> 'Closed'" % c.ride_name
    return type(c).__name__


def print_queue(title, queue):
    print("\n=== %s ===" % title)
    for i, c in enumerate(queue):
        print("  [%2d] %s" % (i, describe(c)))


def _pin(item, display):
    """Pin a content item to a deterministic, legible frame (centre if it fits)."""
    if isinstance(item, ScrollingText):
        w = len(item.text) * 6
        item._text_width = w
        item._position = 2 if w > display.width else (display.width - w) // 2
    if hasattr(item, "_name_x"):  # Ride/Closed: pin the scrolling name
        w = len(item.ride_name) * 6
        item._name_w = w
        item._name_x = 2 if w > display.width else (display.width - w) // 2


async def shot(display, item, path):
    if hasattr(item, "start"):
        await item.start()
    _pin(item, display)
    await display.clear()
    await item.render(display)
    await display.show()
    save_matrix_png(display, path)


def find(queue, pred):
    for c in queue:
        if pred(c):
            return c
    return None


async def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/tpw_parity"
    os.makedirs(outdir, exist_ok=True)

    display = ThemeParkDisplay(64, 32, 4)
    await display.initialize()
    try:
        await display.set_brightness(1.0)   # full brightness so glyphs read clearly in the shot
    except Exception:
        pass

    def p(name):
        return os.path.join(outdir, name)

    # 1) Single park: closed ride + open-with-0-wait + big number -------------
    sm = settings(selected_park_ids=[6], sort_mode="alphabetical")
    q = ContentQueue()
    build_content_queue(q, park_list([(6, MK_RIDES)]), sm, Vacation())
    print_queue("Scenario 1 — single park (closed ride, zero-wait, big number)", q)
    await shot(display, find(q, lambda c: isinstance(c, ClosedRideContent)), p("1a_closed_ride.png"))
    await shot(display, find(q, lambda c: isinstance(c, RideScreenContent) and c.wait_minutes == 45),
               p("1b_open_ride_45.png"))
    await shot(display, find(q, lambda c: isinstance(c, RideScreenContent) and c.wait_minutes == 0),
               p("1c_open_ride_0.png"))

    # 2) Multi-park grouping (both parks open) --------------------------------
    sm = settings(selected_park_ids=[6, 5], group_by_park=True)
    q = ContentQueue()
    build_content_queue(q, park_list([(6, MK_RIDES), (5, EPCOT_OPEN)]), sm, Vacation())
    print_queue("Scenario 2 — multi-park grouping (group_by_park=True)", q)
    await shot(display, find(q, lambda c: isinstance(c, ScrollingText) and "Magic Kingdom wait" in c.text),
               p("2a_mk_header.png"))
    await shot(display, find(q, lambda c: isinstance(c, ScrollingText) and "Epcot wait" in c.text),
               p("2b_epcot_header.png"))
    await shot(display, find(q, lambda c: isinstance(c, RideScreenContent) and c.ride_name.startswith("Guardians")),
               p("2c_epcot_ride.png"))

    # 3) Closed-park message (group_by_park, Epcot closed) --------------------
    sm = settings(selected_park_ids=[6, 5], group_by_park=True)
    q = ContentQueue()
    build_content_queue(q, park_list([(6, MK_RIDES), (5, EPCOT_CLOSED)]), sm, Vacation())
    print_queue("Scenario 3 — closed-park message", q)
    await shot(display, find(q, lambda c: isinstance(c, ScrollingText) and "is closed" in c.text),
               p("3_park_closed.png"))

    # 4) Vacation countdown — 3 variants --------------------------------------
    import datetime as _dt
    today = _dt.date.today()
    variants = [("4a_vacation_5days", today + _dt.timedelta(days=5)),
                ("4b_vacation_tomorrow", today + _dt.timedelta(days=1)),
                ("4c_vacation_today", today)]
    print("\n=== Scenario 4 — vacation countdown ===")
    for name, d in variants:
        sm = settings(selected_park_ids=[6])
        vac = Vacation("Magic Kingdom", d.year, d.month, d.day)
        q = ContentQueue()
        build_content_queue(q, park_list([(6, MK_RIDES)]), sm, vac)
        msg = find(q, lambda c: isinstance(c, ScrollingText) and "acation" in c.text)
        print("  %-22s days_until=%s  %r" % (name, vac.get_days_until(), msg.text if msg else None))
        if msg:
            await shot(display, msg, p(name + ".png"))

    print("\nsaved PNGs -> %s" % outdir)


if __name__ == "__main__":
    asyncio.run(main())
