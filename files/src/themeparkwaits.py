"""ThemeParkWaits bootstrap — sets import paths, then runs the app.

On CircuitPython, the device's vendored libraries live in ``/src/lib`` and
``/lib`` (the latter also holds the deployed ``scrollkit`` package). On desktop,
the sibling ``../ScrollKit Library/src`` and this repo are added so
``python -m src.themeparkwaits --dev`` runs without a manual PYTHONPATH.

Copyright (c) 2024-2026 Michael Czeiszperger
"""
import os
import sys

is_circuitpython = hasattr(sys, "implementation") and sys.implementation.name == "circuitpython"

if is_circuitpython:
    for _p in ("/src/lib", "/lib"):
        if _p not in sys.path:
            sys.path.append(_p)
    # --- warm-boot normalization (ledger, 2026-07-16) -----------------------
    # A HARDWARE reset (RESET button, watchdog bite) cannot run radio-off code
    # first, so it can carry warm radio state into this session — which then
    # degrades until every new outbound connect fails OSError 16. Fix: detect
    # those reset reasons at the earliest possible moment (before any WiFi
    # join) and perform ONE radio-off cold reset, giving the operational
    # session the verified-healthy radio-off-before-reset start.
    # Loop safety, twice over: (1) the follow-up reset reads SOFTWARE and
    # skips this block; (2) a marker file records the attempt, so even if the
    # reset reason unexpectedly persisted we continue instead of looping.
    # If the marker can't be written (FS is read-only to the device = a
    # USB-deploy session), skip entirely — never fight a deploy.
    try:
        import microcontroller
        _rr = microcontroller.cpu.reset_reason
        _warm = _rr in (microcontroller.ResetReason.RESET_PIN,
                        microcontroller.ResetReason.WATCHDOG)
        _MARKER = "/warm_boot_normalized"
        if _warm:
            try:
                import os
                os.stat(_MARKER)          # marker present: we already tried
                os.remove(_MARKER)
                print("boot: reset reason still %s after normalization — continuing" % _rr)
            except OSError:
                try:
                    with open(_MARKER, "w") as _f:
                        _f.write("1\n")
                except OSError:
                    print("boot: warm reset (%s) but FS read-only — skipping normalization" % _rr)
                else:
                    print("boot: hardware reset (%s) — one cold reset for a clean radio" % _rr)
                    try:
                        import wifi
                        wifi.radio.enabled = False
                    except Exception:
                        pass
                    import time
                    time.sleep(0.5)
                    microcontroller.reset()
        else:
            try:                          # healthy boot: clear any stale marker
                import os
                os.remove(_MARKER)
            except OSError:
                pass
    except Exception as _e:
        print("boot normalization skipped:", _e)
else:
    # Desktop dev: make the sibling ScrollKit library + repo root importable.
    _here = os.path.dirname(os.path.abspath(__file__))   # .../themeparkwaits/src
    _repo = os.path.dirname(_here)                        # .../themeparkwaits
    _workspace = os.path.dirname(_repo)                   # .../ScrollKit
    # The library checkout may be named "ScrollKit Library" (the author's) or
    # "scrollkit" (a fresh `git clone`); PYTHONPATH overrides both.
    for _p in (_repo,
               os.path.join(_workspace, "ScrollKit Library", "src"),
               os.path.join(_workspace, "scrollkit", "src")):
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
    # Vendored bundle APPENDED (never inserted): src/lib carries an asyncio/
    # tree that must lose to the stdlib on desktop; appending still lets pure
    # python vendored modules (adafruit_json_stream) import in the simulator.
    _bundle = os.path.join(_here, "lib")
    if os.path.isdir(_bundle) and _bundle not in sys.path:
        sys.path.append(_bundle)

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
        # scrollkit.utils.diagnostics catches a DETERMINISTIC crash — after a few
        # fault reboots it drops into safe mode instead of resetting forever — so
        # this can't spin. The cause is shown on the config web UI after recovery.
        try:
            import traceback
            from scrollkit.utils.diagnostics import open as open_diagnostics
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
            # Radio off first (inline — don't trust library imports in a crash
            # handler): a warm-radio reset degrades the next session's outbound
            # connects (EBUSY; ledger 2026-07-15).
            import wifi
            wifi.radio.enabled = False
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
