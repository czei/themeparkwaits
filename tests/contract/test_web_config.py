"""T023-T025 — config web handler: render the form + apply POSTed settings."""
from scrollkit.web.adapters import DevelopmentAdapter, MockRequest
from src.web.config_server import make_handler_class
from src.app import ThemeParkApp


def _handler(app):
    HandlerCls = make_handler_class(app)
    adapter = DevelopmentAdapter(HandlerCls, "src/www")
    return HandlerCls(adapter), adapter


async def test_index_page_lists_parks(mock_http_client, settings_factory):
    app = ThemeParkApp(http_client=mock_http_client, settings=settings_factory(), enable_web=True)
    await app.service.initialize()                      # fetch park list (mock)
    handler, adapter = _handler(app)
    resp = handler.route_index(MockRequest("GET", "/", "", "", adapter))
    assert resp.status == 200
    assert "ThemeParkWaits" in resp.body
    assert "Magic Kingdom" in resp.body and "Epcot" in resp.body   # park dropdowns


async def test_post_applies_settings_and_rebuilds(mock_http_client, settings_factory):
    app = ThemeParkApp(http_client=mock_http_client, settings=settings_factory(), enable_web=True)
    await app.service.initialize()
    handler, adapter = _handler(app)

    body = ("park_1=6&sort_mode=min_wait&scroll_speed=Fast&brightness_scale=0.6"
            "&skip_meet=on&default_color=%23112233&domain_name=mybox")
    resp = handler.route_settings(MockRequest("POST", "/settings", "", body, adapter))
    assert resp.status == 200                            # redirect/confirmation page

    sm = app.settings
    assert sm.get("sort_mode") == "min_wait"
    assert sm.get("scroll_speed") == "Fast"
    assert sm.get("skip_meet") is True                   # checkbox present
    assert sm.get("group_by_park") is False              # checkbox absent -> False
    assert sm.get("selected_park_ids") == [6]
    assert sm.get("default_color") == "0x112233"         # #rrggbb -> 0xrrggbb
    assert sm.get("domain_name") == "mybox"
    # selected park resolved + a content queue was (re)built
    assert app.service.park_list.selected_parks[0].id == 6
    assert app.content_queue.get_content_count() > 0


async def test_server_starts_and_stops(mock_http_client, settings_factory):
    app = ThemeParkApp(http_client=mock_http_client, settings=settings_factory(), enable_web=True)
    server = await app.create_web_server()
    assert server is not None
    ok = await server.start(host="127.0.0.1", port=8099)
    try:
        assert ok is True and server.is_running
    finally:
        await server.stop()
