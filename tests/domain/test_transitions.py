"""Per-item screen transitions: every scrolling screen is tagged with a transition
chosen from the live catalog; the splash is not. Plus app._get_transition selection."""
import json
import random

from scrollkit.display.content import ContentQueue
from src.app import ThemeParkApp
from src.models.theme_park_list import ThemeParkList
from src.models.vacation import Vacation
from src.ui.content_builder import build_content_queue, _TX_SCROLL
from src.ui.effect_catalog import scrolling_catalog
from src.ui.reveal_splash import SplashContent
from tests.conftest import DESTINATIONS_JSON, LIVE_JSON, MAGIC_KINGDOM_ID


def _plist(sm):
    plist = ThemeParkList(json.loads(DESTINATIONS_JSON))
    plist.load_settings(sm)
    mk = plist.get_park_by_id(MAGIC_KINGDOM_ID)
    mk.update(json.loads(LIVE_JSON))
    plist.selected_parks = [mk]
    return plist


def _tag(c):
    return getattr(c, "_tpw_transition", None)


def test_every_screen_tagged_from_catalog_splash_not(settings_factory):
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID], group_by_park=True)
    q = ContentQueue()
    build_content_queue(q, _plist(sm), sm, Vacation(), rng=random.Random(0))
    cat = scrolling_catalog()
    valid = set(cat.transitions) | {_TX_SCROLL}
    items = list(q)
    for c in items:
        if isinstance(c, SplashContent):
            assert _tag(c) is None        # the splash's swarm reveal IS its entrance
        else:
            assert _tag(c) in valid       # every scrolling screen has a catalog tag


def _Tagged_cls():
    class _Tagged:
        _tpw_transition = "Iris Snap"
    return _Tagged()


class _Untagged:
    pass


def test_get_transition_auto_selects_by_tag(mock_http_client, settings_factory):
    sm = settings_factory(transition_style="Auto")
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)

    app._current_content = _Tagged_cls()
    assert app._get_transition() is not None        # Auto + tag -> a transition
    app._current_content = _Untagged()
    assert app._get_transition() is None            # Auto + untagged (splash) -> none


def test_get_transition_none_and_specific(mock_http_client, settings_factory):
    sm = settings_factory(transition_style="None")
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    app._current_content = _Tagged_cls()
    assert app._get_transition() is None             # master off

    sm.set("transition_style", "Scan Fold")          # a specific global transition
    assert app._get_transition() is not None         # falls through to library behavior
