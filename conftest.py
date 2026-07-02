# Copyright (c) 2024-2026 Michael Czeiszperger
"""Repo-root pytest shim (loads before pytest configures its plugins).

CircuitPython requires a ``code.py`` at the project root. On desktop, pytest
prepends the repo root to ``sys.path``, so ``import code`` resolves to our
``code.py`` instead of the standard library's ``code`` module — and pytest's
debugging plugin imports ``code`` (via ``pdb``), which would execute our app and
crash collection. Cache the real stdlib ``code`` module before that happens.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))

if "code" not in sys.modules:
    _saved = sys.path[:]
    # Drop any sys.path entry that points at the repo root (incl. "" / ".").
    sys.path = [
        p for p in sys.path
        if p not in ("", ".") and os.path.abspath(p or ".") != _ROOT
    ]
    try:
        import code  # noqa: F401  -> the real stdlib module, now cached
    finally:
        sys.path = _saved

# Ensure the repo root is importable for the `src` package.
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
