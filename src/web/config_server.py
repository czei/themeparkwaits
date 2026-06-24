"""Configuration web UI for ThemeParkWaits — native ``adafruit_httpserver``.

This used to run on the library's web abstraction (``SLDKWebServer`` +
``ServerAdapter`` + ``MockRequest``/``MockResponse`` + a ``@route`` registry).
That layer hid SIX CircuitPython-only traps the CPython simulator could never
catch (``func._route_info``/``func.__name__`` attribute assignment, an
``__init_subclass__`` that CircuitPython never calls, adafruit_httpserver v1→v4
API drift, ``os.path``, ``str.title()``). ``adafruit_httpserver`` is itself
cross-platform — it runs on desktop CPython with the stdlib ``socket`` module as
its pool — so the abstraction was redundant *and* it masked the API drift.

So the config UI now talks to ``adafruit_httpserver`` directly. The SAME server
object runs on desktop and on the Matrix Portal S3; the only platform difference
is where the socket pool comes from::

    pool = socketpool.SocketPool(wifi.radio)   # CircuitPython
    pool = socket                              # desktop (stdlib module)

Routes (per contracts/web-config-routes.md): GET ``/`` (the form), GET/POST
``/settings`` (POST applies + 303-redirects to ``/``), POST ``/update`` (schedule
OTA), and static files (``/style.css`` …) served from ``src/www`` automatically.

POST ``/settings`` applies to the ``SettingsManager`` and rebuilds the display
content queue (no network fetch — FR-004), then returns a lightweight HTTP 303
redirect to ``/`` (NOT a heavy styled meta-refresh page — that was the likely
cause of the on-device POST freeze).

Note: adafruit ``FormData`` exposes one value per field, so multi-park selection
uses four distinct ``park_1..park_4`` dropdowns rather than a repeated field.

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

import sys

from scrollkit.utils.url_utils import url_decode
from src.ui.content_builder import build_content_queue

SORT_MODES = ("alphabetical", "max_wait", "min_wait")
SCROLL_SPEEDS = ("Slow", "Medium", "Fast")
MAX_PARKS = 4

# Curated colors that stay visually distinct on the bit_depth=4 panel (16 levels
# per channel -> 4096 colors, not the 16.7M a free <input type=color> implied).
# A dropdown of these is honest about the gamut: what you pick is what the panel
# can actually show. Values are the app's canonical 0xRRGGBB strings (stored
# as-is). Channels stick to 0x00/0x80/0xc0/0xff so they survive 4-bit truncation.
COLOR_PALETTE = (
    ("White", "0xffffff"),
    ("Red", "0xff0000"),
    ("Orange", "0xff8000"),
    ("Yellow", "0xffff00"),
    ("Lime", "0x80ff00"),
    ("Green", "0x00ff00"),
    ("Cyan", "0x00ffff"),
    ("Blue", "0x0000ff"),
    ("Purple", "0x8000ff"),
    ("Magenta", "0xff00ff"),
    ("Pink", "0xff80c0"),
    ("Gray", "0x808080"),
)

# adafruit_httpserver wants (code, text) tuples for non-default statuses. 303 makes
# the browser re-GET "/" with a GET (POST-redirect-GET), so a refresh won't re-POST.
_SEE_OTHER = (303, "See Other")
# Poll cadence for the serve loop. A small yield keeps the config UI responsive
# (<~20 ms) without busy-spinning the single asyncio loop the display shares; the
# old library adapter throttled at 0.1 s (sluggish) — this is well under that.
_POLL_INTERVAL = 0.02


def _is_circuitpython() -> bool:
    return bool(getattr(sys, "implementation", None)) and sys.implementation.name == "circuitpython"


def _color_to_int(value) -> int:
    """Coerce '0xRRGGBB'/'#RRGGBB'/'RRGGBB'/int to an int (white on failure)."""
    try:
        if isinstance(value, str):
            s = value.strip()
            if s.startswith("#"):
                s = s[1:]
            return int(s, 16)
        return int(value)
    except (TypeError, ValueError):
        return 0xFFFFFF


def _nearest_palette_value(current) -> str:
    """The COLOR_PALETTE entry closest (RGB distance) to ``current``.

    Lets a legacy free-picked color (e.g. an old '0xff2600') pre-select a sensible
    dropdown option instead of falling off the list.
    """
    cur = _color_to_int(current)
    cr, cg, cb = (cur >> 16) & 0xFF, (cur >> 8) & 0xFF, cur & 0xFF
    best, best_d = COLOR_PALETTE[0][1], None
    for _label, hexv in COLOR_PALETTE:
        v = int(hexv, 16)
        d = (((v >> 16) & 0xFF) - cr) ** 2 + (((v >> 8) & 0xFF) - cg) ** 2 + ((v & 0xFF) - cb) ** 2
        if best_d is None or d < best_d:
            best, best_d = hexv, d
    return best


def _html_to_hex(value) -> str:
    """'#0000ff' -> '0x0000ff' for storage (matches the app's color format)."""
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        return "0x" + value[1:].lower()
    return value


def _esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def SettingsLabel(key):
    """Pretty label for a settings key ('sort_mode' -> 'Sort Mode')."""
    return " ".join(w[:1].upper() + w[1:] for w in str(key).replace("_", " ").split())


def _params(request) -> dict:
    """Flatten an adafruit ``Request`` (form body + query string) to a plain dict.

    ``apply_settings`` treats params as a dict (``key in params``, ``.get``,
    ``params[key]``) — adafruit ``FormData``/``QueryParams`` expose ``keys()`` +
    ``get()`` but not ``__contains__``, so normalise here. Values are coerced to
    ``str`` (urlencoded forms are text, but ``get`` can return ``bytes``).
    """
    out = {}
    for source in (getattr(request, "form_data", None), getattr(request, "query_params", None)):
        if not source:
            continue
        try:
            keys = source.keys()
        except Exception:
            continue
        for k in keys:
            if k in out:
                continue
            v = source.get(k)
            if isinstance(v, bytes):
                v = v.decode("utf-8", "replace")
            if v is None:
                v = ""
            elif isinstance(v, str):
                # adafruit_httpserver does NOT URL-decode form bodies, so a color
                # '#ffffff' arrives as '%23ffffff' and 'My Trip' as 'My+Trip'.
                # Decode here (idempotent for plain values) so apply_settings sees
                # real values — otherwise '%23ffffff' is stored and later crashes
                # int(color, 16) in build_content_queue, blanking the display.
                v = url_decode(v)
            out[k] = v
    return out


# --------------------------------------------------------------------------- #
# Settings persistence (POST /settings)
# --------------------------------------------------------------------------- #
def apply_settings(app, params) -> None:
    """Apply POSTed form values to the SettingsManager + rebuild content (FR-004)."""
    sm = app.settings
    svc = getattr(app, "service", None)

    # Park selection (park_1..park_4 -> selected_park_ids).
    ids = []
    for i in range(1, MAX_PARKS + 1):
        raw = params.get("park_%d" % i, "").strip()
        if raw:
            try:
                pid = int(raw)
            except ValueError:
                continue
            if pid > 0 and pid not in ids:
                ids.append(pid)
    if ids:
        sm.set("selected_park_ids", ids)
        sm.set("current_park_id", ids[0])

    # Scalars.
    for key in ("sort_mode", "scroll_speed", "domain_name"):
        if key in params and params[key]:
            sm.set(key, params[key])
    if "brightness_scale" in params:
        sm.set("brightness_scale", params["brightness_scale"])
    for key in ("default_color", "ride_name_color", "ride_wait_time_color"):
        if key in params:
            sm.set(key, _html_to_hex(params[key]))

    # Booleans: an unchecked box is simply absent from the form.
    for key in ("group_by_park", "skip_closed", "skip_meet"):
        sm.set(key, key in params)

    # Vacation.
    if "next_visit" in params:
        sm.set("next_visit", params.get("next_visit", ""))
        for k in ("next_visit_year", "next_visit_month", "next_visit_day"):
            try:
                sm.set(k, int(params.get(k, 0)))
            except (TypeError, ValueError):
                pass

    sm.save_settings()

    # Reflect changes immediately (no network fetch — FR-004). A newly-selected
    # park has no ride data yet, so this rebuild shows no wait times; the POST
    # handler schedules a prompt async refresh (_schedule_refresh) to fetch them.
    try:
        if svc and svc.park_list is not None:
            svc.park_list.load_settings(sm)
        if svc:
            svc.vacation.load_settings(sm)
        build_content_queue(app.content_queue, svc.park_list if svc else None,
                            sm, svc.vacation if svc else None)
    except Exception as e:
        print("apply settings rebuild failed:", e)


def _schedule_refresh(app) -> None:
    """Fire-and-forget a data refresh on the running event loop.

    A settings change (notably a new park, which has no ride data yet) rebuilds
    the queue immediately but with no wait times; without this the times only
    appear on the next ``update_data()`` tick — up to ``update_interval`` seconds
    later. Scheduling ``update_data()`` here fetches the new park and rebuilds
    within a second or two. It does NOT block the POST handler's redirect
    (FR-004), and it is a no-op when no event loop is running (unit tests calling
    ``apply_settings`` directly, or the threaded test server).
    """
    update = getattr(app, "update_data", None)
    if update is None:
        return
    try:
        import asyncio
        asyncio.get_running_loop().create_task(update())
    except RuntimeError:
        pass  # no running event loop in this context
    except Exception as e:
        print("schedule refresh failed:", e)


def schedule_update(app) -> bool:
    """Ask the OTA glue to check + stage an update (POST /update). Never raises."""
    ota = getattr(app, "ota", None)
    if ota is not None and hasattr(ota, "schedule_update"):
        try:
            return bool(ota.schedule_update())
        except Exception:
            return False
    return False


# --------------------------------------------------------------------------- #
# Page rendering (GET / and GET /settings)
# --------------------------------------------------------------------------- #
def render_page(app) -> str:
    """Render the settings form, pre-filled, with the live park list."""
    sm = app.settings
    svc = getattr(app, "service", None)
    parks = sorted(getattr(getattr(svc, "park_list", None), "park_list", []) or [],
                   key=lambda p: p.name)
    selected = list(sm.get("selected_park_ids", []) or [])

    def park_select(i):
        cur = selected[i - 1] if i - 1 < len(selected) else None
        opts = ['<option value="">(none)</option>']
        for p in parks:
            sel = " selected" if cur == p.id else ""
            opts.append('<option value="%d"%s>%s</option>' % (p.id, sel, _esc(p.name)))
        return ('<div class="form-group"><label>Park %d</label>'
                '<select class="form-control" name="park_%d">%s</select></div>'
                % (i, i, "".join(opts)))

    def select(name, options, current):
        opts = []
        for o in options:
            sel = " selected" if o == current else ""
            opts.append('<option%s>%s</option>' % (sel, _esc(o)))
        return ('<div class="form-group"><label>%s</label>'
                '<select class="form-control" name="%s">%s</select></div>'
                % (_esc(SettingsLabel(name)), name, "".join(opts)))

    def checkbox(name):
        chk = " checked" if sm.get(name, False) else ""
        return ('<div class="form-group"><label>'
                '<input type="checkbox" name="%s"%s> %s</label></div>'
                % (name, chk, _esc(SettingsLabel(name))))

    def color_select(name):
        # Dropdown of panel-distinct colors (the panel can't show a free 24-bit
        # pick). Pre-select the palette entry nearest the stored value.
        current = _nearest_palette_value(sm.get(name, "0xffffff"))
        opts = []
        for label, hexv in COLOR_PALETTE:
            sel = " selected" if hexv == current else ""
            opts.append('<option value="%s"%s>%s</option>' % (hexv, sel, _esc(label)))
        return ('<div class="form-group"><label>%s</label>'
                '<select class="form-control" name="%s">%s</select></div>'
                % (_esc(SettingsLabel(name)), name, "".join(opts)))

    park_html = "".join(park_select(i) for i in range(1, MAX_PARKS + 1))
    try:
        brightness = float(sm.get("brightness_scale", "0.5"))
    except (TypeError, ValueError):
        brightness = 0.5

    return PAGE_TEMPLATE.format(
        park_selectors=park_html,
        sort=select("sort_mode", SORT_MODES, sm.get("sort_mode", "alphabetical")),
        scroll=select("scroll_speed", SCROLL_SPEEDS, sm.get("scroll_speed", "Medium")),
        brightness=brightness,
        group=checkbox("group_by_park"),
        skip_closed=checkbox("skip_closed"),
        skip_meet=checkbox("skip_meet"),
        default_color=color_select("default_color"),
        name_color=color_select("ride_name_color"),
        wait_color=color_select("ride_wait_time_color"),
        domain=_esc(sm.get("domain_name", "themeparkwaits")),
        vac_name=_esc(sm.get("next_visit", "") or ""),
        vac_year=_esc(sm.get("next_visit_year", "") or ""),
        vac_month=_esc(sm.get("next_visit_month", "") or ""),
        vac_day=_esc(sm.get("next_visit_day", "") or ""),
    )


# --------------------------------------------------------------------------- #
# The server — native adafruit_httpserver, same object on desktop + device
# --------------------------------------------------------------------------- #
class ThemeParkConfigServer:
    """Config web server on ``adafruit_httpserver`` (desktop + CircuitPython).

    Implements the ``ScrollKitApp`` web contract: ``await start()`` (truthy on
    success), ``get_server_url()``, ``await run_forever()`` (poll loop), and
    ``await stop()``. The framework adds ``run_forever`` as an asyncio task, so
    the poll loop cooperates with the display + data loops on one event loop.
    """

    def __init__(self, app, *, static_dir="src/www", socket_pool=None,
                 host="0.0.0.0", port=None):
        self.app = app
        self.static_dir = static_dir
        self.socket_pool = socket_pool
        self.host = host
        # Device serves on :80 so raw-IP and <domain>.local work without a port;
        # desktop uses :8080 (the simulator's established config port).
        self.port = port if port is not None else (80 if _is_circuitpython() else 8080)
        self.is_running = False
        self._server = None

    def _build_server(self):
        from adafruit_httpserver import Server, Response, Redirect, GET, POST

        pool = self.socket_pool
        if pool is None:
            import socket as _socket  # stdlib module IS a valid adafruit pool on desktop
            pool = _socket

        server = Server(pool, self.static_dir, debug=False)
        app = self.app

        @server.route("/")
        def _index(request):  # noqa: ANN001
            return Response(request, render_page(app), content_type="text/html")

        @server.route("/settings", [GET, POST])
        def _settings(request):  # noqa: ANN001
            if request.method == POST:
                try:
                    apply_settings(app, _params(request))
                except Exception as e:  # never 500 the form on a bad apply
                    print("apply_settings failed:", e)
                # Fetch a newly-selected park now (async, non-blocking) so its wait
                # times show within seconds instead of at the next update tick.
                _schedule_refresh(app)
                return Redirect(request, "/", status=_SEE_OTHER)
            return Response(request, render_page(app), content_type="text/html")

        @server.route("/update", [POST])
        def _update(request):  # noqa: ANN001
            schedule_update(app)
            return Redirect(request, "/", status=_SEE_OTHER)

        return server

    async def start(self, host=None, port=None) -> bool:
        try:
            if host is not None:
                self.host = host
            if port is not None:
                self.port = port
            self._server = self._build_server()
            self._server.start(self.host, self.port)
            self.is_running = True
            return True
        except Exception as e:
            print("config server start failed:", e)
            self.is_running = False
            return False

    def get_server_url(self) -> str:
        host = self.host
        if _is_circuitpython():
            try:
                import wifi
                host = str(wifi.radio.ipv4_address)
            except Exception:
                pass
        return "http://%s:%d/" % (host, self.port)

    async def run_forever(self) -> None:
        import asyncio
        while self.is_running:
            try:
                self._server.poll()
            except Exception as e:  # a malformed request must not kill the loop
                print("config server poll error:", e)
            await asyncio.sleep(_POLL_INTERVAL)

    async def stop(self) -> None:
        self.is_running = False
        try:
            if self._server is not None:
                self._server.stop()
        except Exception:
            pass


PAGE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ThemeParkWaits</title><link rel="stylesheet" href="/style.css"></head>
<body><div class="container">
<div class="header"><h1>ThemeParkWaits</h1></div>
<div class="content">
<form method="POST" action="/settings">
<h3>Parks (up to 4)</h3>
{park_selectors}
<h3>Display</h3>
{sort}
{scroll}
<div class="form-group"><label>Brightness</label>
<input class="form-control" type="range" name="brightness_scale" min="0" max="1" step="0.05" value="{brightness}"></div>
{group}
{skip_closed}
{skip_meet}
{default_color}
{name_color}
{wait_color}
<h3>Network</h3>
<div class="form-group"><label>Domain Name (.local)</label>
<input class="form-control" type="text" name="domain_name" value="{domain}"></div>
<h3>Vacation Countdown</h3>
<div class="form-group"><label>Park Name</label>
<input class="form-control" type="text" name="next_visit" value="{vac_name}"></div>
<div class="form-group"><label>Year</label>
<input class="form-control" type="number" name="next_visit_year" value="{vac_year}"></div>
<div class="form-group"><label>Month</label>
<input class="form-control" type="number" name="next_visit_month" value="{vac_month}"></div>
<div class="form-group"><label>Day</label>
<input class="form-control" type="number" name="next_visit_day" value="{vac_day}"></div>
<button class="btn" type="submit">Save</button>
</form>
<form method="POST" action="/update" style="margin-top:20px">
<button class="btn" type="submit">Check for Update</button>
</form>
</div></div></body></html>
"""
