"""Content builder: sort / group / filter / closed / vacation / attribution."""
import json

from scrollkit.display.content import ContentQueue, ScrollingText
from src.models.theme_park_list import ThemeParkList
from src.models.vacation import Vacation
from src.ui.content_builder import build_content_queue
from src.ui.ride_screen_content import RideScreenContent, ClosedRideContent
from tests.conftest import DESTINATIONS_JSON, LIVE_JSON, MAGIC_KINGDOM_ID


def _park_list_with_rides(settings):
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    plist.load_settings(settings)                 # selected_parks from settings
    mk = plist.get_park_by_id(MAGIC_KINGDOM_ID)
    mk.update(json.loads(LIVE_JSON))              # populate rides + is_open
    # ensure selected_parks points at the populated park object
    plist.selected_parks = [mk]
    return plist


def _items(queue):
    return list(queue)


def test_builds_rides_with_closed_and_zero_wait(settings_factory):
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], sort_mode="alphabetical")
    q = ContentQueue()
    build_content_queue(q, _park_list_with_rides(sm), sm, Vacation())
    rides = [c for c in _items(q) if isinstance(c, (RideScreenContent, ClosedRideContent))]
    by_name = {c.ride_name: c for c in rides}
    # Space Mountain (OPERATING, wait 45) -> RideScreenContent
    assert isinstance(by_name["Space Mountain"], RideScreenContent)
    assert by_name["Space Mountain"].wait_minutes == 45
    # Astro Orbiter (OPERATING, wait 0) -> RideScreenContent showing 0 (parity)
    assert isinstance(by_name["Astro Orbiter"], RideScreenContent)
    assert by_name["Astro Orbiter"].wait_minutes == 0
    # Buzz Lightyear (CLOSED) -> ClosedRideContent
    assert isinstance(by_name["Buzz Lightyear"], ClosedRideContent)
    # Walt Disney World Railroad (DOWN) -> ClosedRideContent (non-OPERATING -> closed)
    assert isinstance(by_name["Walt Disney World Railroad"], ClosedRideContent)


def test_skip_meet_and_skip_closed(settings_factory):
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], skip_meet=True, skip_closed=True)
    q = ContentQueue()
    build_content_queue(q, _park_list_with_rides(sm), sm, Vacation())
    names = [c.ride_name for c in _items(q)
             if isinstance(c, (RideScreenContent, ClosedRideContent))]
    assert "Mickey Meet & Greet" not in names      # skip_meet
    assert "Buzz Lightyear" not in names           # skip_closed (CLOSED)
    assert "Astro Orbiter" not in names            # skip_closed (is_open() False: wait 0)
    assert "Tom Sawyer Island" not in names        # skip_closed (REFURBISHMENT)
    assert "Space Mountain" in names               # open with wait survives


def test_sort_modes(settings_factory):
    def ride_order(mode):
        sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], sort_mode=mode, skip_meet=True)
        q = ContentQueue()
        build_content_queue(q, _park_list_with_rides(sm), sm, Vacation())
        return [c.ride_name for c in _items(q)
                if isinstance(c, (RideScreenContent, ClosedRideContent))]

    assert ride_order("alphabetical") == sorted(ride_order("alphabetical"), key=str.lower)
    # max_wait: Space Mountain (45) first
    assert ride_order("max_wait")[0] == "Space Mountain"
    # min_wait: Space Mountain (45) last
    assert ride_order("min_wait")[-1] == "Space Mountain"


def test_wait_time_effect_threads_to_rides(settings_factory):
    """The wait_time_effect setting reaches every open ride; default is Rain."""
    def effects(**overrides):
        sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], **overrides)
        q = ContentQueue()
        build_content_queue(q, _park_list_with_rides(sm), sm, Vacation())
        return {c.effect for c in _items(q) if isinstance(c, RideScreenContent)}

    assert effects() == {"Rain"}                       # default
    assert effects(wait_time_effect="Swarm") == {"Swarm"}
    assert effects(wait_time_effect="None") == {"None"}
    # grouped mode threads it too
    assert effects(wait_time_effect="Swarm", group_by_park=True) == {"Swarm"}


def test_wait_color_severity_vs_fixed(settings_factory):
    """severity mode colors the number green->red by wait; fixed uses the setting."""
    def waits(**overrides):
        sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], **overrides)
        q = ContentQueue()
        build_content_queue(q, _park_list_with_rides(sm), sm, Vacation())
        return {c.ride_name: c.wait_color for c in _items(q)
                if isinstance(c, RideScreenContent)}

    sev = waits()                                  # default wait_color_mode=severity
    assert sev["Astro Orbiter"] == 0x00FF00        # 0 min -> green
    assert sev["Mickey Meet & Greet"] == 0x00FF00  # 15 min -> green
    assert sev["Space Mountain"] == 0xFFC000       # 45 min -> amber

    fixed = waits(wait_color_mode="fixed", ride_wait_time_color="0xffffff")
    assert set(fixed.values()) == {0xFFFFFF}        # all use the fixed setting


def test_group_by_park_adds_header_and_attribution(settings_factory):
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], group_by_park=True)
    q = ContentQueue()
    build_content_queue(q, _park_list_with_rides(sm), sm, Vacation())
    texts = [c.text for c in _items(q) if isinstance(c, ScrollingText)]
    assert any("Magic Kingdom Park wait times" in t for t in texts)
    assert any("provided by ThemeParks.wiki" in t for t in texts)   # attribution
    assert not any("queue-times" in t for t in texts)               # never the old source


def test_no_parks_shows_choose_message(settings_factory):
    sm = settings_factory()
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))   # nothing selected
    q = ContentQueue()
    build_content_queue(q, plist, sm, Vacation())
    texts = [c.text for c in _items(q) if isinstance(c, ScrollingText)]
    assert any("Choose theme park" in t for t in texts)


def test_vacation_messages(settings_factory):
    from datetime import datetime, timedelta
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    target = datetime.now() + timedelta(days=5)
    vac = Vacation("Magic Kingdom", target.year, target.month, target.day)
    q = ContentQueue()
    build_content_queue(q, _park_list_with_rides(sm), sm, vac)
    texts = [c.text for c in _items(q) if isinstance(c, ScrollingText)]
    assert any("Vacation to Magic Kingdom in:" in t for t in texts)
