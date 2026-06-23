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
)

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
    assert "Magic Kingdom" in html and "Epcot" in html  # park dropdowns


async def test_apply_settings_persists_and_rebuilds(mock_http_client, settings_factory):
    app = await _app(mock_http_client, settings_factory)
    apply_settings(app, {
        "park_1": "6", "sort_mode": "min_wait", "scroll_speed": "Fast",
        "brightness_scale": "0.6", "skip_meet": "on",
        "default_color": "#112233", "domain_name": "mybox",
    })
    sm = app.settings
    assert sm.get("sort_mode") == "min_wait"
    assert sm.get("scroll_speed") == "Fast"
    assert sm.get("skip_meet") is True       # checkbox present
    assert sm.get("group_by_park") is False  # checkbox absent -> False
    assert sm.get("selected_park_ids") == [6]
    assert sm.get("default_color") == "0x112233"  # #rrggbb -> 0xrrggbb
    assert sm.get("domain_name") == "mybox"
    assert app.service.park_list.selected_parks[0].id == 6
    assert app.content_queue.get_content_count() > 0


# --------------------------------------------------------------------------- #
# End-to-end HTTP tests — the real server over the stdlib socket pool
# --------------------------------------------------------------------------- #
async def test_get_index_over_http(mock_http_client, settings_factory):
    app = await _app(mock_http_client, settings_factory)
    with _RunningServer(app, _PORT) as srv:
        status, body = _get(srv.base, "/")
        assert status == 200
        assert "ThemeParkWaits" in body and "Magic Kingdom" in body


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
            srv.base, "/settings", "park_1=6&scroll_speed=Fast&sort_mode=max_wait", follow=False)
        assert code == 303
        assert location == "/"
    sm = app.settings
    assert sm.get("scroll_speed") == "Fast"
    assert sm.get("sort_mode") == "max_wait"
    assert sm.get("selected_park_ids") == [6]


async def test_post_update_is_handled(mock_http_client, settings_factory):
    app = await _app(mock_http_client, settings_factory)
    with _RunningServer(app, _PORT + 3) as srv:
        code, location = _post(srv.base, "/update", "", follow=False)
        assert code == 303 and location == "/"


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
