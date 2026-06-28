# Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""Domain model tests: ThemePark / ThemeParkRide / ThemeParkList on themeparks.wiki."""
import json

from src.models.theme_park import ThemePark
from src.models.theme_park_ride import ThemeParkRide
from src.models.theme_park_list import ThemeParkList
from tests.conftest import (
    DESTINATIONS_JSON,
    LIVE_JSON,
    MAGIC_KINGDOM_ID,
    EPCOT_ID,
    DISNEYLAND_PARIS_ID,
    DISNEYLAND_ANAHEIM_ID,
)


def test_remove_non_ascii():
    assert ThemePark.remove_non_ascii("Café Wörld") == "Caf Wrld"
    assert ThemePark.remove_non_ascii("Magic Kingdom") == "Magic Kingdom"


def test_is_valid_requires_real_id():
    assert ThemePark().is_valid() is False                       # default sentinel
    assert ThemePark("", "Magic Kingdom", MAGIC_KINGDOM_ID).is_valid() is True


def test_ride_is_open_rule():
    # open_flag True AND wait_time > 0 -> open
    assert ThemeParkRide("Space Mountain", "a", 45, True).is_open() is True
    # open_flag True but wait_time == 0 -> NOT open (closed-park / no-standby quirk)
    assert ThemeParkRide("Astro Orbiter", "b", 0, True).is_open() is False
    # open_flag False -> not open
    assert ThemeParkRide("Buzz", "c", 0, False).is_open() is False


# --- US1: live parsing + status mapping ------------------------------------
def test_park_parses_only_attractions():
    park = ThemePark(json.loads(LIVE_JSON), "Magic Kingdom", MAGIC_KINGDOM_ID)
    names = {r.name for r in park.rides}
    assert "Space Mountain" in names              # ATTRACTION
    assert "Mickey Meet & Greet" in names         # ATTRACTION (meet-and-greet)
    # non-attraction entities are excluded
    assert "Festival of Fantasy Parade" not in names   # SHOW
    assert "Be Our Guest Restaurant" not in names      # RESTAURANT
    assert "Magic Kingdom Park" not in names           # PARK entity
    assert park.is_open is True                   # at least one OPERATING attraction


def test_status_maps_to_open_flag():
    park = ThemePark(json.loads(LIVE_JSON), "Magic Kingdom", MAGIC_KINGDOM_ID)
    by_name = {r.name: r for r in park.rides}
    assert by_name["Space Mountain"].open_flag is True          # OPERATING
    assert by_name["Buzz Lightyear"].open_flag is False         # CLOSED
    assert by_name["Walt Disney World Railroad"].open_flag is False   # DOWN -> closed
    assert by_name["Tom Sawyer Island"].open_flag is False      # REFURBISHMENT -> closed


def test_standby_wait_extraction_and_null_safety():
    park = ThemePark(json.loads(LIVE_JSON), "Magic Kingdom", MAGIC_KINGDOM_ID)
    by_name = {r.name: r for r in park.rides}
    assert by_name["Space Mountain"].wait_time == 45           # STANDBY present
    assert by_name["Astro Orbiter"].wait_time == 0            # STANDBY 0
    assert by_name["TRON Lightcycle / Run"].wait_time == 0    # no STANDBY (RETURN_TIME only)
    assert by_name["Casey Jr. Splash 'N' Soak Station"].wait_time == 0  # STANDBY waitTime null
    # OPERATING with no standby is still "open" (shows 0), per parity
    assert by_name["TRON Lightcycle / Run"].open_flag is True


def test_ride_name_is_ascii_stripped():
    # Build a one-off entity with a non-ASCII name and confirm stripping.
    data = {"liveData": [{"id": "x", "name": "Sœur Café", "entityType": "ATTRACTION",
                          "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 5}}}]}
    park = ThemePark(data, "x", "x")
    assert park.rides[0].name == "Sur Caf"


def test_malformed_queue_does_not_drop_later_rides():
    """A non-dict queue/STANDBY must not crash parsing or abort the remaining rides
    (FR-016 never-crash on malformed data)."""
    data = {"liveData": [
        {"id": "a", "name": "Good One", "entityType": "ATTRACTION",
         "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 10}}},
        {"id": "b", "name": "Malformed", "entityType": "ATTRACTION",
         "status": "OPERATING", "queue": [1, 2]},          # queue is a LIST, not a dict
        {"id": "c", "name": "After", "entityType": "ATTRACTION",
         "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 20}}},
    ]}
    park = ThemePark(data, "x", "x")
    by_name = {r.name: r for r in park.rides}
    assert set(by_name) == {"Good One", "Malformed", "After"}   # none dropped
    assert by_name["Malformed"].wait_time == 0                  # safe fallback
    assert by_name["After"].wait_time == 20                     # parsing continued


def test_is_legacy_id_classification():
    f = ThemeParkList._is_legacy_id
    assert f(6) is True and f(5) is True          # positive legacy integers
    assert f("6") is True                          # all-digit legacy string
    assert f(-1) is False                          # the app's own sentinel
    assert f(0) is False                           # empty/zero, not a real id
    assert f("") is False                          # blank
    assert f(MAGIC_KINGDOM_ID) is False            # a real UUID (has hyphens)
    assert f(True) is False                         # bool is not an id


def test_skip_flags_survive_a_migration_boot(settings_factory):
    """The migration must not stop skip_meet/skip_closed from loading on the
    upgrade boot (regression guard for the early-return that used to skip them)."""
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    sm = settings_factory(selected_park_ids=[6], skip_meet=True, skip_closed=True)
    plist.load_settings(sm)
    assert plist.selected_parks == []          # legacy selection cleared
    assert plist.skip_meet is True             # ...but skip flags still loaded
    assert plist.skip_closed is True


# --- US2: catalog parsing + disambiguation + migration ----------------------
def test_park_list_parses_destinations():
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    names = {p.name for p in plist.park_list}
    assert {"Magic Kingdom Park", "EPCOT"} <= names
    mk = plist.get_park_by_id(MAGIC_KINGDOM_ID)
    assert mk is not None and mk.name == "Magic Kingdom Park"


def test_duplicate_park_carries_destination():
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    dlp = plist.get_park_by_id(DISNEYLAND_PARIS_ID)
    dlr = plist.get_park_by_id(DISNEYLAND_ANAHEIM_ID)
    assert dlp.name == dlr.name == "Disneyland Park"           # same name
    assert dlp.destination_name == "Disneyland Paris"          # distinct destinations
    assert dlr.destination_name == "Disneyland Resort"


def test_selected_parks_with_uuids(settings_factory):
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID, EPCOT_ID])
    plist.load_settings(sm)
    assert [p.id for p in plist.selected_parks] == [MAGIC_KINGDOM_ID, EPCOT_ID]
    assert plist.current_park.id == MAGIC_KINGDOM_ID           # back-compat: first selected


def test_legacy_integer_ids_are_cleared_on_upgrade(settings_factory):
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    sm = settings_factory(selected_park_ids=[6, 5],            # queue-times integers
                          selected_park_names=["Magic Kingdom", "Epcot"],
                          current_park_id=6)
    plist.load_settings(sm)
    assert plist.selected_parks == []                          # cleared
    assert sm.settings.get("selected_park_ids") in (None, [])
    assert "current_park_id" not in sm.settings


def test_legacy_single_park_id_is_cleared(settings_factory):
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    sm = settings_factory()
    sm.settings.pop("selected_park_ids", None)
    sm.settings["current_park_id"] = 5                         # legacy single int id
    plist.load_settings(sm)
    assert plist.selected_parks == []
    assert "current_park_id" not in sm.settings


def test_valid_uuid_selection_is_not_cleared(settings_factory):
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    plist.load_settings(sm)
    assert sm.settings.get("selected_park_ids") == [MAGIC_KINGDOM_ID]   # kept
    assert [p.id for p in plist.selected_parks] == [MAGIC_KINGDOM_ID]
