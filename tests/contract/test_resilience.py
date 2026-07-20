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
    """An http_client stub returning a fresh recording response per get().

    Deliberately exposes ONLY .text + .close() (no iter_content): the streaming
    fetch path must keep working against text-only responses via its fallback,
    and must STILL close them (the socket-leak contract)."""
    def __init__(self, text):
        self._text = text
        self.responses = []

    async def get(self, url, headers=None, max_retries=3, stream=False):
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


# --- streaming parse (2026-07-19): no whole-body allocation, ever -------------
# The MemoryError field failure: 50-90 KB park bodies held as one contiguous
# string (twice, with the old eager .content copy) + a full json.loads tree,
# on a non-compacting heap. The streamed extractor must produce IDENTICAL
# model-visible results from arbitrary chunkings.


def _norm_rides(data):
    """Model-visible view of a /live payload: (id, name, status, wait) per
    ATTRACTION — exactly the fields ThemePark.get_rides_from_json consumes."""
    out = []
    for item in data.get("liveData", []):
        if item.get("entityType") != "ATTRACTION":
            continue
        q = item.get("queue") or {}
        std = q.get("STANDBY") if isinstance(q, dict) else None
        wait = std.get("waitTime") if isinstance(std, dict) else None
        out.append((item.get("id"), item.get("name"), item.get("status"), wait))
    return out


def test_streaming_extractor_matches_whole_tree_parse():
    """Parity: streamed extraction == json.loads extraction, at pathological
    chunk sizes (17 B) through single-chunk whole-body."""
    import json
    from src.api.theme_park_service import _extract_live_rides

    expected = _norm_rides(json.loads(LIVE_JSON))
    assert expected, "fixture must contain ATTRACTION entries"

    body = LIVE_JSON.encode("utf-8")
    for n in (17, 64, 512, len(body) + 1):
        chunks = iter([body[i:i + n] for i in range(0, len(body), n)])
        streamed = _extract_live_rides(chunks)
        assert _norm_rides(streamed) == expected, f"chunk size {n} diverged"


def test_streaming_extractor_rejects_garbage():
    """Malformed payloads raise (KeyError/ValueError/EOFError) so the fetch
    retry treats them as parse failures — never a silent empty success."""
    import pytest
    from src.api.theme_park_service import _extract_live_rides
    with pytest.raises((KeyError, ValueError, EOFError)):
        _extract_live_rides(iter([b'{"noLiveDataHere": []}']))


async def test_fetch_park_data_streams_via_mock(mock_http_client, settings_factory):
    """End-to-end through HttpClient's stream=True path (mock provider →
    StreamingResponse fallback): same minimal-dict shape the models consume."""
    svc = ThemeParkService(mock_http_client, settings_factory())
    data = await svc.fetch_park_data(MAGIC_KINGDOM_ID)
    assert data and "liveData" in data
    assert all(e.get("entityType") == "ATTRACTION" for e in data["liveData"])
    assert _norm_rides(data), "streamed fetch produced no rides"


def test_streaming_extractor_handles_empty_chunks():
    """A native iter_content may legally yield b'' — the vendored parser's
    LOCAL PATCH 1 must skip them (upstream raised IndexError)."""
    import json
    from src.api.theme_park_service import _extract_live_rides
    expected = _norm_rides(json.loads(LIVE_JSON))
    body = LIVE_JSON.encode("utf-8")
    chunks = [b""]
    for i in range(0, len(body), 64):
        chunks.append(body[i:i + 64])
        chunks.append(b"")
    assert _norm_rides(_extract_live_rides(iter(chunks))) == expected


def test_streaming_extractor_rejects_truncated_body():
    """A body cut after a well-formed liveData array (missing the root's
    closing brace) must raise — the extractor finishes the ROOT object."""
    import pytest
    from src.api.theme_park_service import _extract_live_rides
    with pytest.raises((KeyError, ValueError, EOFError)):
        _extract_live_rides(iter([b'{"liveData": []']))


def test_streaming_extractor_normalizes_bad_shapes():
    """Valid JSON with the wrong SHAPE (scalar root, non-array liveData,
    non-object entries) must land in the parse-failure class — never the
    generic handler that feeds wedge evidence."""
    import pytest
    from src.api.theme_park_service import _extract_live_rides
    for payload in (b"42", b'{"liveData": 7}', b'{"liveData": ["x", 3]}'):
        with pytest.raises((KeyError, ValueError, EOFError)):
            _extract_live_rides(iter([payload]))


def _norm_catalog(data):
    """Model-visible view of a /destinations payload: (park id, park name,
    destination name) — exactly what ThemeParkList.__init__ consumes."""
    out = []
    for dest in data.get("destinations", []):
        if not isinstance(dest, dict):
            continue
        dname = dest.get("name", "")
        for p in dest.get("parks", []):
            if not isinstance(p, dict):
                continue
            if p.get("id") and p.get("name"):
                out.append((p["id"], p["name"], dname))
    return sorted(out)


def test_streaming_catalog_matches_whole_tree_parse():
    """Parity for the /destinations catalog (the last whole-body allocation):
    streamed extraction == json.loads extraction, at pathological chunk sizes.
    Exercises NESTED transients (each destination's parks array)."""
    import json
    from src.api.theme_park_service import _extract_destinations

    expected = _norm_catalog(json.loads(DESTINATIONS_JSON))
    assert expected, "fixture must contain parks"

    body = DESTINATIONS_JSON.encode("utf-8")
    for n in (13, 64, 512, len(body) + 1):
        chunks = iter([body[i:i + n] for i in range(0, len(body), n)])
        assert _norm_catalog(_extract_destinations(chunks)) == expected, \
            f"chunk size {n} diverged"


def test_streaming_catalog_rejects_truncated_and_bad_shapes():
    import pytest
    from src.api.theme_park_service import _extract_destinations
    for payload in (b'{"destinations": [', b"42", b'{"destinations": 7}',
                    b'{"nothing": 1}'):
        with pytest.raises((KeyError, ValueError, EOFError)):
            _extract_destinations(iter([payload]))


async def test_fetch_park_list_streams_and_builds_models(
        mock_http_client, settings_factory):
    """End-to-end: the streamed catalog still builds a populated, sorted
    ThemeParkList carrying destination names (the FR-005a disambiguator)."""
    import json
    svc = ThemeParkService(mock_http_client, settings_factory())
    park_list = await svc.fetch_park_list()
    assert park_list is not None and park_list.park_list

    # ThemeParkList strips non-ASCII from both names (e.g. the ® in "Walt
    # Disney World® Resort") — apply the same transform to the expectation.
    from src.models.theme_park import ThemePark
    strip = ThemePark.remove_non_ascii
    expected = [(pid, strip(pname), strip(dname))
                for pid, pname, dname in _norm_catalog(json.loads(DESTINATIONS_JSON))]
    got = sorted((p.id, p.name, getattr(p, "destination_name", ""))
                 for p in park_list.park_list)
    assert got == sorted(expected)
    names = [p.name for p in park_list.park_list]
    assert names == sorted(names), "park list must stay alphabetically sorted"


async def test_mid_stream_failure_closes_and_keeps_wedge_evidence(settings_factory):
    """Device-shaped response whose body dies mid-stream with errno 16: the
    socket must close, the fetch must fail, and the EBUSY signature must reach
    last_refresh_errors (wedge-classifier evidence must survive streaming)."""

    class _DyingStream:
        status_code = 200
        headers = {}

        def __init__(self):
            self.closed = False

        def iter_content(self, chunk_size=512):
            yield b'{"liveData": ['
            raise OSError("[Errno 16] EBUSY")

        def close(self):
            self.closed = True

    class _Client:
        def __init__(self):
            self.responses = []

        async def get(self, url, headers=None, max_retries=3, stream=False):
            r = _DyingStream()
            self.responses.append(r)
            return r

    client = _Client()
    svc = ThemeParkService(client, settings_factory())
    data = await svc.fetch_park_data(MAGIC_KINGDOM_ID)
    assert data is None
    assert all(r.closed for r in client.responses), "mid-stream failure leaked the socket"
    assert any("Errno 16" in e for e in svc.last_refresh_errors), \
        "EBUSY evidence must survive for the wedge classifier"


# --- partial failure is visible and escalates (2026-07-19) --------------------
# Three big parks failed MemoryError for hours behind an all-green dashboard:
# a partial success rode the full-health accounting path. Partial must read
# DEGRADED (stale flag, hot retry, no budget/streak re-arm, PARTIAL status)
# and a continuous degraded hour earns one rate-limited reboot cure.


def _make_partial(app, failed=("EPCOT",)):
    async def _partial():
        app.service.last_failed_parks = list(failed)
        app.service.last_refresh_errors = []
        return 1                      # one park updated => ok=True (partial)
    app.service.update_selected_parks = _partial


async def test_partial_refresh_reads_degraded_not_healthy(
        mock_http_client, settings_factory, tmp_path):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    await app._initialize_display()
    await app.setup()
    await app.update_data()               # consume the no-op initial refresh

    app._write_recovery_reset_count(2)    # pretend two resets were spent
    _make_partial(app)
    await app.update_data()

    assert app._data_stale is True, "partial must read degraded"
    assert app.update_interval == app._stale_retry_interval
    assert app._read_recovery_reset_count() == 2, \
        "partial must NOT re-arm the wedge budget (full health only)"
    assert app._partial_since is not None

    from src.web.config_server import _diagnostics_html
    html = _diagnostics_html(app)
    assert "PARTIAL" in html and "EPCOT" in html
    assert "Parks (last updated)" in html


async def test_partial_passes_rearm_false_to_diagnostics(
        mock_http_client, settings_factory, tmp_path):
    """The recovery machinery must see a partial as stamp-only: rearm=False
    reaches diagnostics, and no clean run is recorded (review 2026-07-19)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    await app._initialize_display()
    await app.setup()
    await app.update_data()               # consume the no-op initial refresh

    calls = []

    class _Diag:
        def note_fetch_result(self, ok, consecutive_failures=0, rearm=None):
            calls.append(("fetch", ok, rearm))
        def note_clean_run(self):
            calls.append(("clean",))
        def record_crash(self, message):
            pass
        def note_deliberate_reboot(self):
            pass
    app.diagnostics = _Diag()

    _make_partial(app)
    await app.update_data()

    assert ("fetch", True, False) in calls, "partial must stamp with rearm=False"
    assert ("clean",) not in calls, "partial must never record a clean run"


async def test_partial_recovery_restores_full_health(
        mock_http_client, settings_factory, tmp_path):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    await app._initialize_display()
    await app.setup()
    await app.update_data()

    _make_partial(app)
    await app.update_data()
    assert app._partial_since is not None

    async def _full():
        app.service.last_failed_parks = []
        app.service.last_refresh_errors = []
        return 1
    app.service.update_selected_parks = _full
    await app.update_data()
    assert app._data_stale is False
    assert app._partial_since is None, "full health must clear the degraded streak"
    assert app.update_interval == app._default_update_interval


async def test_degraded_hour_escalates_to_reboot_cure(
        mock_http_client, settings_factory, tmp_path):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import time
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    await app._initialize_display()
    await app.setup()
    await app.update_data()

    events = []

    class _Diag:
        def note_fetch_result(self, ok, consecutive_failures=0, rearm=None):
            pass
        def note_clean_run(self):
            pass
        def record_crash(self, message):
            events.append(("crash", message))
        def note_deliberate_reboot(self):
            events.append(("epoch",))
    app.diagnostics = _Diag()

    resets = []
    app._hardware_reset = lambda: resets.append(True)
    _make_partial(app)
    app._partial_since = time.monotonic() - app.PARTIAL_ESCALATION_S - 1
    await app.update_data()

    assert resets == [True], "a degraded hour must attempt the reboot cure"
    crashes = [m for k, m in [e for e in events if e[0] == "crash"]]
    assert any("degraded" in m for m in crashes)
    assert ("epoch",) in events, "escalation must open the rate-limit epoch"


async def test_boot_partial_marks_degraded(mock_http_client, settings_factory):
    """A partial BOOT fetch must not read healthy for its first 10 minutes."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)

    async def _partial():
        app.service.last_failed_parks = ["EPCOT"]
        return 1
    app.service.update_selected_parks = _partial

    await app._initialize_display()
    await app.setup()
    assert app._data_stale is True
    assert app.update_interval == app._stale_retry_interval


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


class _SafeModeDiag:
    """Stub diagnostics pinned in safe mode (the NVM breaker has tripped)."""
    safe_mode = True

    def __init__(self):
        self.clean_runs = 0
    def record_boot(self, reason="UNKNOWN"):
        return self
    def note_clean_run(self):
        self.clean_runs += 1
    def note_fetch_result(self, ok, consecutive_failures=0, rearm=None):
        pass
    def record_crash(self, message):
        pass
    def summary(self):
        return {"reset_reason": "WATCHDOG"}


async def test_safe_mode_still_fetches_park_catalog(
        mock_http_client, settings_factory):
    """The 2026-07-17 customer trap: safe mode skipped the catalog fetch, so
    the 'reconfigure' page it advertises could only offer '(none)' — with no
    exit. Safe mode must still fetch the PARK CATALOG (guarded) while
    continuing to skip wait-time fetching."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    app.diagnostics = _SafeModeDiag()

    fetched = {"catalog": 0}
    real_init = app.service.initialize
    async def _init():
        fetched["catalog"] += 1
        return await real_init()
    app.service.initialize = _init

    async def _never():
        raise AssertionError("safe mode must not fetch wait times")
    app.service.update_selected_parks = _never

    await app._initialize_display()
    await app.setup()

    assert app._safe_mode is True
    assert fetched["catalog"] == 1        # the reconfigure page gets its parks
    assert app.service.park_list is not None


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
    # Degraded is not healthy (review 2026-07-19): wedge evidence must surface
    # as stale on the diagnostics page even though content was kept.
    assert app._data_stale is True
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


async def test_partial_wedge_escalation_stamps_success_before_crash_record(
        mock_http_client, settings_factory, tmp_path):
    """Ordering (review 2026-07-17): when a PARTIAL success lands the final
    wedge strike, this refresh's success must reach diagnostics BEFORE the
    escalation's record_crash — record_crash flushes the last-ok epoch to NVM,
    and the cold reset that follows destroys anything still in RAM. Wrong
    order = the post-reboot page understates 'Last fetch OK' by up to the
    30-min persist throttle."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    await app._initialize_display()
    await app.setup()
    await app.update_data()               # consume the no-op initial refresh

    calls = []

    class _Diag:
        def note_fetch_result(self, ok, consecutive_failures=0, rearm=None):
            calls.append(("fetch", ok))
        def record_crash(self, message):
            calls.append(("crash", message))
        def note_clean_run(self):
            pass
    app.diagnostics = _Diag()

    import time
    now = time.monotonic()
    app._wedge_strikes = [now] * (app.WEDGE_STRIKES_MAX - 1)  # next strike fires

    async def _partial():
        app.service.last_refresh_errors = [EBUSY]
        return 1                          # one park updated, one died EBUSY
    app.service.update_selected_parks = _partial

    await app.update_data()

    crash_calls = [c for c in calls if c[0] == "crash"]
    assert crash_calls, "escalation should record WHY+WHEN to NVM"
    assert "wedge cold reset (refresh-partial)" in crash_calls[0][1]
    first_crash = calls.index(crash_calls[0])
    assert ("fetch", True) in calls[:first_crash], \
        "this refresh's success must be stamped before record_crash flushes"


# --- keep-going redesign (2026-07-19): nothing ever parks ---------------------
# Design invariant: from any state the device returns to a normal-operation
# attempt within bounded time, forever, with no human intervention. Health for
# the boot-loop breaker is "the app runs", never "the network works".


async def test_stable_uptime_is_a_clean_run(mock_http_client, settings_factory):
    """R1 fix: surviving STABLE_UPTIME_S IS a clean run — it clears the NVM
    boot-loop streak and /safemode.py's counter with NO fetch success, so an
    offline-but-running box can never accumulate into safe mode. It must NOT
    touch the fetch accounting (the failure-reboot epoch ends only on a real
    fetch success — that rate limit exists precisely for boxes that stay up
    but keep failing)."""
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)

    calls = []

    class _Diag:
        def note_clean_run(self):
            calls.append("clean")
        def note_fetch_result(self, ok, consecutive_failures=0, rearm=None):
            calls.append("fetch")
    app.diagnostics = _Diag()
    cleared = []
    app._clear_safemode_streak = lambda: cleared.append(True)

    app.STABLE_UPTIME_S = 0
    app.running = True
    await app._note_stable_runtime()

    assert "clean" in calls, "stable uptime must count as a clean run"
    assert "fetch" not in calls, "must not fake a fetch success"
    assert cleared, "stable uptime must re-arm /safemode.py's fast retries"


def test_outage_reboot_cycles_never_reach_safe_mode():
    """THE brick walk is dead: each outage cycle = >10 min of stable (offline)
    running — so the stable-uptime clean run fires before every deliberate
    reboot — and 100 such cycles must leave safe mode untripped. The
    failure-reboot epoch flag, by contrast, persists through all of them
    (rate-limiting reboots to ~hourly) until a REAL fetch success ends it."""
    from src.diagnostics import Diagnostics, _SIZE
    nvm = bytearray(max(_SIZE, 242))
    for _ in range(100):
        d = Diagnostics(nvm).record_boot("SOFTWARE")
        assert d.safe_mode is False, "an outage walked the box into safe mode"
        d.note_clean_run()             # the stable-uptime task (>10 min alive)
        d.note_deliberate_reboot()     # then the rate-limited failure reboot
    d = Diagnostics(nvm).record_boot("SOFTWARE")
    assert d.safe_mode is False
    assert d.rapid_boots == 1
    assert d.was_deliberate_reboot() is True    # epoch persists across reboots
    d.note_fetch_result(True)                   # WAN back: one success ends it
    assert d.was_deliberate_reboot() is False


async def test_recovery_mode_probation_fetch_exits(mock_http_client, settings_factory):
    """Recovery mode (the former TERMINAL safe mode) self-heals: a probation
    fetch that succeeds proves the crash cause cleared -> cold reset into a
    normal boot (desktop: exits in place). No human required."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    app.diagnostics = _SafeModeDiag()
    await app._initialize_display()
    await app.setup()
    assert app._safe_mode is True

    resets = []
    app._hardware_reset = lambda: resets.append(True)
    app._safe_mode_last_probe = None           # probe due immediately
    await app.update_data()                    # recovery tick -> probation fetch

    assert resets, "probation success must reboot into a normal boot"
    assert app._safe_mode is False             # desktop in-place exit
    assert app.update_interval == app._default_update_interval


async def test_recovery_mode_probe_is_throttled(mock_http_client, settings_factory):
    """Between probes, recovery mode stays quiet (no fetch storm from the
    60 s data cadence)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    app.diagnostics = _SafeModeDiag()
    await app._initialize_display()
    await app.setup()

    fetches = []
    async def _count():
        fetches.append(1)
        return True
    app._fetch_and_build = _count
    import time
    app._safe_mode_last_probe = time.monotonic()   # probed "just now"
    await app.update_data()
    assert fetches == [], "probe fired before its interval elapsed"


async def test_recovery_mode_timed_reboot_fires_once(mock_http_client, settings_factory):
    """The 60-min full reboot re-tests the whole boot path even when probes
    can't reach the crasher (it lives in setup()). Fires once per boot — the
    reset is a no-op on desktop, so the flag stops a sim reboot storm."""
    sm = settings_factory(selected_park_ids=[MAGIC_KINGDOM_ID])
    app = ThemeParkApp(http_client=mock_http_client, settings=sm)
    app._safe_mode = True
    resets = []
    app._hardware_reset = lambda: resets.append(True)
    app._uptime_s = lambda: app.SAFE_MODE_REBOOT_S + 1
    import time
    app._safe_mode_last_probe = time.monotonic()   # keep probes out of the way
    await app._recovery_mode_tick()
    app._safe_mode_last_probe = time.monotonic()
    await app._recovery_mode_tick()
    assert resets == [True], "timed re-test reboot must fire exactly once"


def test_wedge_budget_exhaustion_trickles_after_cooldown(
        mock_http_client, settings_factory, tmp_path):
    """Budget exhaustion is a RATE LIMIT, not a terminal fuse (the old 'not
    resetting', forever, left a persistently wedged box stale for good): after
    RECOVERY_BUDGET_COOLDOWN_S of uptime one more reset is allowed, without
    incrementing past the cap — each further trickle reset needs another
    cooldown's worth of uptime."""
    app = _check_app(mock_http_client, settings_factory, tmp_path)
    app._write_recovery_reset_count(app.RECOVERY_RESET_BUDGET)

    for _ in range(app.WEDGE_STRIKES_MAX - 1):
        assert app.note_wedge_strike("check", EBUSY) is False
    assert app.note_wedge_strike("check", EBUSY) is False   # exhausted + young

    app._uptime_s = lambda: app.RECOVERY_BUDGET_COOLDOWN_S + 1
    for _ in range(app.WEDGE_STRIKES_MAX - 1):
        assert app.note_wedge_strike("check", EBUSY) is False
    assert app.note_wedge_strike("check", EBUSY) is True    # cooled-down trickle
    assert app._read_recovery_reset_count() == app.RECOVERY_RESET_BUDGET


# --- /safemode.py: the CircuitPython-safe-mode escape hatch -------------------

def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_safemode(reason="WATCHDOG", nvm=None):
    """Exec /safemode.py with stubbed CircuitPython modules; return the stubs.

    The file is module-level code that runs INSTEAD of code.py in CP safe mode,
    so the test executes it the same way, with time/microcontroller/supervisor/
    wifi replaced by recorders."""
    import sys
    import types
    from unittest.mock import patch

    sleeps = []
    fake_time = types.ModuleType("time")
    fake_time.sleep = lambda s: sleeps.append(s)

    resets = []
    fake_mc = types.ModuleType("microcontroller")
    fake_mc.nvm = nvm
    fake_mc.reset = lambda: resets.append(True)

    class _Reason:
        def __init__(self, name):
            self._name = name
        def __repr__(self):
            return "supervisor.SafeModeReason.%s" % self._name
        __str__ = __repr__

    class _SafeModeReason:
        USER = _Reason("USER")
        WATCHDOG = _Reason("WATCHDOG")

    fake_sup = types.ModuleType("supervisor")
    fake_sup.SafeModeReason = _SafeModeReason
    fake_sup.runtime = types.SimpleNamespace(
        safe_mode_reason=getattr(_SafeModeReason, reason, _Reason(reason)))

    fake_wifi = types.ModuleType("wifi")
    fake_wifi.radio = types.SimpleNamespace(enabled=True)

    with open(os.path.join(_repo_root(), "safemode.py")) as f:
        source = f.read()
    mods = {"time": fake_time, "microcontroller": fake_mc,
            "supervisor": fake_sup, "wifi": fake_wifi}
    with patch.dict(sys.modules, mods):
        exec(compile(source, "safemode.py", "exec"), {"__name__": "safemode"})
    return types.SimpleNamespace(sleeps=sleeps, resets=resets, nvm=nvm,
                                 wifi=fake_wifi)


def test_safemode_escape_ladder_never_parks():
    """The core invariant: a non-USER safe mode ALWAYS reboots back into the
    app — fast at first, then on an escalating delay, forever. The old
    park-at-5 turned five transient watchdog bites into a dark brick."""
    nvm = bytearray(256)
    r1 = _run_safemode(nvm=nvm)
    assert r1.resets == [True]
    assert 10 in r1.sleeps                    # resets 1-5: 10 s
    assert nvm[240] == 0x5A and nvm[241] == 1

    nvm[241] = 7
    r2 = _run_safemode(nvm=nvm)
    assert r2.resets and 60 in r2.sleeps      # resets 6-10: 60 s
    assert nvm[241] == 8

    nvm[241] = 30
    r3 = _run_safemode(nvm=nvm)
    assert r3.resets and 900 in r3.sleeps     # 11+: 15 min — and STILL resets
    assert nvm[241] == 31

    nvm[241] = 255
    r4 = _run_safemode(nvm=nvm)
    assert r4.resets, "must keep rebooting even at the counter cap"
    assert nvm[241] == 255                    # saturates, never wraps


def test_safemode_escape_respects_user_request():
    """Deliberate (button) safe mode is the ONE respected park."""
    nvm = bytearray(256)
    r = _run_safemode(reason="USER", nvm=nvm)
    assert r.resets == []
    assert r.sleeps == []


def test_safemode_escape_cold_resets_radio_off():
    """Warm-radio law: the escape reset must drop the radio first, or wedged
    WiFi-driver state rides into the next session (errno-16 connect failures)."""
    r = _run_safemode(nvm=bytearray(256))
    assert r.wifi.radio.enabled is False


def test_safemode_escape_survives_missing_nvm():
    """No NVM (or a too-small one) still reboots — the counter is best-effort,
    the escape is not."""
    r = _run_safemode(nvm=None)
    assert r.resets == [True]


def test_nvm_layout_reserves_safemode_bytes():
    """The safemode counter bytes are hand-coordinated across three places
    (safemode.py, app._clear_safemode_streak, the diagnostics ledger's size) —
    pin them together so layout drift can't silently corrupt the escape hatch."""
    from scrollkit.utils.diagnostics import _SIZE, SAFEMODE_RESERVED_START
    assert SAFEMODE_RESERVED_START == 240
    assert _SIZE <= SAFEMODE_RESERVED_START, "diagnostics ledger grew into the reserved range"
    with open(os.path.join(_repo_root(), "safemode.py")) as f:
        src = f.read()
    assert "_OFF_MAGIC = 240" in src and "_OFF_COUNT = 241" in src
    with open(os.path.join(_repo_root(), "src", "app.py")) as f:
        appsrc = f.read()
    assert "nvm[240]" in appsrc and "nvm[241]" in appsrc


async def test_boot_fetch_counts_as_fetch_success(
        mock_http_client, settings_factory, tmp_path):
    """The boot-time fetch in setup() must feed the fetch accounting: without
    this, 'Last fetch OK' reads '(never)' for the first 10 min after EVERY
    reboot while the panel shows fresh data (seen live 2026-07-17) — a misread
    factory during reboot churn."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    app = _check_app(mock_http_client, settings_factory, tmp_path)

    calls = []

    class _Diag:
        def note_fetch_result(self, ok, consecutive_failures=0, rearm=None):
            calls.append(("fetch", ok))
        def note_clean_run(self):
            calls.append(("clean",))
        def record_boot(self, reason="UNKNOWN"):
            return self
        def record_crash(self, message):
            calls.append(("crash", message))
        safe_mode = False
        def summary(self):
            return {}
    app.diagnostics = _Diag()

    await app._initialize_display()
    await app.setup()

    assert ("fetch", True) in calls, "boot fetch success must reach diagnostics"
    assert app.seconds_since_last_refresh_success() is not None, \
        "boot fetch must stamp the session success time"


# --- OTA provenance marker (2026-07-20) ---------------------------------------
# install_pending() reboots on success and never returns, so the pre-apply
# version must be stamped to flash BEFORE the apply or the "came from" fact is
# lost. The diagnostics row proves an OTA replaced running CODE — a version
# string alone only proves the .version file landed.

def test_update_source_reports_ota_transition(tmp_path, monkeypatch):
    from src import ota_glue
    marker = str(tmp_path / "last_ota")
    monkeypatch.setattr(ota_glue, "LAST_UPDATE_PATH", marker)

    # No stamp yet: the build arrived some other way.
    assert "USB" in ota_glue.describe_update_source("3.5.20")

    # Stamped before an apply that then changed the running version.
    ota_glue.note_pre_update_version("3.5.19")
    assert ota_glue.read_pre_update_version() == "3.5.19"
    assert ota_glue.describe_update_source("3.5.20") == "OTA (3.5.19 -> 3.5.20)"

    # Stamped, but the version never moved (apply failed / rolled back).
    assert "unchanged" in ota_glue.describe_update_source("3.5.19")


def test_pre_update_stamp_survives_unwritable_fs(tmp_path, monkeypatch):
    """A read-only filesystem (USB-deploy mode) must not break the boot path."""
    from src import ota_glue
    monkeypatch.setattr(ota_glue, "LAST_UPDATE_PATH", "/definitely/not/writable/x")
    ota_glue.note_pre_update_version("3.5.19")        # must not raise
    assert ota_glue.read_pre_update_version() is None
