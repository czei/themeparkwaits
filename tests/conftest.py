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


# --- canned themeparks.wiki payloads ---------------------------------------
# Loaded from tests/fixtures/ (captured/trimmed from the real API). The catalog
# (/v1/destinations) and live data (/v1/entity/{id}/live) cover every parsing
# branch: status enum (OPERATING/DOWN/CLOSED/REFURBISHMENT), STANDBY present /
# absent / null, non-ATTRACTION entities (PARK/SHOW/RESTAURANT), a meet-and-greet,
# and a duplicate park name ("Disneyland Park") across two destinations.
_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

with open(os.path.join(_FIXTURES, "themeparks_destinations.json")) as _f:
    DESTINATIONS_JSON = _f.read()
with open(os.path.join(_FIXTURES, "themeparks_mk_live.json")) as _f:
    LIVE_JSON = _f.read()

# Stable themeparks.wiki park ids used across tests (UUIDs, not integers).
MAGIC_KINGDOM_ID = "75ea578a-adc8-4116-a54d-dccb60765ef9"
EPCOT_ID = "47f90d2c-e191-4239-a466-5892ef59a88b"
DISNEYLAND_PARIS_ID = "ba88a23e-3d68-4d0b-8b5e-1a2b3c4d5e6f"
DISNEYLAND_ANAHEIM_ID = "7340550b-c14d-4def-80bb-acdb51d49a66"


def _canned_provider(url):
    """mock_provider(url) -> MockResponse for scrollkit.network.HttpClient.

    Routes the two themeparks.wiki endpoints the app uses: the catalog
    (``/v1/destinations``) and per-park live data (``/v1/entity/{id}/live``).
    """
    from scrollkit.network.http_client import MockResponse
    if url.endswith("/destinations"):
        return MockResponse(status_code=200, text=DESTINATIONS_JSON)
    if url.endswith("/live"):
        return MockResponse(status_code=200, text=LIVE_JSON)
    return MockResponse(status_code=404, text="{}")


@pytest.fixture
def mock_http_client():
    """An HttpClient wired to canned themeparks.wiki responses (no network)."""
    from scrollkit.network.http_client import HttpClient
    client = HttpClient(session=None, mock_provider=_canned_provider)
    client.set_use_live_data(False)
    return client


@pytest.fixture
def settings_factory(tmp_path):
    """Factory → the app's SettingsManager (real schema) backed by a temp file.

    Pass overrides as kwargs.
    """
    from src.settings_schema import make_settings

    def _make(**overrides):
        path = os.path.join(str(tmp_path), "settings.json")
        sm = make_settings(path)
        for k, v in overrides.items():
            sm.set(k, v)
        return sm

    return _make
