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
except Exception as e:  # last-resort recovery
    print(f"Fatal error running ThemeParkWaits: {e}")
    if is_circuitpython:
        # The old code re-raised here, leaving the panel frozen/black until a
        # manual power-cycle. Instead: persist the cause to NVM (survives the
        # reset) and reboot to self-recover. The boot-loop breaker in
        # src/diagnostics catches a DETERMINISTIC crash — after a few fault
        # reboots it drops into safe mode instead of resetting forever — so this
        # can't spin. The cause is shown on the config web UI after recovery.
        try:
            import traceback
            from src.diagnostics import open as open_diagnostics
            try:
                tb = "".join(traceback.format_exception(e))
            except Exception:
                tb = str(e)
            open_diagnostics().record_crash("%s: %s" % (type(e).__name__, tb))
        except Exception as log_err:
            print("crash record failed:", log_err)
        try:
            import time
            time.sleep(3)  # let serial/logs flush; avoid a tight reset cycle
        except Exception:
            pass
        try:
            import microcontroller
            microcontroller.reset()
        except Exception as reset_err:
            print("reset failed:", reset_err)
            raise
    else:
        # Desktop dev: surface the traceback so it's debuggable.
        raise
