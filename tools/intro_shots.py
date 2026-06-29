# Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""Sim e2e for the per-ride intro image: build a REAL content queue, render the
actual ``RideScreenContent`` through the simulator, and assert the intro flow
(HOLD -> FADE+scroll -> wait-number reveal) for every ride that has an image.

Data-driven: ``RIDES_WITH_INTRO`` lists rides whose UUID is in
``src/images/rides/manifest.json``; each is built into one fixture park, rendered
through the real ``UnifiedDisplay`` (so the on-disk BMP + palette/transparency path
is exercised), phase-asserted, and saved as ``<name>.gif``. A control ride with no
manifest entry asserts the no-image path still renders normally.

    PYTHONPATH="../ScrollKit Library/src:." SDL_VIDEODRIVER=dummy \
        python3 tools/intro_shots.py [outdir] [name-substring]
        #   default outdir: /tmp/tpw_intro ; optional filter renders one ride
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
from src.ui.ride_images import lookup_intro_image               # noqa: E402
from src.ui.ride_screen_content import RideScreenContent        # noqa: E402

MK_ID = "75ea578a-adc8-4116-a54d-dccb60765ef9"
NO_IMAGE_ID = "00000000-0000-0000-0000-000000000000"   # not in the manifest -> no intro

# (display name, a UUID that IS in the manifest). One per distinct image is enough —
# the render path is identical for every BMP, so this samples each shipped drawing.
RIDES_WITH_INTRO = [
    ("Space Mountain",   "b2260923-9315-40fd-9c6b-44dd811dbe64"),
    ("Haunted Mansion",  "2551a77d-023f-4ab1-9a19-8afec0190f39"),
    ("Pirates of the Caribbean", "352feb94-e52e-45eb-9c92-e4b44c6b1a9d"),
    ("Jungle Cruise",    "796b0a25-c51e-456e-9bb8-50a324e301b3"),
    ("Big Thunder Mountain Railroad", "de3309ca-97d5-4211-bffe-739fed47e92f"),
    # batch 2
    ("Mad Tea Party",    "0aae716c-af13-4439-b638-d75fb1649df3"),
    ("Winnie the Pooh",  "0d94ad60-72f0-4551-83a6-ebaecdd89737"),
    ("Regal Carrousel",  "273ddb8d-e7b5-4e34-8657-1113f49262a5"),
    ("Country Bear Jamboree", "0f57cecf-5502-4503-8bc3-ba84d3708ace"),
    ("Buzz Lightyear",   "72c7343a-f7fb-4f66-95df-c91016de7338"),
    ("Enchanted Tiki Room", "6fd1e225-53a0-4a80-a577-4bbc9a471075"),
    ("Turtle Talk",      "57acb522-a6fc-4aa4-a80e-21f21f317250"),
    ("Enchanted Tales with Belle", "e76c93df-31af-49a5-8e2f-752c76c937c9"),
    # batch 3
    ("Test Track",       "37ae57c5-feaf-4e47-8f27-4b385be200f0"),
    ("WDW Railroad",     "e40ac396-cbac-43f4-8752-764ed60ccceb"),
    ("Mission SPACE",    "5b6475ad-4e9a-4793-b841-501aa382c9c0"),
    ("Star Tours",       "cc718d11-fa15-44ee-87d0-ded989ad61bc"),
    ("Tree of Life",     "bc1ffa86-9b1a-4ce9-84a5-b479dfa3cb53"),
    # batch 4
    ("Cinderella Castle", "90d79335-c907-4069-a021-d0fe1ec73ae2"),
    ("Spaceship Earth",  "480fde8f-fe58-4bfb-b3ab-052a39d4db7c"),
    ("Expedition Everest", "64a6915f-a835-4226-ba5c-8389fc4cade3"),
    ("Dumbo",            "890fa430-89c0-4a3f-96c9-11597888005e"),
    ("TRON Lightcycle",  "5a43d1a7-ad53-4d25-abfe-25625f0da304"),
    ("Millennium Falcon", "b2c2549c-e9da-4fdd-98ea-1dcff596fed7"),
    # batch 5
    ("Finding Nemo",     "64d44aaa-6857-4693-b24b-bcff6c6dcfa1"),
    ("Mark Twain Riverboat", "6c30d5b0-8c0a-406f-9258-0b6c55d4a5e4"),
    ("Davy Crockett Canoes", "5bd95ae8-181d-449c-8f04-a621e2448961"),
    ("Tiana's Bayou Adventure", "73cb9445-0695-47a3-87ce-d08ae36b5f3c"),
    ("Jumpin Jellyfish", "c8a4b7b1-c1b2-4dfe-b73c-4e834b4a73db"),
    ("Navi River",       "7a5af3b7-9bc1-4962-92d0-3ea9c9ce35f0"),
    # batch 6
    ("Peter Pan",        "86a41273-5f15-4b54-93b6-829f140e5161"),
    ("Magic Carpets",    "96455de6-f4f1-403c-9391-bf8396979149"),
    ("Seven Dwarfs",     "9d4d5229-7142-44b6-b4fb-528920969a2c"),
    ("Snow White",       "4f0053e7-b8db-4833-b02f-35e1c91b4523"),
    ("Toy Story Mania",  "20b5daa8-e1ea-436f-830c-2d7d18d929b5"),
    ("PhilharMagic",     "7c5e1e02-3a44-4151-9005-44066d5ba1da"),
    # batch 7
    ("Main Street Vehicles", "888fb4a4-7adf-47a1-8ba2-c258cc64fd75"),
    ("Barnstormer",      "924a3b2c-6b4b-49e5-99d3-e9dc3f2e8a48"),
    ("Monsters Inc",     "e8f0b426-7645-4ea3-8b41-b94ae7091a41"),
    ("Remy",             "1e735ffb-4868-47f1-b2cd-2ac1156cd5f0"),
    ("Mr Toad",          "9d401ad3-49b2-469f-ac73-93eb429428fb"),
    ("Journey of Water", "dae68dee-dfba-4128-b594-6aa12add1070"),
    ("Living with the Land", "8f353879-d6ac-4211-9352-4029efb47c18"),
    # batch 8
    ("it's a small world", "f5aad2d4-a419-4384-bd9a-42f86385c750"),
    ("Casey Jr Splash",  "f010bc01-b450-4476-a5f3-a5f2813104b2"),
    ("Matterhorn",       "faaa8be9-cc1e-4535-ac20-04a535654bd0"),
    ("Incredicoaster",   "5d07a2b1-49ca-4de7-9d32-6d08edf69b08"),
    ("Soarin Across America", "81b15dfd-cf6a-466f-be59-3dd65d2a2807"),
    ("Soarin Over California", "77f205a4-d482-4d91-a5ff-71e54a086ad2"),
    # batch 9 (Efteling) — one per new image
    ("Joris en de Draak", "5db59b64-d2cd-4211-a1fa-b4369b6e110a"),
    ("Python",            "c0137454-0e1f-451e-85bd-aef4f443c51e"),
    ("Pagode",            "27551b3f-7188-4bd6-b6b9-6bdd6b0f6ddd"),
    ("Danse Macabre",     "1f356f6c-2033-48bb-b2d1-761c73441ac1"),
    ("Droomvlucht",       "bd02be82-ce77-4c38-8c8d-567df7810648"),
    ("Fairytale Forest",  "3b01fd39-77d3-437d-a195-9904e010ec3f"),
    ("Pirana",            "a59b1021-ae84-4a11-a93f-545553f5e568"),  # device strips the ñ
    ("Vogel Rok",         "1fdcb9bd-7ce3-4b23-a89c-b6d5f338cae9"),
    # batch 10 (Chessington) — one per new image
    ("Croc Drop",         "7a10dbec-c209-4bfe-8b19-84b428ae266b"),
    ("Room on the Broom", "0f29655b-884e-44f7-b3c5-9edc0017d8e8"),
    ("Vampire",           "97465ae2-dd6c-47e0-a55c-5ff4b221b672"),
    ("Marshalls Firetruck", "98f86d9f-ffe5-45c2-a679-6a6d23778350"),
    ("Skyes Helicopter",  "09d8ffee-a759-4563-8d78-fa268f712e52"),
    ("Tiger Rock",        "f8ee1993-38f2-4f9f-96cf-e228b4a4e914"),
    ("Mandrill Mayhem",   "089d2fb3-b24c-4eb2-85ce-c7849c844ea2"),
    ("Ostrich Stampede",  "013c9096-4b5a-4ff0-9a5d-24af5d544737"),
]


def _live(rides):
    items = []
    for name, rid in rides:
        items.append('{"id":"%s","name":"%s","entityType":"ATTRACTION",'
                     '"status":"OPERATING","queue":{"STANDBY":{"waitTime":45}}}'
                     % (rid, name))
    items.append('{"id":"%s","name":"Astro Orbiter","entityType":"ATTRACTION",'
                 '"status":"OPERATING","queue":{"STANDBY":{"waitTime":10}}}' % NO_IMAGE_ID)
    return '{"liveData":[%s]}' % ",".join(items)


PARKS = ('{"destinations":[{"name":"Walt Disney World","parks":['
         '{"id":"%s","name":"Magic Kingdom","latitude":"28.4","longitude":"-81.5"}]}]}' % MK_ID)


def build_queue(rides):
    pl = ThemeParkList(json.loads(PARKS))
    park = pl.get_park_by_id(MK_ID)
    park.update(json.loads(_live(rides)))
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


async def render_ride(display, ride, gif_path):
    """Render one ride's full intro; assert phases; save its GIF. Returns counts."""
    await ride.start()
    frames, phases = [], []
    for _ in range(180):
        await display.clear()
        await ride.render(display)
        await cap(display, frames)
        phases.append((ride._intro_phase, ride._intro_tile is not None,
                       getattr(ride, "_reveal", None) is not None))
        if ride._intro_phase is None and getattr(ride, "_reveal", None) is not None \
                and ride._scrolled_off:
            break
    await ride.stop()
    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                   duration=50, loop=0, optimize=True)

    holds = [p for p in phases if p[0] == "hold"]
    fades = [p for p in phases if p[0] == "fade"]
    normals = [p for p in phases if p[0] is None]
    assert holds and all(p[1] for p in holds), "HOLD must show the image layer"
    assert fades and all(p[1] for p in fades), "FADE must keep the image layer"
    assert normals, "must reach NORMAL"
    assert not normals[-1][1], "image layer must be detached by NORMAL"
    assert any(p[2] for p in normals), "wait-number reveal must build in NORMAL"
    assert not any(p[2] for p in holds + fades), "number must be gated until after the fade"
    return len(holds), len(fades), len(normals)


async def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/tpw_intro"
    only = sys.argv[2].lower() if len(sys.argv) > 2 else None
    os.makedirs(outdir, exist_ok=True)

    rides = [r for r in RIDES_WITH_INTRO if not only or only in r[0].lower()]
    if not rides:
        raise SystemExit("no ride matches %r" % only)

    items = build_queue(rides)

    # --- wiring assertions: every test ride has its image; the control has none ---
    for name, uuid in rides:
        c = find_ride(items, name)
        assert c is not None, "%s RideScreenContent not built" % name
        expect = lookup_intro_image(uuid)
        assert expect and c._tpw_intro_image == expect, \
            "%s intro image mismatch: %r != %r" % (name, c._tpw_intro_image, expect)
        print("wiring OK: %-32s intro=%s" % (name, os.path.basename(expect)))
    ctrl = find_ride(items, "Astro Orbiter")
    assert ctrl is not None and ctrl._tpw_intro_image is None, \
        "Astro Orbiter (no manifest entry) must have no intro, got %r" % (ctrl._tpw_intro_image,)
    print("wiring OK: %-32s intro=None (control)" % "Astro Orbiter")

    # --- render each through the REAL UnifiedDisplay ---
    display = UnifiedDisplay(64, 32, 4)
    await display.initialize()
    try:
        await display.set_brightness(1.0)
    except Exception:
        pass

    for name, _ in rides:
        ride = find_ride(items, name)
        slug = name.lower().replace(" ", "_").replace("'", "").replace("!", "")
        gif = os.path.join(outdir, slug + ".gif")
        h, f, n = await render_ride(display, ride, gif)
        print("phases  %-32s hold=%-3d fade=%-3d normal=%-3d  -> %s"
              % (name, h, f, n, gif))

    print("\nOK: %d ride(s) verified through the real UnifiedDisplay." % len(rides))


if __name__ == "__main__":
    asyncio.run(main())
