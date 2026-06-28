# Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""Content builder: sort / group / filter / closed / vacation / attribution, the
dual-zone ride LAYOUT (scrolling name + large wait number) is preserved, and each
ride's name effect (scrolling category) + number reveal (static category) are chosen
dynamically + at random from the live ScrollKit catalog."""
import json
import random

from scrollkit.display.content import ContentQueue
from src.models.theme_park_list import ThemeParkList
from src.models.vacation import Vacation
from src.ui.content_builder import build_content_queue
from src.ui.effect_catalog import scrolling_catalog
from src.ui.reveal_splash import SplashContent
from src.ui.ride_screen_content import RideScreenContent, ClosedRideContent
from tests.conftest import DESTINATIONS_JSON, LIVE_JSON, MAGIC_KINGDOM_ID


def _park_list_with_rides(settings):
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    plist.load_settings(settings)                 # selected_parks from settings
    mk = plist.get_park_by_id(MAGIC_KINGDOM_ID)
    mk.update(json.loads(LIVE_JSON))              # populate rides + is_open
    plist.selected_parks = [mk]                   # ensure it points at the populated park
    return plist


def _items(queue):
    return list(queue)


def _rides(queue):
    """Ride screens (the dual-zone layout content), in queue order."""
    return [c for c in queue if isinstance(c, (RideScreenContent, ClosedRideContent))]


def _texts(queue):
    """Text of every info-message scroller (rides expose their name via .ride_name)."""
    return [c.text for c in queue if hasattr(c, "text")]


def _build(sm, vac=None, seed=0):
    q = ContentQueue()
    build_content_queue(q, _park_list_with_rides(sm), sm, vac or Vacation(),
                        rng=random.Random(seed))
    return q


def test_rides_keep_dual_zone_layout_with_closed_and_zero_wait(settings_factory):
    """Rides are the dual-zone layout content (name + wait number), NOT merged lines."""
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], sort_mode="alphabetical")
    by_name = {c.ride_name: c for c in _rides(_build(sm))}
    # Space Mountain (OPERATING, wait 45) -> RideScreenContent showing the number
    assert isinstance(by_name["Space Mountain"], RideScreenContent)
    assert by_name["Space Mountain"].wait_minutes == 45
    # Astro Orbiter (OPERATING, wait 0) -> RideScreenContent showing 0 (parity)
    assert isinstance(by_name["Astro Orbiter"], RideScreenContent)
    assert by_name["Astro Orbiter"].wait_minutes == 0
    # Buzz Lightyear (CLOSED) -> ClosedRideContent
    assert isinstance(by_name["Buzz Lightyear"], ClosedRideContent)
    # Walt Disney World Railroad (DOWN) -> ClosedRideContent
    assert isinstance(by_name["Walt Disney World Railroad"], ClosedRideContent)


def test_skip_meet_and_skip_closed(settings_factory):
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], skip_meet=True, skip_closed=True)
    names = [c.ride_name for c in _rides(_build(sm))]
    assert "Mickey Meet & Greet" not in names      # skip_meet
    assert "Buzz Lightyear" not in names           # skip_closed (CLOSED)
    assert "Astro Orbiter" not in names            # skip_closed (is_open() False: wait 0)
    assert "Tom Sawyer Island" not in names        # skip_closed (REFURBISHMENT)
    assert "Space Mountain" in names               # open with wait survives


def test_sort_modes(settings_factory):
    def order(mode):
        sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], sort_mode=mode, skip_meet=True)
        return [c.ride_name for c in _rides(_build(sm))]

    assert order("alphabetical") == sorted(order("alphabetical"), key=str.lower)
    assert order("max_wait")[0] == "Space Mountain"     # 45 first
    assert order("min_wait")[-1] == "Space Mountain"    # 45 last


def test_ride_name_effect_alternates_on_off(settings_factory):
    """The ride NAME effect ALTERNATES on/off across rides (every other ride scrolls
    plain), so the board isn't busy — not an effect on every single name."""
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], skip_meet=True)
    rides = _rides(_build(sm, seed=3))
    assert len(rides) >= 3
    present = [c._name_content is not None for c in rides]
    # strict alternation, starting with an effect
    assert present == [i % 2 == 0 for i in range(len(rides))]
    # the rides WITHOUT an effect scroll plain; the others carry a catalog effect
    assert all(c._tpw_name_effect == "plain" for c in rides if c._name_content is None)


def test_ride_name_effect_chosen_dynamically_and_randomized(settings_factory):
    """When a ride name HAS an effect, it is a SCROLLING-category effect from the live
    catalog — the FULL set (motion scrollers AND palette colour effects), varied."""
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], skip_meet=True)
    rides = [c for c in _rides(_build(sm, seed=3)) if c._name_content is not None]
    cat = scrolling_catalog()
    valid = set(cat.scrollers) | set(cat.palettes)        # the full scrolling-tagged set
    assert valid and rides, "catalog must expose scrolling effects + some effect names"
    effects = [c._tpw_name_effect for c in rides]
    assert all(e in valid for e in effects)
    assert len(set(effects)) > 1                           # actually randomized
    # a palette colour effect (not just motion) reaches some names
    assert set(effects) & set(cat.palettes), "names never get a palette colour effect"


def test_wait_number_keeps_severity_colour_with_randomized_effect(settings_factory):
    """The big 2x wait NUMBER stays (layout unchanged) and KEEPS its green->red
    severity colour; its effect is randomized per ride across BOTH the assembly
    reveals (Rain/Swarm) and the held colour animations (sheen/pulse)."""
    from src.ui.content_builder import _NUMBER_EFFECTS
    from src.ui.ride_screen_content import NUMBER_STYLES
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], skip_meet=True)
    open_rides = [c for c in _rides(_build(sm, seed=4)) if isinstance(c, RideScreenContent)]
    assert open_rides
    assert set(_NUMBER_EFFECTS) >= {"Rain", "Swarm"} | set(NUMBER_STYLES)  # all four available
    effects = [c._tpw_number_effect for c in open_rides]
    assert all(e in _NUMBER_EFFECTS for e in effects)
    assert len(set(effects)) > 1                            # randomized across rides
    # SEVERITY colour preserved on the number for every style (Rain/Swarm drip/flock
    # in it; sheen/pulse shimmer it)
    by = {c.ride_name: c.wait_color for c in open_rides}
    assert by["Space Mountain"] == 0xFFC000                # 45 min -> amber


def test_splitflap_in_rotation_and_rain_direction_randomized(settings_factory):
    """The wait NUMBER rotation includes SplitFlap (digits flip into place), and the
    'Rain' drip now enters from a RANDOM edge per ride (top/bottom/left/right) instead
    of always the top. Other reveals don't steer a drip (direction stays top/None)."""
    from src.ui.content_builder import _NUMBER_EFFECTS
    from src.ui.ride_screen_content import DRIP_DIRECTIONS, WAIT_EFFECTS
    assert "SplitFlap" in _NUMBER_EFFECTS and "SplitFlap" in WAIT_EFFECTS

    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], skip_meet=True)
    number_effects, rain_dirs = set(), set()
    for seed in range(30):
        for c in _rides(_build(sm, seed=seed)):
            ne = getattr(c, "_tpw_number_effect", None)
            if ne is None:
                continue                                   # closed ride (no number)
            number_effects.add(ne)
            direction = getattr(c, "_tpw_drip_direction", None)
            if ne == "Rain":
                assert direction in DRIP_DIRECTIONS        # a valid entry edge
                rain_dirs.add(direction)
            else:
                assert direction in (None, "top")          # non-Rain: no steered drip
    assert "SplitFlap" in number_effects                   # SplitFlap actually reaches rides
    assert len(rain_dirs) > 1                              # Rain direction is randomized


def test_wait_color_severity_vs_fixed(settings_factory):
    """severity mode colors the wait NUMBER green->red by wait; fixed uses the
    setting. The big number is always present (its color, not its existence, varies)."""
    def waits(**overrides):
        sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], **overrides)
        return {c.ride_name: c.wait_color for c in _rides(_build(sm))
                if isinstance(c, RideScreenContent)}

    sev = waits()                                  # default wait_color_mode=severity
    assert sev["Astro Orbiter"] == 0x00FF00        # 0 min -> green
    assert sev["Mickey Meet & Greet"] == 0x00FF00  # 15 min -> green
    assert sev["Space Mountain"] == 0xFFC000       # 45 min -> amber

    fixed = waits(wait_color_mode="fixed", ride_wait_time_color="0xffffff")
    assert fixed["Space Mountain"] == 0xFFFFFF


def test_configure_message_has_no_effect(settings_factory):
    """The 'Configure at <domain>.local' setup URL is a plain ScrollingText (no
    text effect) so it stays maximally legible."""
    from scrollkit.display.content import ScrollingText
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    configure = [c for c in _items(_build(sm))
                 if hasattr(c, "text") and "Configure at" in c.text]
    assert configure, "Configure message should be present"
    assert all(isinstance(c, ScrollingText) for c in configure)        # plain scroller
    assert all(getattr(c, "_tpw_effect", None) == "plain" for c in configure)


def test_group_by_park_adds_header_and_attribution(settings_factory):
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], group_by_park=True)
    texts = _texts(_build(sm))
    assert any("Magic Kingdom Park wait times" in t for t in texts)
    assert any("provided by ThemeParks.wiki" in t for t in texts)   # attribution
    assert not any("queue-times" in t for t in texts)               # never the old source


def test_splash_caps_each_cycle(settings_factory):
    """The swarm splash is the LAST queue item, after all rides + attribution."""
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    items = _items(_build(sm))
    assert isinstance(items[-1], SplashContent)                    # caps the cycle
    assert sum(isinstance(c, SplashContent) for c in items) == 1   # exactly one
    last_ride = max(i for i, c in enumerate(items)
                    if isinstance(c, (RideScreenContent, ClosedRideContent)))
    assert items.index(items[-1]) > last_ride


def test_no_splash_when_no_parks(settings_factory):
    sm = settings_factory()
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))   # nothing selected
    q = ContentQueue()
    build_content_queue(q, plist, sm, Vacation(), rng=random.Random(0))
    assert not any(isinstance(c, SplashContent) for c in _items(q))


def test_no_parks_shows_choose_message(settings_factory):
    sm = settings_factory()
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))   # nothing selected
    q = ContentQueue()
    build_content_queue(q, plist, sm, Vacation(), rng=random.Random(0))
    assert any("Choose theme park" in t for t in _texts(q))


def test_vacation_messages(settings_factory):
    from datetime import datetime, timedelta
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    target = datetime.now() + timedelta(days=5)
    vac = Vacation("Magic Kingdom", target.year, target.month, target.day)
    assert any("Vacation to Magic Kingdom in:" in t for t in _texts(_build(sm, vac)))
