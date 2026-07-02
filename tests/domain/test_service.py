# Copyright (c) 2024-2026 Michael Czeiszperger
"""ThemeParkService fetch + parse on themeparks.wiki via scrollkit HttpClient."""
import pytest

from src.api.theme_park_service import ThemeParkService
from tests.conftest import DESTINATIONS_JSON, MAGIC_KINGDOM_ID


@pytest.mark.asyncio
async def test_fetch_park_list(mock_http_client, settings_factory):
    svc = ThemeParkService(mock_http_client, settings_factory())
    plist = await svc.fetch_park_list()
    names = {p.name for p in plist.park_list}
    assert {"Magic Kingdom Park", "EPCOT"} <= names


@pytest.mark.asyncio
async def test_fetch_park_data_parses_rides(mock_http_client, settings_factory):
    svc = ThemeParkService(mock_http_client, settings_factory())
    data = await svc.fetch_park_data(MAGIC_KINGDOM_ID)
    assert data is not None
    from src.models.theme_park import ThemePark
    park = ThemePark(data, "Magic Kingdom", MAGIC_KINGDOM_ID)
    waits = {r.name: r.wait_time for r in park.rides}
    assert waits["Space Mountain"] == 45
    assert "Mickey Meet & Greet" in waits


@pytest.mark.asyncio
async def test_update_selected_parks(mock_http_client, settings_factory):
    import json
    from src.models.theme_park_list import ThemeParkList

    svc = ThemeParkService(mock_http_client,
                           settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID]))
    svc.park_list = ThemeParkList(json.loads(DESTINATIONS_JSON))
    svc.park_list.load_settings(svc.settings_manager)
    updated = await svc.update_selected_parks()
    assert updated == 1
    assert any(r.name == "Space Mountain" for r in svc.park_list.selected_parks[0].rides)
