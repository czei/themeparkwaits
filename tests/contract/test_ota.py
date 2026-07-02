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
    assert sess.calls == [
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
