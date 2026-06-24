"""T007 — vacation countdown math, including tomorrow/today special cases."""
from datetime import datetime, timedelta

from src.models.vacation import Vacation


def _vac_in(days):
    target = datetime.now() + timedelta(days=days)
    return Vacation("Magic Kingdom", target.year, target.month, target.day)


def test_is_set():
    assert Vacation("", 0, 0, 0).is_set() is False
    assert Vacation("MK", 1999, 1, 1).is_set() is False   # year must be > 1999
    assert Vacation("MK", 2030, 6, 1).is_set() is True


def test_days_until_future():
    # get_days_until returns diff.days + 1; ~5 days out -> ~5/6 depending on time of day
    assert _vac_in(5).get_days_until() in (5, 6)


def test_today_and_tomorrow_boundaries():
    # day-of: target == now -> diff.days is -1 (now slightly past midnight target) or 0; +1 => 0 or 1
    assert _vac_in(0).get_days_until() in (0, 1)
    assert _vac_in(1).get_days_until() in (1, 2)


def test_load_store_round_trip(settings_factory):
    sm = settings_factory()
    v = Vacation("Epcot", 2030, 12, 25)
    v.store_settings(sm)
    v2 = Vacation()
    v2.load_settings(sm)
    assert (v2.name, v2.year, v2.month, v2.day) == ("Epcot", 2030, 12, 25)
