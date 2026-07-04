# Copyright (c) 2024-2026 Michael Czeiszperger
"""T023-T025 — config web UI on native adafruit_httpserver.

The config server is now plain ``adafruit_httpserver`` (no library web layer).
Because that server runs on desktop CPython with the stdlib ``socket`` module as
its pool, these tests exercise the REAL server over REAL HTTP round-trips on the
loopback interface — the same code path that runs on the Matrix Portal S3 (only
the socket pool differs). That is the whole point of going native: the simulator
test and the device share one server implementation.
"""
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from src.app import ThemeParkApp
from src.web.config_server import (
    ThemeParkConfigServer,
    apply_settings,
    render_page,
    _schedule_refresh,
)
from tests.conftest import MAGIC_KINGDOM_ID

# Each test gets its own loopback port (avoids TIME_WAIT rebind races between
# sequentially-started servers). The client always targets the server's own port.
_PORT = 8137


async def _app(mock_http_client, settings_factory, **overrides):
    app = ThemeParkApp(http_client=mock_http_client,
                       settings=settings_factory(**overrides), enable_web=True)
    await app.service.initialize()  # fetch the (mock) park list
    return app


class _RunningServer:
    """Context manager: start the native server + poll it on a background thread.

    Exposes ``.base`` (e.g. ``http://127.0.0.1:8138``) so the client always hits
    THIS server's port.
    """

    def __init__(self, app, port):
        self.server = ThemeParkConfigServer(app, static_dir="src/www",
                                            socket_pool=socket, host="127.0.0.1", port=port)
        self.base = "http://127.0.0.1:%d" % port
        self._stop = False
        self._thread = None

    def __enter__(self):
        # Build + bind the underlying adafruit Server synchronously.
        self.server._server = self.server._build_server()
        self.server._server.start("127.0.0.1", self.server.port)
        self.server.is_running = True

        def _serve():
            while not self._stop:
                try:
                    self.server._server.poll()
                except Exception:
                    pass
                time.sleep(0.005)

        self._thread = threading.Thread(target=_serve, daemon=True)
        self._thread.start()
        time.sleep(0.1)  # let the listener settle
        return self

    def __exit__(self, *exc):
        self._stop = True
        if self._thread:
            self._thread.join(timeout=1)
        try:
            self.server._server.stop()
        except Exception:
            pass


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=3) as r:
        return r.status, r.read().decode("utf-8", "replace")


def _post_body(base, path, data):
    """POST and return (status, decoded body) — for routes that answer inline."""
    import urllib.request
    req = urllib.request.Request(base + path, data=data.encode(), method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read().decode()


def _post(base, path, body, follow=True):
    """POST urlencoded ``body``. Returns (status, final_url). When follow=False,
    returns the redirect's status code + Location header instead of following it."""
    req = urllib.request.Request(base + path, data=body.encode(), method="POST")

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=3) as r:
            return r.status, r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location")


# --------------------------------------------------------------------------- #
# Pure-function tests (no socket) — render + apply
# --------------------------------------------------------------------------- #
async def test_render_page_lists_parks(mock_http_client, settings_factory):
    app = await _app(mock_http_client, settings_factory)
    html = render_page(app)
    assert "ThemeParkWaits" in html
    assert "Magic Kingdom Park" in html and "EPCOT" in html  # park dropdowns
    assert '<option value="%s"' % MAGIC_KINGDOM_ID in html   # UUID option value


async def test_render_page_disambiguates_duplicate_park_names(mock_http_client, settings_factory):
    """Two parks named 'Disneyland Park' must be distinguishable in the dropdown
    by their destination (FR-005a)."""
    app = await _app(mock_http_client, settings_factory)
    html = render_page(app)
    assert "Disneyland Park - Disneyland Paris" in html
    assert "Disneyland Park - Disneyland Resort" in html


async def test_render_page_uses_color_dropdown(mock_http_client, settings_factory):
    """Color fields are a curated dropdown matched to the panel gamut, not a free
    24-bit <input type=color>; a legacy free-picked value pre-selects the nearest."""
    app = await _app(mock_http_client, settings_factory)
    app.settings.set("ride_name_color", "0xff2600")   # legacy free-picked red
    html = render_page(app)
    assert 'type="color"' not in html                 # no free picker
    assert 'name="ride_name_color"' in html
    assert '<option value="0xff0000"' in html          # palette options present
    # 0xff2600 is nearest to Red in the palette, so Red is preselected
    assert '<option value="0xff0000" selected>Red</option>' in html


async def test_render_page_has_wait_effect_dropdown(mock_http_client, settings_factory):
    """The wait-number reveal effect is a dropdown, pre-selected to the saved value."""
    app = await _app(mock_http_client, settings_factory)
    app.settings.set("wait_time_effect", "Swarm")
    html = render_page(app)
    assert 'name="wait_time_effect"' in html
    assert "<option>Rain</option>" in html              # all choices present
    assert "<option selected>Swarm</option>" in html    # saved value preselected


async def test_apply_settings_persists_and_rebuilds(mock_http_client, settings_factory):
    app = await _app(mock_http_client, settings_factory)
    apply_settings(app, {
        "park_1": MAGIC_KINGDOM_ID, "sort_mode": "min_wait", "scroll_speed": "Fast",
        "wait_time_effect": "None",
        "brightness_scale": "0.6", "skip_meet": "on",
        "default_color": "#112233", "domain_name": "mybox",
    })
    sm = app.settings
    assert sm.get("sort_mode") == "min_wait"
    assert sm.get("scroll_speed") == "Fast"
    assert sm.get("wait_time_effect") == "None"
    assert sm.get("skip_meet") is True       # checkbox present
    assert sm.get("group_by_park") is False  # checkbox absent -> False
    assert sm.get("selected_park_ids") == [MAGIC_KINGDOM_ID]   # UUID string stored
    assert sm.get("default_color") == "0x112233"  # #rrggbb -> 0xrrggbb
    assert sm.get("domain_name") == "mybox"
    assert app.service.park_list.selected_parks[0].id == MAGIC_KINGDOM_ID
    assert app.content_queue.get_content_count() > 0


async def test_apply_settings_can_clear_all_parks(mock_http_client, settings_factory):
    """Submitting the form with every park dropdown set to '(none)' clears the
    selection — the user must be able to deselect all parks."""
    app = await _app(mock_http_client, settings_factory)
    apply_settings(app, {"park_1": MAGIC_KINGDOM_ID})
    assert app.settings.get("selected_park_ids") == [MAGIC_KINGDOM_ID]
    # Now all four dropdowns submitted empty.
    apply_settings(app, {"park_1": "", "park_2": "", "park_3": "", "park_4": ""})
    assert app.settings.get("selected_park_ids") == []
    assert app.settings.get("current_park_id") == ""


# --------------------------------------------------------------------------- #
# End-to-end HTTP tests — the real server over the stdlib socket pool
# --------------------------------------------------------------------------- #
async def test_get_index_over_http(mock_http_client, settings_factory):
    app = await _app(mock_http_client, settings_factory)
    with _RunningServer(app, _PORT) as srv:
        status, body = _get(srv.base, "/")
        assert status == 200
        assert "ThemeParkWaits" in body and "Magic Kingdom Park" in body


async def test_get_static_css_over_http(mock_http_client, settings_factory):
    app = await _app(mock_http_client, settings_factory)
    with _RunningServer(app, _PORT + 1) as srv:
        # /style.css is NOT a route — served from src/www by root_path.
        status, _ = _get(srv.base, "/style.css")
        assert status == 200


async def test_post_settings_redirects_and_applies(mock_http_client, settings_factory):
    app = await _app(mock_http_client, settings_factory)
    with _RunningServer(app, _PORT + 2) as srv:
        # Don't follow the redirect: assert it's a clean 303 -> "/".
        code, location = _post(
            srv.base, "/settings",
            "park_1=%s&scroll_speed=Fast&sort_mode=max_wait" % MAGIC_KINGDOM_ID, follow=False)
        assert code == 303
        assert location == "/"
    sm = app.settings
    assert sm.get("scroll_speed") == "Fast"
    assert sm.get("sort_mode") == "max_wait"
    assert sm.get("selected_park_ids") == [MAGIC_KINGDOM_ID]


async def test_post_url_encoded_color_is_decoded(mock_http_client, settings_factory):
    """A browser submits the color '#ffffff' as '%23ffffff' in the form body. The
    server must URL-decode it so it's stored as '0xffffff'. An undecoded
    '%23ffffff' later raises int(color, 16) in build_content_queue, which clears
    the queue first — blanking the display (the frozen-screen bug). This test
    posts over real HTTP (the direct apply_settings tests bypass the form parser).
    """
    app = await _app(mock_http_client, settings_factory)
    with _RunningServer(app, _PORT + 6) as srv:
        code, _ = _post(
            srv.base, "/settings",
            "park_1=%s&default_color=%%23ffffff&ride_name_color=%%2300aaff" % MAGIC_KINGDOM_ID,
            follow=False)
        assert code == 303
    sm = app.settings
    assert sm.get("default_color") == "0xffffff"   # %23ffffff -> #ffffff -> 0xffffff
    assert sm.get("ride_name_color") == "0x00aaff"
    # Queue rebuilt without raising (the bug left it empty -> frozen screen).
    assert app.content_queue.get_content_count() > 0


async def test_post_update_reports_outcome(mock_http_client, settings_factory):
    """POST /update answers with the OTA outcome (200 + reason), not a blind
    redirect — failures used to be serial-only and undiagnosable in the field."""
    app = await _app(mock_http_client, settings_factory)
    with _RunningServer(app, _PORT + 3) as srv:
        code, body = _post_body(srv.base, "/update", "")
        assert code == 200
        assert ("No update installed" in body) or ("Update staged" in body)


async def test_save_settings_server_survives_and_redirects(mock_http_client, settings_factory):
    """Full browser save cycle: POST /settings → follow 303 → GET / returns 200.

    The existing POST test uses follow=False and only verifies the 303 itself.
    This test follows the redirect the way a real browser does, exercising the
    second TCP connection (GET /) that the server must handle after apply_settings
    runs.  It would have caught the old hang: if apply_settings crashes the server
    or poll() never handles the follow-up GET, urllib times out and the assert
    fails.
    """
    app = await _app(mock_http_client, settings_factory)
    with _RunningServer(app, _PORT + 5) as srv:
        # follow=True (default): urllib follows 303 → opens second connection → GET /
        final_code, final_url = _post(
            srv.base, "/settings",
            "park_1=%s&scroll_speed=Fast&sort_mode=max_wait" % MAGIC_KINGDOM_ID,
        )
        assert final_code == 200, "redirect target returned %d (server may have crashed)" % final_code
        assert final_url.rstrip("/").endswith(str(_PORT + 5)), "landed on unexpected URL: %s" % final_url
        # Server is still answering fresh requests after the save
        status, body = _get(srv.base, "/")
        assert status == 200
        assert "ThemeParkWaits" in body
    # Settings were persisted
    sm = app.settings
    assert sm.get("scroll_speed") == "Fast"
    assert sm.get("sort_mode") == "max_wait"
    assert sm.get("selected_park_ids") == [MAGIC_KINGDOM_ID]


async def test_settings_change_schedules_prompt_refresh(mock_http_client, settings_factory):
    """A settings change must trigger a prompt data refresh. The old `update_needed`
    flag was set but never consumed, so a newly-selected park showed no wait times
    until the next ~5-min update tick. _schedule_refresh runs update_data() on the
    loop (fire-and-forget), and is a no-op when no loop is running."""
    import asyncio
    app = await _app(mock_http_client, settings_factory)
    ran = []

    async def fake_update():
        ran.append(True)

    app.update_data = fake_update
    _schedule_refresh(app)
    for _ in range(3):
        await asyncio.sleep(0)   # let the scheduled task run
    assert ran == [True], "settings change should schedule update_data()"


# --------------------------------------------------------------------------- #
# create_web_server wiring + lifecycle
# --------------------------------------------------------------------------- #
async def test_create_web_server_returns_native_server(mock_http_client, settings_factory):
    app = ThemeParkApp(http_client=mock_http_client, settings=settings_factory(), enable_web=True)
    server = await app.create_web_server()
    assert isinstance(server, ThemeParkConfigServer)
    ok = await server.start(host="127.0.0.1", port=_PORT + 4)
    try:
        assert ok is True and server.is_running
        assert server.get_server_url().startswith("http://")
    finally:
        await server.stop()
        assert server.is_running is False
