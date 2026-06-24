"""T026/T027 — OTA manifest generation + glue construction (no network)."""
import hashlib


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
    assert read_current_version() == "1.95"            # reads src/.version
