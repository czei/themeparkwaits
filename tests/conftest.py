"""Shared pytest fixtures and desktop import-path setup for ThemeParkWaits tests.

Adds the refactored ScrollKit library (sibling ``../ScrollKit Library/src``) and
this repo's ``src`` to ``sys.path`` so tests can ``import scrollkit`` and the app's
domain modules without installing anything. See specs/001-this-project-is/quickstart.md.
"""
import os
import sys

import pytest

# --- import paths -----------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # themeparkwaits/
_WORKSPACE = os.path.dirname(_REPO_ROOT)                                   # ScrollKit/
_LIB_SRC = os.path.join(_WORKSPACE, "ScrollKit Library", "src")           # ScrollKit Library/src

for _p in (_LIB_SRC, _REPO_ROOT, os.path.join(_REPO_ROOT, "src")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)


# --- canned queue-times.com payloads ---------------------------------------
PARKS_JSON = """
[{"id": 1, "name": "Walt Disney World", "parks": [
    {"id": 6, "name": "Magic Kingdom", "latitude": "28.4", "longitude": "-81.5"},
    {"id": 5, "name": "Epcot", "latitude": "28.3", "longitude": "-81.5"}]}]
"""

QUEUE_TIMES_JSON = """
{"lands": [{"id": 1, "name": "Tomorrowland", "rides": [
    {"id": 101, "name": "Space Mountain", "is_open": true, "wait_time": 45},
    {"id": 102, "name": "Astro Orbiter", "is_open": true, "wait_time": 0},
    {"id": 103, "name": "Buzz Lightyear", "is_open": false, "wait_time": 0}]}],
 "rides": [{"id": 104, "name": "Mickey Meet & Greet", "is_open": true, "wait_time": 15}]}
"""


def _canned_provider(url):
    """mock_provider(url) -> MockResponse for scrollkit.network.HttpClient."""
    from scrollkit.network.http_client import MockResponse
    if url.endswith("/parks.json"):
        return MockResponse(status_code=200, text=PARKS_JSON)
    if "queue_times.json" in url:
        return MockResponse(status_code=200, text=QUEUE_TIMES_JSON)
    return MockResponse(status_code=404, text="{}")


@pytest.fixture
def mock_http_client():
    """An HttpClient wired to canned queue-times responses (no network)."""
    from scrollkit.network.http_client import HttpClient
    client = HttpClient(session=None, mock_provider=_canned_provider)
    client.set_use_live_data(False)
    return client


@pytest.fixture
def settings_factory(tmp_path):
    """Factory → a scrollkit SettingsManager backed by a temp JSON file.

    Pass overrides as kwargs; defaults mirror src/settings_schema.py.
    """
    from scrollkit.config.settings_manager import SettingsManager

    def _make(**overrides):
        path = os.path.join(str(tmp_path), "settings.json")
        sm = SettingsManager(
            path,
            defaults={
                "sort_mode": "alphabetical",
                "group_by_park": False,
                "skip_closed": False,
                "skip_meet": False,
                "selected_park_ids": [],
            },
            bool_keys=["skip_closed", "skip_meet", "group_by_park"],
        )
        for k, v in overrides.items():
            sm.set(k, v)
        return sm

    return _make
