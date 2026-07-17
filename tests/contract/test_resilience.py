# Copyright (c) 2024-2026 Michael Czeiszperger
"""Field-reliability regressions for the "goes black" failures.

1. A FAILED refresh must keep showing last-good content — never empty the queue
   (the field "goes black" bug: the old _teardown_active_content() called
   queue.clear() *before* the fallible fetch, so a flaky-network failure left the
   panel black until a later refresh happened to succeed).
2. Every HTTP response must be closed after use, on both the success and the
   parse-failure paths (a leaked socket exhausts the ESP32-S3's ~4-socket pool
   and drives the client into OutOfRetries / connection hangs).
"""
import os

from src.app import ThemeParkApp
from src.api.theme_park_service import ThemeParkService
from tests.conftest import MAGIC_KINGDOM_ID, LIVE_JSON, DESTINATIONS_JSON


# --- 1. failed refresh keeps last-good content (the black-screen regression) ---

async def test_failed_refresh_keeps_last_good_content(mock_http_client, settings_factory):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    await app._initialize_display()
    await app.setup()                     # builds the ride queue from canned data
    await app.update_data()               # consume the no-op initial refresh

    assert not app.content_queue.is_empty, "setup() should have built content"
    count_before = app.content_queue.get_content_count()

    # Force the next refresh to fail the way a flaky network does (the fetch
    # raises, so build_content_queue is skipped and _fetch_and_build returns False).
    async def _boom():
        raise RuntimeError("network down")
    app.service.update_selected_parks = _boom

    await app.update_data()

    # The bug was: queue emptied -> display renders nothing -> black panel.
    assert not app.content_queue.is_empty, "failed refresh wiped the queue (black screen!)"
    assert app.content_queue.get_content_count() == count_before
    assert app._data_stale is True
    assert app.update_interval == app._stale_retry_interval, "should retry sooner while stale"

    # And it must NOT be stuck suspended (that would also blank the screen).
    assert app._suspend_queue_render is False
    assert await app.prepare_display_content() is not None


async def test_http_500_refresh_marks_stale(settings_factory):
    """A refresh that fails via the HTTP client's swallowed-error path (returns a
    500 response, NOT an exception) must register as stale and shorten the retry —
    the common real failure the old code missed by returning True regardless."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from scrollkit.network.http_client import HttpClient, MockResponse

    def prov(url):
        if url.endswith("/destinations"):
            return MockResponse(status_code=200, text=DESTINATIONS_JSON)
        return MockResponse(status_code=500, text="{}")   # /live fails, no exception

    hc = HttpClient(session=None, mock_provider=prov)
    hc.set_use_live_data(False)
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=hc, settings=sm)
    await app._initialize_display()
    await app.setup()                     # boot fetch fails (0 parks updated)
    await app.update_data()               # consume the no-op skip

    await app.update_data()               # real refresh: 500 -> 0 updated, no raise
    assert app._data_stale is True, "a 500/timeout refresh must be detected as stale"
    assert app.update_interval == app._stale_retry_interval
    assert not app.content_queue.is_empty, "must keep last-good/offline content, not black"


async def test_recovered_refresh_clears_stale_state(mock_http_client, settings_factory):
    """After a failure, a subsequent successful refresh clears the stale flag and
    restores the normal cadence."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    await app._initialize_display()
    await app.setup()
    await app.update_data()               # consume no-op

    async def _boom():
        raise RuntimeError("network down")
    real_update = app.service.update_selected_parks
    app.service.update_selected_parks = _boom
    await app.update_data()
    assert app._data_stale is True

    app.service.update_selected_parks = real_update   # network back
    await app.update_data()
    assert app._data_stale is False
    assert app._consecutive_fetch_failures == 0
    assert app.update_interval == app._default_update_interval


# --- 2. responses are always closed (socket-leak fix) -------------------------

class _RecordingResponse:
    def __init__(self, text):
        self.text = text
        self.closed = False

    def close(self):
        self.closed = True


class _RecordingClient:
    """An http_client stub returning a fresh recording response per get()."""
    def __init__(self, text):
        self._text = text
        self.responses = []

    async def get(self, url, headers=None, max_retries=3):
        r = _RecordingResponse(self._text)
        self.responses.append(r)
        return r


async def test_fetch_park_data_closes_response_on_success(settings_factory):
    client = _RecordingClient(LIVE_JSON)
    svc = ThemeParkService(client, settings_factory())
    data = await svc.fetch_park_data(MAGIC_KINGDOM_ID)
    assert data
    assert client.responses, "expected at least one request"
    assert all(r.closed for r in client.responses), "response left open (socket leak)"


async def test_fetch_park_data_closes_response_on_bad_json(settings_factory):
    client = _RecordingClient("definitely not json {{{")
    svc = ThemeParkService(client, settings_factory())
    data = await svc.fetch_park_data(MAGIC_KINGDOM_ID)
    assert data is None
    assert len(client.responses) >= 1
    assert all(r.closed for r in client.responses), "response left open on parse failure"


async def test_fetch_park_list_closes_response(settings_factory):
    client = _RecordingClient(DESTINATIONS_JSON)
    svc = ThemeParkService(client, settings_factory())
    result = await svc.fetch_park_list()
    assert result is not None
    assert client.responses
    assert all(r.closed for r in client.responses), "park-list response left open"


# --- 3. logging is bounded and preserves evidence across reboots --------------

def test_errorhandler_preserves_log_on_boot_in_production(tmp_path):
    """A reboot must NOT wipe the previous session's log (the old __init__ deleted
    it AND truncated it with a 'w' write-test, erasing crash evidence)."""
    from scrollkit.utils.error_handler import ErrorHandler
    log = str(tmp_path / "error_log")
    with open(log, "w") as f:
        f.write("previous session crash evidence\n")
    eh = ErrorHandler(log, mode=ErrorHandler.PRODUCTION)
    assert not eh.is_readonly
    with open(log) as f:
        assert "previous session crash evidence" in f.read(), \
            "production boot wiped the prior log (lost crash evidence)"


def test_errorhandler_bounds_log_size(tmp_path):
    """Logging can never fill flash: the file is rotated once it hits the cap."""
    from scrollkit.utils.error_handler import ErrorHandler
    log = str(tmp_path / "error_log")
    eh = ErrorHandler(log, mode=ErrorHandler.PRODUCTION)
    big = "x" * 500
    for _ in range(200):                       # ~100 KB of writes
        eh.error(None, big)
    size = os.stat(log)[6]
    assert size <= ErrorHandler.MAX_LOG_BYTES + 2000, f"log not bounded: {size} bytes"
    assert os.path.exists(log + ".old"), "expected one rotated generation"


# --- 4. NVM boot-loop breaker + crash breadcrumbs -----------------------------

def test_diagnostics_boot_loop_breaker_enters_safe_mode():
    """Repeated fault-reboots with no clean run in between trip safe mode; a clean
    run resets the streak."""
    from src.diagnostics import Diagnostics, RAPID_BOOT_LIMIT, _SIZE
    nvm = bytearray(_SIZE)                      # persists across simulated boots

    flags = [Diagnostics(nvm).record_boot("WATCHDOG").safe_mode
             for _ in range(RAPID_BOOT_LIMIT + 2)]
    assert flags[0] is False
    assert flags[-1] is True, "should enter safe mode after repeated fault reboots"

    Diagnostics(nvm).note_clean_run()          # a healthy run clears the streak
    d = Diagnostics(nvm).record_boot("WATCHDOG")
    assert d.rapid_boots == 1
    assert d.safe_mode is False


def test_diagnostics_persists_crash_message_and_counters():
    from src.diagnostics import Diagnostics, _SIZE
    nvm = bytearray(_SIZE)
    d = Diagnostics(nvm).record_boot("POWER_ON")
    assert d.boot_count == 1
    d.record_crash("MemoryError: pystack exhausted")
    d.note_fetch_result(False, consecutive_failures=3)

    d2 = Diagnostics(nvm).record_boot("SOFTWARE")   # next boot reads the record
    assert d2.boot_count == 2
    assert "MemoryError" in d2.last_message
    assert d2.consecutive_failures == 3
    assert d2.summary()["reset_reason"] == "SOFTWARE"


def test_diagnostics_open_is_noop_off_device():
    """open() must return a usable no-op store on desktop (no NVM)."""
    from src import diagnostics
    d = diagnostics.open()
    d.record_boot("UNKNOWN")            # must not raise
    d.record_crash("x")
    d.note_fetch_result(True)
    assert d.safe_mode is False
    assert isinstance(d.summary(), dict)


def test_config_page_shows_diagnostics(mock_http_client, settings_factory):
    """The config web UI surfaces the diagnostics panel for field debugging."""
    from src.web.config_server import render_page
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    html = render_page(app)
    assert "Diagnostics" in html
    assert "Last reset reason" in html
    assert "Status" in html


# --- failure budget -> cold reset, with NO in-band recovery (2026-07-16) ------

async def test_fetch_failures_never_bounce_the_radio(
        mock_http_client, settings_factory):
    """3.5.17 contract: consecutive fetch failures ride the failure budget
    straight to the base auto-reboot (cold reset) — the app must NOT bounce the
    radio or rebuild the session along the way. The 2026-07-16 soak proved
    bounce+rebuild does not cure the selective wedge, while a failed bounce can
    leave the radio unassociated mid-run (observed live on the two-AP mesh)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    await app._initialize_display()
    await app.setup()
    await app.update_data()               # consume the no-op initial refresh

    bounces = []

    class _Wifi:
        async def bounce(self):
            bounces.append(app._consecutive_fetch_failures)
            return True
    app.wifi = _Wifi()

    rebuilds = {"n": 0}
    def _rebuild():
        rebuilds["n"] += 1
        return True
    app.http_client.rebuild_session = _rebuild

    async def _boom():
        raise RuntimeError("network down")
    app.service.update_selected_parks = _boom

    for _ in range(7):
        await app.update_data()

    assert bounces == [], bounces         # no in-band radio recovery, ever
    assert rebuilds["n"] == 0             # no in-band session recovery, ever
    assert app.consecutive_refresh_failures == 7   # the budget still counts


# --- update-check health ledger: the selective-wedge detector -----------------

def _check_app(mock_http_client, settings_factory, tmp_path):
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    # Persist the reset budget somewhere writable (on-device this is "/...").
    app.CHECK_RESET_BUDGET_PATH = str(tmp_path / "check_reset_count")
    return app


def test_check_failures_escalate_to_one_budgeted_reset(
        mock_http_client, settings_factory, tmp_path):
    """The selective wedge: park fetches succeed on their pooled socket while
    every check (a NEW connection) fails — only the CHECK counter can see it.
    After MAX_CHECK_FAILURES consecutive failures the app asks for exactly one
    cold reset (returns True); the count restarts toward the next one."""
    app = _check_app(mock_http_client, settings_factory, tmp_path)

    results = [app.note_check_result(False, "check failed: OSError: 16")
               for _ in range(app.MAX_CHECK_FAILURES)]
    assert results[:-1] == [False] * (app.MAX_CHECK_FAILURES - 1)
    assert results[-1] is True            # the threshold asks for the reset
    assert app._consecutive_check_failures == 0   # re-counts toward the next

    # Park-fetch success must NOT have cleared the ledger meanwhile — that is
    # the whole point (pooled-socket success can't see the wedge). Simulate by
    # confirming a fresh failure run escalates again on schedule.
    for _ in range(app.MAX_CHECK_FAILURES - 1):
        assert app.note_check_result(False, "still wedged") is False


def test_check_reset_budget_caps_consecutive_resets(
        mock_http_client, settings_factory, tmp_path):
    """An external outage (check host down, DNS broken) is NOT curable by a
    reset: after CHECK_RESET_BUDGET escalations with no definitive answer in
    between, the app stops asking for resets instead of reboot-looping."""
    app = _check_app(mock_http_client, settings_factory, tmp_path)

    fired = 0
    for _ in range(app.CHECK_RESET_BUDGET + 2):        # budget + 2 extra rounds
        for _ in range(app.MAX_CHECK_FAILURES):
            if app.note_check_result(False, "host down"):
                fired += 1
    assert fired == app.CHECK_RESET_BUDGET

    # A definitive answer re-arms the budget (and clears the counter).
    assert app.note_check_result(True) is False
    for _ in range(app.MAX_CHECK_FAILURES - 1):
        assert app.note_check_result(False, "wedged again") is False
    assert app.note_check_result(False, "wedged again") is True


def test_check_reset_budget_survives_reboot(
        mock_http_client, settings_factory, tmp_path):
    """The budget must persist across the very reboots it triggers — a fresh
    app instance (post-reset boot) continues the same budget file."""
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    for _ in range(app.MAX_CHECK_FAILURES):
        app.note_check_result(False, "wedged")         # spends budget slot 1

    app2 = _check_app(mock_http_client, settings_factory, tmp_path)
    assert app2._read_check_reset_count() == 1

    # Spend the remaining budget across "reboots"...
    fired = 0
    for _ in range(app2.CHECK_RESET_BUDGET + 1):
        for _ in range(app2.MAX_CHECK_FAILURES):
            if app2.note_check_result(False, "wedged"):
                fired += 1
    assert fired == app2.CHECK_RESET_BUDGET - 1        # slot 1 already spent

    # ...and a definitive answer clears the file for good.
    app2.note_check_result(True)
    assert app2._read_check_reset_count() == 0


async def test_failures_feed_base_watchdog_and_success_resets(
        mock_http_client, settings_factory):
    """enable_auto_reboot is only as real as its diet: update_data() must call
    note_refresh_result() so the base ladder counts, and a success must reset it.
    (The wedge review found the app never fed the hook, so the watchdog could
    never fire regardless of settings.)"""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    await app._initialize_display()
    await app.setup()
    await app.update_data()               # consume the no-op initial refresh

    assert app.enable_auto_reboot is True
    assert app.max_refresh_failures == 12
    # Regression guard for the v3.5.15 watchdog reset loop: the timeout must
    # exceed the app's longest legitimate event-loop block (~20 s synchronous
    # update check). The library's 8 s default is NOT survivable here.
    assert app.watchdog_timeout >= 30

    async def _boom():
        raise RuntimeError("network down")
    good = app.service.update_selected_parks
    app.service.update_selected_parks = _boom

    await app.update_data()
    await app.update_data()
    assert app.consecutive_refresh_failures == 2

    app.service.update_selected_parks = good
    await app.update_data()
    assert app.consecutive_refresh_failures == 0
