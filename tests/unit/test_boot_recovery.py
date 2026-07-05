# Copyright (c) 2024-2026 Michael Czeiszperger
"""boot.py OTA crash recovery — the flash-frozen anchor.

A power cut while an OTA apply rewrote /code.py or /src leaves the app
unparseable (SyntaxError -> REPL), so app-level recovery is unreachable; the
restore must run in boot.py. These tests exec the REAL boot.py with fake
CircuitPython modules and drive ``_ota_recover`` against a tmp_path sandbox.

Marker contract (mirrors scrollkit/ota/client.py):
  /updates/apply_started   = an apply began; the live tree may be torn
  /updates/backup_complete = /backup holds a complete pre-update snapshot
"""
import os
import sys
import types

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOOT_PY = os.path.join(REPO_ROOT, "boot.py")


@pytest.fixture()
def ota_recover(monkeypatch):
    """Exec the real boot.py under fake board/digitalio/storage; return _ota_recover."""

    class _FakePin:
        def __init__(self, pin):
            self.direction = None
            self.pull = None

        @property
        def value(self):
            return True          # pull-up, button NOT pressed

    monkeypatch.setitem(sys.modules, "board",
                        types.SimpleNamespace(BUTTON_DOWN="down", BUTTON_UP="up"))
    monkeypatch.setitem(sys.modules, "digitalio", types.SimpleNamespace(
        DigitalInOut=_FakePin,
        Direction=types.SimpleNamespace(INPUT="input"),
        Pull=types.SimpleNamespace(UP="up")))
    monkeypatch.setitem(sys.modules, "storage",
                        types.SimpleNamespace(remount=lambda *a, **k: None))

    namespace = {}
    with open(BOOT_PY) as f:
        exec(compile(f.read(), BOOT_PY, "exec"), namespace)
    return namespace["_ota_recover"]


def _sandbox(tmp_path, *, live=None, backup=None, staging=()):
    """Lay out live files, backup files, and staging entries under tmp_path."""
    for rel, content in (live or {}).items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    for rel, content in (backup or {}).items():
        p = tmp_path / "backup" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    for name in staging:
        p = tmp_path / "updates" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")


def test_noop_when_no_markers(ota_recover, tmp_path):
    _sandbox(tmp_path, live={"src/app.py": b"LIVE"})
    ota_recover(root=str(tmp_path))
    assert (tmp_path / "src" / "app.py").read_bytes() == b"LIVE"
    assert not (tmp_path / "updates").exists()      # nothing created


def test_restores_backup_when_both_markers(ota_recover, tmp_path):
    _sandbox(
        tmp_path,
        live={"src/app.py": b"TORN", "code.py": b"TORN2"},
        backup={"src/app.py": b"OLD", "code.py": b"OLD2"},
        staging=("manifest.json", "apply_started", "backup_complete"))

    ota_recover(root=str(tmp_path))

    assert (tmp_path / "src" / "app.py").read_bytes() == b"OLD"
    assert (tmp_path / "code.py").read_bytes() == b"OLD2"
    # Staged state fully cleared — no auto-retry of the torn install.
    assert not (tmp_path / "updates" / "manifest.json").exists()
    assert not (tmp_path / "updates" / "apply_started").exists()
    assert not (tmp_path / "updates" / "backup_complete").exists()


def test_skips_when_readonly(ota_recover, tmp_path):
    """DOWN held at boot = filesystem read-only to the device: recovery must not
    attempt writes; state stays put for the next normal boot."""
    _sandbox(
        tmp_path,
        live={"src/app.py": b"TORN"},
        backup={"src/app.py": b"OLD"},
        staging=("manifest.json", "apply_started", "backup_complete"))

    ota_recover(root=str(tmp_path), readonly=True)

    assert (tmp_path / "src" / "app.py").read_bytes() == b"TORN"   # untouched
    assert (tmp_path / "updates" / "apply_started").exists()


def test_leaves_state_when_backup_incomplete(ota_recover, tmp_path):
    """Power cut DURING backup: the live tree was only read, never written — the
    app is intact and install_pending() retries normally."""
    _sandbox(
        tmp_path,
        live={"src/app.py": b"LIVE"},
        staging=("manifest.json", "apply_started"))

    ota_recover(root=str(tmp_path))

    assert (tmp_path / "src" / "app.py").read_bytes() == b"LIVE"
    assert (tmp_path / "updates" / "manifest.json").exists()       # retry allowed
    assert (tmp_path / "updates" / "apply_started").exists()


def test_clears_stale_markers_without_manifest(ota_recover, tmp_path):
    """Leftovers from an interrupted cleanup/rollback (manifest already gone):
    janitor the markers, touch nothing else."""
    _sandbox(
        tmp_path,
        live={"src/app.py": b"LIVE"},
        staging=("apply_started", "backup_complete"))

    ota_recover(root=str(tmp_path))

    assert (tmp_path / "src" / "app.py").read_bytes() == b"LIVE"
    assert not (tmp_path / "updates" / "apply_started").exists()
    assert not (tmp_path / "updates" / "backup_complete").exists()


def test_recovery_is_idempotent(ota_recover, tmp_path):
    """A power cut DURING recovery re-runs it on the next boot."""
    _sandbox(
        tmp_path,
        live={"src/app.py": b"TORN"},
        backup={"src/app.py": b"OLD"},
        staging=("manifest.json", "apply_started", "backup_complete"))

    ota_recover(root=str(tmp_path))
    ota_recover(root=str(tmp_path))    # second run: converged no-op

    assert (tmp_path / "src" / "app.py").read_bytes() == b"OLD"
    assert not (tmp_path / "updates" / "apply_started").exists()
