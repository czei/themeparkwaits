"""T019 — ThemeParkService fetch + parse onto scrollkit.network.HttpClient."""
import pytest

from src.api.theme_park_service import ThemeParkService


@pytest.mark.asyncio
async def test_fetch_park_list(mock_http_client, settings_factory):
    svc = ThemeParkService(mock_http_client, settings_factory())
    plist = await svc.fetch_park_list()
    names = {p.name for p in plist.park_list}
    assert {"Magic Kingdom", "Epcot"} <= names


@pytest.mark.asyncio
async def test_fetch_park_data_parses_rides(mock_http_client, settings_factory):
    svc = ThemeParkService(mock_http_client, settings_factory())
    data = await svc.fetch_park_data(6)
    assert data is not None
    from src.models.theme_park import ThemePark
    park = ThemePark(data, "Magic Kingdom", 6)
    waits = {r.name: r.wait_time for r in park.rides}
    assert waits["Space Mountain"] == 45
    assert "Mickey Meet & Greet" in waits


@pytest.mark.asyncio
async def test_update_selected_parks(mock_http_client, settings_factory):
    import json
    from tests.conftest import PARKS_JSON
    from src.models.theme_park_list import ThemeParkList

    svc = ThemeParkService(mock_http_client, settings_factory(selected_park_ids=[6]))
    svc.park_list = ThemeParkList(json.loads(PARKS_JSON))
    svc.park_list.load_settings(svc.settings_manager)
    updated = await svc.update_selected_parks()
    assert updated == 1
    assert any(r.name == "Space Mountain" for r in svc.park_list.selected_parks[0].rides)
