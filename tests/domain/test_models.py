"""T006 — domain model tests: ThemePark / ThemeParkRide / ThemeParkList."""
import json

from src.models.theme_park import ThemePark
from src.models.theme_park_ride import ThemeParkRide
from src.models.theme_park_list import ThemeParkList
from tests.conftest import PARKS_JSON, QUEUE_TIMES_JSON


def test_remove_non_ascii():
    assert ThemePark.remove_non_ascii("Café Wörld") == "Caf Wrld"
    assert ThemePark.remove_non_ascii("Magic Kingdom") == "Magic Kingdom"


def test_get_url():
    park = ThemePark("", "Magic Kingdom", 6, 28.4, -81.5)
    assert park.get_url() == "https://queue-times.com/parks/6/queue_times.json"


def test_ride_is_open_rule():
    # open_flag True AND wait_time > 0 -> open
    assert ThemeParkRide("Space Mountain", 101, 45, True).is_open() is True
    # open_flag True but wait_time == 0 -> NOT open (closed-park quirk)
    assert ThemeParkRide("Astro Orbiter", 102, 0, True).is_open() is False
    # open_flag False -> not open
    assert ThemeParkRide("Buzz", 103, 0, False).is_open() is False


def test_park_parses_lands_and_direct_rides():
    park = ThemePark(json.loads(QUEUE_TIMES_JSON), "Magic Kingdom", 6)
    names = {r.name for r in park.rides}
    assert "Space Mountain" in names          # from lands[].rides
    assert "Mickey Meet & Greet" in names     # from top-level rides[]
    assert park.is_open is True               # at least one ride open


def test_park_list_parses_company_structure():
    plist = ThemeParkList(json.loads(PARKS_JSON))
    names = {p.name for p in plist.park_list}
    assert {"Magic Kingdom", "Epcot"} <= names
    mk = plist.get_park_by_id(6)
    assert mk is not None and mk.name == "Magic Kingdom"


def test_park_list_selected_parks_and_legacy(settings_factory):
    plist = ThemeParkList(json.loads(PARKS_JSON))
    # new-style multi-park
    sm = settings_factory(selected_park_ids=[6, 5])
    plist.load_settings(sm)
    assert [p.id for p in plist.selected_parks] == [6, 5]
    assert plist.current_park.id == 6  # back-compat: first selected

    # legacy single-park fallback
    plist2 = ThemeParkList(json.loads(PARKS_JSON))
    sm2 = settings_factory()
    sm2.settings.pop("selected_park_ids", None)
    sm2.settings["current_park_id"] = 5
    plist2.load_settings(sm2)
    assert plist2.current_park.id == 5
