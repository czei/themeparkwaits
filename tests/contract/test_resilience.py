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


# --- the wedge ledger: windowed, classified escalation (3.5.18) ---------------

EBUSY = "GET https://api.themeparks.wiki/v1/entity/x/live failed after 3 attempts: 16"


def _check_app(mock_http_client, settings_factory, tmp_path):
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    # Persist the reset budget somewhere writable (on-device this is "/...").
    app.RECOVERY_BUDGET_PATH = str(tmp_path / "check_reset_count")
    return app


def test_wedge_classifier_matches_ebusy_only():
    """Only the errno-16 signature is reset-curable; everything else (DNS,
    HTTP status, the mbedtls -16256 memory error) must never trigger one."""
    f = ThemeParkApp._is_wedge_error
    assert f("Update check failed: OSError: 16")
    assert f(EBUSY)
    assert f("[Errno 16] EBUSY")
    assert not f("Update check failed: OSError: -16256")     # PK_ALLOC, not wedge
    assert not f("Update check failed: [Errno -2] Name or service not known")
    assert not f("Server error: 500")
    assert not f("check failed: MemoryError")


def test_wedge_strikes_escalate_and_survive_flapping(
        mock_http_client, settings_factory, tmp_path):
    """THE 2026-07-16 lesson: the wedge flaps, so healthy moments must not
    erase the evidence. Strikes from refreshes and checks accumulate in one
    window; a definitive check between them re-arms the budget but keeps the
    strikes; the threshold buys exactly one reset."""
    app = _check_app(mock_http_client, settings_factory, tmp_path)

    results = []
    for i in range(app.WEDGE_STRIKES_MAX - 1):
        src = "refresh" if i % 2 else "check"
        results.append(app.note_wedge_strike(src, EBUSY))
        if i == 2:
            # A lucky definitive check mid-flap: must NOT clear the strikes.
            assert app.note_check_result(True) is False
    assert results == [False] * (app.WEDGE_STRIKES_MAX - 1)
    assert len(app._wedge_strikes) == app.WEDGE_STRIKES_MAX - 1

    assert app.note_wedge_strike("refresh", EBUSY) is True   # threshold: reset
    assert app._wedge_strikes == []                          # fresh count after


def test_non_wedge_check_failures_never_escalate(
        mock_http_client, settings_factory, tmp_path):
    """A check-host outage or DNS failure is not curable by a reset — any
    number of them must produce zero strikes and zero resets."""
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    for _ in range(20):
        assert app.note_check_result(False, "check failed: [Errno -2] DNS") is False
    assert app._wedge_strikes == []


def test_wedge_strikes_expire_by_time_not_success(
        mock_http_client, settings_factory, tmp_path):
    """Strikes outside the rolling window drop out of the count: five stale
    strikes plus one fresh one must NOT reach a threshold of six."""
    import time
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    stale = time.monotonic() - app.WEDGE_WINDOW_S - 60
    app._wedge_strikes = [stale] * (app.WEDGE_STRIKES_MAX - 1)

    assert app.note_wedge_strike("check", EBUSY) is False    # stale ones pruned
    assert len(app._wedge_strikes) == 1


def test_ebusy_check_failures_ride_the_budget(
        mock_http_client, settings_factory, tmp_path):
    """Budget semantics: one reset per unhealthy epoch, max 3 without health;
    a definitive answer re-arms; the budget file survives 'reboots' (fresh
    app instances)."""
    app = _check_app(mock_http_client, settings_factory, tmp_path)

    fired = 0
    for _ in range(app.RECOVERY_RESET_BUDGET + 2):           # budget + 2 rounds
        for _ in range(app.WEDGE_STRIKES_MAX):
            if app.note_check_result(False, EBUSY):
                fired += 1
    assert fired == app.RECOVERY_RESET_BUDGET                # capped, no loop

    # A fresh instance (post-reboot) sees the spent budget on disk.
    app2 = _check_app(mock_http_client, settings_factory, tmp_path)
    assert app2._read_recovery_reset_count() == app.RECOVERY_RESET_BUDGET

    # Health re-arms; the next full strike round fires again.
    assert app2.note_check_result(True) is False
    assert app2._read_recovery_reset_count() == 0
    fired2 = sum(1 for _ in range(app2.WEDGE_STRIKES_MAX)
                 if app2.note_check_result(False, EBUSY))
    assert fired2 == 1


async def test_partial_success_with_wedge_evidence_strikes_and_stays_hot(
        mock_http_client, settings_factory, tmp_path):
    """One park succeeding on a surviving pooled socket must NOT mask the
    wedge: the cycle keeps its content (ok) but counts a strike, keeps the
    short retry cadence, and drains the socket pool afterward."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    await app._initialize_display()
    await app.setup()
    await app.update_data()               # consume the no-op initial refresh

    drained = {"n": 0}
    app.http_client.close_pooled_sockets = lambda: drained.__setitem__("n", drained["n"] + 1) or True

    async def _partial():
        app.service.last_refresh_errors = [EBUSY]
        return 1                          # one park updated, one died EBUSY
    app.service.update_selected_parks = _partial

    await app.update_data()

    assert not app.content_queue.is_empty          # content kept (it IS a success)
    assert app._data_stale is False
    assert app.update_interval == app._stale_retry_interval   # but stay hot
    assert len(app._wedge_strikes) == 1                       # and count it
    assert drained["n"] >= 1                                  # idle = zero sockets


async def test_healthy_refresh_closes_sockets_and_rearms_budget(
        mock_http_client, settings_factory, tmp_path):
    """Fully healthy cycles idle with the pool drained and the budget re-armed
    — but do NOT erase wedge strikes (only time does)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    await app._initialize_display()
    await app.setup()
    await app.update_data()               # consume the no-op initial refresh

    drained = {"n": 0}
    app.http_client.close_pooled_sockets = lambda: drained.__setitem__("n", drained["n"] + 1) or True
    app._write_recovery_reset_count(2)    # pretend two resets were spent
    app.note_wedge_strike("check", EBUSY)

    await app.update_data()               # healthy refresh (mock data)

    assert drained["n"] >= 1
    assert app._read_recovery_reset_count() == 0   # health re-armed the budget
    assert len(app._wedge_strikes) == 1            # strikes survive success
    assert app.update_interval == app._default_update_interval


def test_default_cadence_is_ten_minutes(mock_http_client, settings_factory):
    """Product intent (owner, 2026-07-16): ~10-minute refreshes."""
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    assert app._default_update_interval == 600
    assert app._stale_retry_interval == 60


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
