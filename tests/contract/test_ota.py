# Copyright (c) 2024-2026 Michael Czeiszperger
"""T026/T027 — OTA manifest generation + glue construction (no network)."""
import hashlib
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def test_manifest_excludes_private_and_hashes(tmp_path):
    from scripts.make_manifest import build_manifest

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hi')")
    (src / "secrets.py").write_text("WIFI='x'")        # must NOT ship
    (src / "settings.json").write_text("{}")           # must NOT ship
    (src / "error_log").write_text("oops")             # must NOT ship
    sub = src / "models"
    sub.mkdir()
    (sub / "x.py").write_text("X=1")
    out = tmp_path / "out"

    m = build_manifest(str(src), str(out), device_root="/src", version="1.96")

    assert m["version"] == "1.96"
    keys = set(m["files"])
    assert "/src/app.py" in keys
    assert "/src/models/x.py" in keys
    assert "/src/secrets.py" not in keys
    assert "/src/settings.json" not in keys
    assert "/src/error_log" not in keys

    body = b"print('hi')"
    assert m["files"]["/src/app.py"]["checksum"] == hashlib.sha256(body).hexdigest()
    assert m["files"]["/src/app.py"]["size"] == len(body)
    # payload mirrored under files/<device-path>
    assert (out / "files" / "src" / "app.py").read_bytes() == body
    assert (out / "manifest.json").exists()


def test_manifest_roundtrips_through_device_validator(tmp_path):
    """THE contract test whose absence shipped the missing-`required` outage:
    the generator (this repo) and validator (scrollkit, frozen on the device)
    live in different repos with no shared schema — the generator's output must
    be accepted by the REAL device-side parser."""
    import json
    from scripts.make_manifest import build_manifest
    from scrollkit.ota.manifest import UpdateManifest

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hi')")
    (src / ".version").write_text("1.96\n")
    out = tmp_path / "out"
    build_manifest(str(src), str(out), device_root="/src", version="1.96")

    data = json.loads((out / "manifest.json").read_text())
    manifest = UpdateManifest.from_dict(data)
    ok, err = manifest.validate()
    assert ok, f"device validator rejected the generated manifest: {err}"
    assert manifest.compare_version("0.0.1") > 0

    # Old fielded validators hard-require the per-file key — keep emitting it.
    assert all(info.get("required") is True for info in data["files"].values())
    assert list(data["files"]) == sorted(data["files"])   # deterministic output
    assert "pre_update_scripts" not in data               # removed exec() surface


def test_ota_glue_constructs_and_reads_version():
    from src.ota_glue import OTAGlue, read_current_version

    g = OTAGlue(current_version="1.95")
    assert g.current_version == "1.95"
    assert g.has_pending() is False                    # nothing staged at /updates
    # read_current_version() reflects whatever src/.version currently holds (don't
    # hardcode a value here — the file is bumped on every release).
    with open(os.path.join(REPO_ROOT, "src", ".version")) as f:
        expected = f.read().strip()
    assert read_current_version() == expected          # reads src/.version


def test_ota_client_uses_injected_session_not_module_get():
    """Regression: on CircuitPython adafruit_requests is Session-based and has NO
    module-level ``get`` — calling ``requests.get`` raised "'module' object has no
    attribute 'get'", so every Check-for-Update silently failed. The OTAClient must
    use the injected session's ``.get`` instead."""
    from scrollkit.ota.client import OTAClient

    class _Resp:
        status_code = 200
        def __init__(self, payload): self._p = payload
        def json(self): return self._p
        def close(self): pass

    class _Session:                                    # has .get; the module does not
        def __init__(self, payload): self.payload, self.calls = payload, []
        def get(self, url, timeout=None):
            self.calls.append(url)
            return _Resp(self.payload)

    sess = _Session({"version": "3.0", "files": {}})
    client = OTAClient.for_github("czei", "themeparkwaits", branch="live",
                                  current_version="1.95", session=sess)
    has_update, info = client.check_for_updates()      # 3.0 > 1.95
    assert has_update is True, info
    # The ~6-byte version.txt fast-path probe fires first (it falls through
    # here: this fake session serves the manifest payload for every URL, and the
    # strict-semver guard rejects that as a version, sending the check on to the
    # manifest).
    assert sess.calls == [
        "https://raw.githubusercontent.com/czei/themeparkwaits/live/version.txt",
        "https://raw.githubusercontent.com/czei/themeparkwaits/live/manifest.json"]


def test_ota_glue_threads_live_http_client_session():
    """OTAGlue must read the HttpClient's CURRENT session at schedule_update time:
    the session is None when the glue is built (it's created during WiFi connect and
    can be rebuilt later), so capturing it at construction would use a dead/None one."""
    from src.ota_glue import OTAGlue

    class _HttpClient:
        def __init__(self): self.session = None        # construction-time state

    http = _HttpClient()
    glue = OTAGlue(current_version="1.95", http_client=http)
    assert glue.client.session is None

    sentinel = object()
    http.session = sentinel                            # WiFi connect (or a rebuild) lands a session
    glue._progress.schedule_update = lambda: "ok"      # don't hit the network/filesystem
    assert glue.schedule_update() == "ok"
    assert glue.client.session is sentinel             # live session was threaded in


def test_ota_glue_checks_against_website_not_github():
    """Ledger attempt #5: the frequent CHECK reads themeparkwaits.com (ECDSA
    chain), never raw.githubusercontent.com (RSA-2048 chain — PK_ALLOC_FAILED
    at runtime)."""
    from src.ota_glue import OTAGlue, DEFAULT_CHECK_URL

    g = OTAGlue(current_version="1.95")
    assert g.client.check_url == DEFAULT_CHECK_URL
    assert "themeparkwaits.com" in DEFAULT_CHECK_URL
    assert "githubusercontent" not in DEFAULT_CHECK_URL


def test_ota_glue_stage_request_lifecycle(tmp_path):
    """/install persists a flag; boot-time staging consumes it exactly once —
    the flag is cleared BEFORE the download attempt so a failed download can
    never become a reboot-download loop."""
    import asyncio
    from src.ota_glue import OTAGlue

    g = OTAGlue(current_version="1.95")
    g.client.update_dir = str(tmp_path / "updates")   # desktop-safe staging dir

    async def _noop():
        pass
    g.show_updating = _noop
    g.show_failed = _noop

    # No request -> no-op.
    assert asyncio.run(g.stage_pending_request()) is False

    assert g.request_stage() is True
    assert g.has_stage_request() is True

    calls = {"n": 0}
    def _fail_stage():
        calls["n"] += 1
        return False
    g.stage_update = _fail_stage

    assert asyncio.run(g.stage_pending_request()) is False
    assert calls["n"] == 1
    assert g.has_stage_request() is False             # consumed: one attempt per request

    # The failed attempt does not resurrect: another boot stages nothing.
    assert asyncio.run(g.stage_pending_request()) is False
    assert calls["n"] == 1

    # A fresh request with a successful download stages.
    assert g.request_stage() is True
    g.stage_update = lambda: True
    assert asyncio.run(g.stage_pending_request()) is True
    assert g.has_stage_request() is False


def test_check_rung3_bounces_radio_then_retries(tmp_path):
    """The warm-radio EBUSY state: eviction can't cure it, a radio bounce can.
    Attempt 1 fails -> evict; attempt 2 fails -> bounce + evict; attempt 3 runs."""
    from src.ota_glue import OTAGlue

    g = OTAGlue(current_version="1.95")
    g.client.update_dir = str(tmp_path)
    attempts = {"n": 0}
    def _failing_check():
        attempts["n"] += 1
        return (False, "Update check failed: OSError: 16")
    g.client.check_for_updates = _failing_check
    evictions = {"n": 0}
    g._evict_data_sockets = lambda: evictions.__setitem__("n", evictions["n"] + 1) or True
    bounces = {"n": 0}
    class _Wifi:
        def bounce_sync(self):
            bounces["n"] += 1
            return True
    g.wifi_manager = _Wifi()

    ok, version, reason = g.check_update()

    assert ok is False and "OSError: 16" in reason
    assert attempts["n"] == 3                 # all three rungs ran
    assert bounces["n"] == 1                  # exactly one radio bounce
    # evictions: after attempt 1 + after the bounce (the _prep_session eviction
    # is skipped here — this glue has no http_client attached)
    assert evictions["n"] == 2


def test_check_stops_after_two_attempts_without_wifi_manager(tmp_path):
    from src.ota_glue import OTAGlue

    g = OTAGlue(current_version="1.95")
    g.client.update_dir = str(tmp_path)
    attempts = {"n": 0}
    def _failing_check():
        attempts["n"] += 1
        return (False, "Update check failed: OSError: 16")
    g.client.check_for_updates = _failing_check
    g._evict_data_sockets = lambda: True
    assert g.wifi_manager is None             # nothing attached (desktop)

    ok, version, reason = g.check_update()

    assert ok is False
    assert attempts["n"] == 2                 # no rung 3 without a wifi manager
