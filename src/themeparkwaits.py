"""ThemeParkWaits bootstrap — sets import paths, then runs the app.

On CircuitPython, the device's vendored libraries live in ``/src/lib`` and
``/lib`` (the latter also holds the deployed ``scrollkit`` package). On desktop,
the sibling ``../ScrollKit Library/src`` and this repo are added so
``python -m src.themeparkwaits --dev`` runs without a manual PYTHONPATH.

Copyright 2024 3DUPFitters LLC
"""
import os
import sys

is_circuitpython = hasattr(sys, "implementation") and sys.implementation.name == "circuitpython"

if is_circuitpython:
    for _p in ("/src/lib", "/lib"):
        if _p not in sys.path:
            sys.path.append(_p)
else:
    # Desktop dev: make the sibling ScrollKit library + repo root importable.
    _here = os.path.dirname(os.path.abspath(__file__))   # .../themeparkwaits/src
    _repo = os.path.dirname(_here)                        # .../themeparkwaits
    _workspace = os.path.dirname(_repo)                   # .../ScrollKit
    for _p in (_repo, os.path.join(_workspace, "ScrollKit Library", "src")):
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)

import asyncio

try:
    from src.main import main
    print("Starting ThemeParkWaits...")
    asyncio.run(main())
except KeyboardInterrupt:
    print("Interrupted by user")
except Exception as e:  # last-resort: keep a console trace on desktop/device
    print(f"Fatal error running ThemeParkWaits: {e}")
    raise
