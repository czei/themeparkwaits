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
