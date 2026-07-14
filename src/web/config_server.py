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

Copyright (c) 2024-2026 Michael Czeiszperger
"""
from __future__ import annotations

import sys

from scrollkit.utils.url_utils import url_decode
from scrollkit.utils.error_handler import ErrorHandler
from src.ui.content_builder import build_content_queue

# Persist OTA install outcomes: error() writes to error_log in BOTH modes (info is
# console-only in PRODUCTION), so a silent download failure leaves a readable reason.
logger = ErrorHandler("error_log")

SORT_MODES = ("alphabetical", "max_wait", "min_wait")
SCROLL_SPEEDS = ("Slow", "Medium", "Fast")
# Wait-number coloring: "severity" colors by wait length (green->red); "fixed"
# uses the Ride Wait Time Color setting.
WAIT_COLOR_MODES = ("severity", "fixed")
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

    # Park selection (park_1..park_4 -> selected_park_ids). themeparks.wiki ids are
    # UUID strings, so store them verbatim (no int() cast). Only touch the selection
    # when the form actually submitted park fields, but then honor an empty choice so
    # the user CAN clear all parks (every "(none)" dropdown -> selected_park_ids=[]).
    if any(("park_%d" % i) in params for i in range(1, MAX_PARKS + 1)):
        ids = []
        for i in range(1, MAX_PARKS + 1):
            raw = params.get("park_%d" % i, "").strip()
            if raw and raw not in ids:
                ids.append(raw)
        sm.set("selected_park_ids", ids)
        sm.set("current_park_id", ids[0] if ids else "")

    # Scalars.
    for key in ("sort_mode", "scroll_speed", "wait_color_mode", "domain_name"):
        if key in params and params[key]:
            sm.set(key, params[key])
    if "brightness_scale" in params:
        sm.set("brightness_scale", params["brightness_scale"])
    for key in ("default_color", "ride_name_color", "ride_wait_time_color"):
        if key in params:
            sm.set(key, _html_to_hex(params[key]))

    # Booleans: an unchecked box is simply absent from the form.
    for key in ("group_by_park", "skip_closed", "skip_meet", "ride_name_gradient"):
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


def _reclaim_display_mem(app) -> None:
    """Free the on-screen ride's intro overlay (its writable bitmap — e.g. the Big
    Thunder goat) + gc before an OTA GET. The manifest/file fetches fail with the
    same MemoryError-on-TLS-socket-allocation as the park-data fetch, starved by that
    bitmap. The data path fixed it by yielding to the display loop's async teardown,
    but this runs synchronously from the web handler and can't yield — so detach the
    current content's intro directly (a sync op) and double-gc for the handshake."""
    try:
        cq = getattr(app, "content_queue", None)
        cur = cq.get_current_content() if cq is not None else None
        detach = getattr(cur, "_detach_intro", None)
        if detach is not None:
            detach()
        import gc
        gc.collect()
        gc.collect()   # second pass frees what the first made collectable
    except Exception as e:
        print("OTA pre-reclaim skipped:", e)


def check_update(app):
    """POST /update: CHECK ONLY. Does a newer release exist? No download — the user
    decides whether to install (the old fused check+stage auto-installed with no
    consent). Returns ``(available: bool, version: str|None, message: str)``; never
    raises. Failures surface to the browser (OTA errors were serial-only before)."""
    ota = getattr(app, "ota", None)
    if ota is None or not hasattr(ota, "check_update"):
        return (False, None, "OTA unavailable: %s"
                % (getattr(app, "ota_error", None) or "not constructed"))
    _reclaim_display_mem(app)          # free heap for the manifest GET's TLS socket
    try:
        return ota.check_update()
    except Exception as e:
        # Same MemoryError-on-TLS-socket class as the data fetch; attach a heap note
        # so a repeat failure is diagnosable from the browser without a serial cable.
        try:
            from src.api.theme_park_service import _heap_note
            hn = _heap_note()
        except Exception:
            hn = ""
        return (False, None, "check failed: %s%s"
                % (e, (" [heap: " + hn + "]") if hn else ""))


def install_update(app) -> bool:
    """POST /install: start the user-confirmed install and return immediately so the
    'update started' page flushes FIRST. A background task then paints
    'Updating / DO NOT / UNPLUG!' on the panel, downloads the staged files (blocking
    — the message holds on screen through it), and reboots so the next boot's
    install_pending() applies them. Returns whether the task was scheduled."""
    import asyncio
    ota = getattr(app, "ota", None)
    if ota is None or not hasattr(ota, "stage_update"):
        return False

    async def _run():
        await asyncio.sleep(0.4)               # let the HTTP response flush first
        try:
            await ota.show_updating()          # "Updating / DO NOT / UNPLUG!" on the panel
        except Exception as e:
            print("show_updating failed:", e)
        _reclaim_display_mem(app)              # free heap for the download GETs
        staged = False
        try:
            staged = bool(ota.stage_update())  # blocking download; the panel message holds
        except Exception as e:
            print("OTA stage failed:", e)
        if staged:
            logger.error(None, "OTA: staged update, rebooting to apply")
            _schedule_reboot(app, delay=0.4)   # reboot -> install_pending applies + reboots
        else:
            # PERSIST why it didn't stage (last_error is otherwise invisible — not on
            # the web page or serial), so a silent download failure is diagnosable.
            logger.error(None, "OTA: install did NOT stage: %s"
                         % (getattr(ota, "last_error", None) or "unknown"))
            try:
                await ota.show_failed()
            except Exception:
                pass

    try:
        asyncio.get_running_loop().create_task(_run())
        return True
    except RuntimeError:
        return False                           # no running loop (tests)


def _schedule_reboot(app, delay=2.0):
    """Reboot shortly AFTER the response flushes, so a staged OTA installs on the
    next boot (the library contract: schedule_update stages, the caller reboots)."""
    import asyncio

    async def _reboot():
        await asyncio.sleep(delay)
        try:
            import supervisor
            supervisor.reload()
        except Exception:
            print("reboot skipped (desktop) — staged OTA would install on next boot")
    try:
        asyncio.get_running_loop().create_task(_reboot())
    except RuntimeError:
        pass  # no running loop (tests) — staged update installs on next manual boot


# --------------------------------------------------------------------------- #
# Page rendering (GET / and GET /settings)
# --------------------------------------------------------------------------- #
def _read_version() -> str:
    """The shipped app version (src/.version, stamped by deploy/OTA)."""
    try:
        with open("src/.version") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def _diagnostics_html(app) -> str:
    """Read-only health panel so a field user can see WHY the device misbehaved
    (last reset reason, last crash, fetch failures) without a serial cable — the
    gap that made the previous black-screen failures undiagnosable."""
    diag = getattr(app, "diagnostics", None)
    summary = {}
    if diag is not None:
        try:
            summary = diag.summary()
        except Exception:
            summary = {}
    stale = getattr(app, "_data_stale", False)              # live runtime state
    consec = getattr(app, "_consecutive_fetch_failures", 0)
    safe = getattr(app, "_safe_mode", False) or summary.get("safe_mode", False)
    status = ("SAFE MODE - reconfigure" if safe
              else "STALE (network issues)" if stale else "OK")
    rows = (
        ("Status", status),
        ("Fetch failures (current)", consec),
        ("Last reset reason", summary.get("reset_reason", "UNKNOWN")),
        ("Boot count", summary.get("boot_count", 0)),
        ("Reboot streak", summary.get("reboot_streak", 0)),
        ("Last error", summary.get("last_error", "") or "(none)"),
        ("App version", _read_version()),
        ("OTA", ("ready" if getattr(app, "ota", None) is not None
                 else "unavailable: %s" % (getattr(app, "ota_error", None) or "?"))),
    )
    items = "".join(
        '<div class="form-group"><label>%s</label><div>%s</div></div>'
        % (_esc(str(k)), _esc(str(v))) for k, v in rows)
    return "<h3>Diagnostics</h3>" + items


def render_page_chunks(app):
    """Yield the settings page in small pieces (a ``ChunkedResponse`` body).

    The full page is ~50 KB (four park ``<select>``s of ~140 options each).
    Building it as ONE string needs a ~50 KB contiguous allocation, which
    fails with MemoryError once a few 90 KB park fetches have fragmented the
    heap — seen live as ``config server poll error: memory allocation failed,
    allocating 50552 bytes`` with 1.5 MB total free, i.e. a dead settings
    site on a healthy device. Streaming keeps the peak allocation to ~3 KB.
    """
    import gc
    gc.collect()

    sm = app.settings
    svc = getattr(app, "service", None)
    parks = sorted(getattr(getattr(svc, "park_list", None), "park_list", []) or [],
                   key=lambda p: p.name)
    selected = list(sm.get("selected_park_ids", []) or [])

    # Names that appear on more than one park are disambiguated by appending the
    # destination/resort (FR-005a) — e.g. the two "Disneyland Park" entries.
    name_counts = {}
    for p in parks:
        name_counts[p.name] = name_counts.get(p.name, 0) + 1

    def park_label(p):
        if name_counts.get(p.name, 0) > 1 and getattr(p, "destination_name", ""):
            return "%s - %s" % (p.name, p.destination_name)
        return p.name

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

    try:
        brightness = float(sm.get("brightness_scale", "0.5"))
    except (TypeError, ValueError):
        brightness = 0.5

    fields = dict(
        sort=select("sort_mode", SORT_MODES, sm.get("sort_mode", "alphabetical")),
        scroll=select("scroll_speed", SCROLL_SPEEDS, sm.get("scroll_speed", "Medium")),
        wait_color_mode=select("wait_color_mode", WAIT_COLOR_MODES,
                               sm.get("wait_color_mode", "severity")),
        brightness=brightness,
        group=checkbox("group_by_park"),
        skip_closed=checkbox("skip_closed"),
        skip_meet=checkbox("skip_meet"),
        name_gradient=checkbox("ride_name_gradient"),
        default_color=color_select("default_color"),
        name_color=color_select("ride_name_color"),
        wait_color=color_select("ride_wait_time_color"),
        domain=_esc(sm.get("domain_name", "themeparkwaits")),
        vac_name=_esc(sm.get("next_visit", "") or ""),
        vac_year=_esc(sm.get("next_visit_year", "") or ""),
        vac_month=_esc(sm.get("next_visit_month", "") or ""),
        vac_day=_esc(sm.get("next_visit_day", "") or ""),
        diagnostics=_diagnostics_html(app),
    )

    # Everything except the park selectors is small; the selectors are streamed
    # option-batch by option-batch between the two template halves.
    head, tail = PAGE_TEMPLATE.split("{park_selectors}")
    yield head.format(**fields)

    for i in range(1, MAX_PARKS + 1):
        cur = selected[i - 1] if i - 1 < len(selected) else None
        yield ('<div class="form-group"><label>Park %d</label>'
               '<select class="form-control" name="park_%d">'
               '<option value="">(none)</option>' % (i, i))
        batch = []
        for p in parks:
            sel = " selected" if cur == p.id else ""
            batch.append('<option value="%s"%s>%s</option>'
                         % (_esc(p.id), sel, _esc(park_label(p))))
            if len(batch) >= 25:
                yield "".join(batch)
                batch = []
        if batch:
            yield "".join(batch)
        yield '</select></div>'

    yield tail.format(**fields)
    gc.collect()


def render_page(app) -> str:
    """Render the settings form as one string (desktop/tests convenience —
    on-device requests stream ``render_page_chunks`` instead)."""
    return "".join(render_page_chunks(app))


def _styled_page(inner: str) -> str:
    """Wrap a small HTML fragment in the settings page's styled shell.

    Status responses (``/update``) were bare fragments with no ``<head>`` or
    stylesheet link, so they rendered as unstyled black-on-white HTML a customer
    could read as "broken". This gives them the same head + ``/style.css`` +
    header/container as the main page. Links are styled as ``.btn`` buttons.
    """
    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<title>ThemeParkWaits</title>'
        '<link rel="stylesheet" href="/style.css"></head>'
        '<body><div class="container">'
        '<div class="header"><h1>ThemeParkWaits</h1></div>'
        '<div class="content">' + inner + '</div>'
        '</div></body></html>'
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
        from adafruit_httpserver import (Server, Response, ChunkedResponse,
                                         Redirect, GET, POST)

        pool = self.socket_pool
        if pool is None:
            import socket as _socket  # stdlib module IS a valid adafruit pool on desktop
            pool = _socket

        server = Server(pool, self.static_dir, debug=False)
        app = self.app

        # The settings page is streamed (ChunkedResponse): as ONE string it
        # needs a ~50 KB contiguous allocation, which MemoryErrors on a
        # fetch-fragmented heap and left the site unreachable in the field.
        @server.route("/")
        def _index(request):  # noqa: ANN001
            # NB: ChunkedResponse CALLS its body (needs a generator FUNCTION).
            return ChunkedResponse(request, lambda: render_page_chunks(app),
                                   content_type="text/html")

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
            return ChunkedResponse(request, lambda: render_page_chunks(app),
                                   content_type="text/html")

        @server.route("/update", [POST])
        def _update(request):  # noqa: ANN001
            # CHECK ONLY: report whether an update exists and let the user choose.
            available, version, message = check_update(app)
            if available:
                body = _styled_page(
                    "<h3>Update available</h3>"
                    "<p>Version <b>%s</b> is ready to install.</p>"
                    "<p>Installing takes 1&ndash;2 minutes: the sign will show "
                    "<b>Updating &mdash; do not unplug</b> and reboot, and this page "
                    "will be unavailable until it finishes.</p>"
                    "<form method='POST' action='/install'>"
                    "<button class='btn' type='submit'>Install update</button></form>"
                    "<p style='margin-top:12px'><a class='btn' href='/'>Not now</a></p>"
                    % _esc(version or "?"))
            else:
                body = _styled_page(
                    "<h3>No update</h3><p>%s</p>"
                    "<p><a class='btn' href='/'>Back</a></p>"
                    % _esc(message or "You're up to date."))
            return Response(request, body, content_type="text/html")

        @server.route("/install", [POST])
        def _install(request):  # noqa: ANN001
            # User confirmed: kick off the install (background task) and tell them
            # what's happening BEFORE the connection drops on reboot.
            started = install_update(app)
            if started:
                body = _styled_page(
                    "<h3>Updating&hellip;</h3>"
                    "<p><b>Do not unplug the sign.</b> It is downloading the update "
                    "and will reboot to install &mdash; the sign shows "
                    "<b>Updating &mdash; do not unplug</b> until it is done.</p>"
                    "<p>This page is unavailable during the update. Wait about two "
                    "minutes, then <a class='btn' href='/'>reload</a>.</p>")
            else:
                body = _styled_page(
                    "<h3>Couldn&rsquo;t start the update</h3>"
                    "<p>OTA is unavailable. <a class='btn' href='/'>Back</a></p>")
            return Response(request, body, content_type="text/html")

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
{name_gradient}
{wait_color_mode}
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
{diagnostics}
</div></div></body></html>
"""
