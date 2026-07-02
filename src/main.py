"""ThemeParkWaits — main entry point (ScrollKit port).

Constructs the ScrollKitApp-based application and runs it. The display
auto-detects platform (Matrix Portal S3 hardware vs. desktop simulator) via
the library's UnifiedDisplay, so ``--dev`` is accepted for compatibility but
no longer selects an implementation.

Copyright (c) 2024-2026 Michael Czeiszperger
"""
import asyncio
import sys

is_circuitpython = hasattr(sys, "implementation") and sys.implementation.name == "circuitpython"

if not is_circuitpython:
    import argparse


def _parse_args():
    """Parse args where argparse exists (desktop); default on CircuitPython."""
    if is_circuitpython:
        class _Defaults:
            dev = False
        return _Defaults()
    parser = argparse.ArgumentParser(description="ThemeParkWaits")
    parser.add_argument("--dev", action="store_true",
                        help="(compat) desktop run; the simulator is auto-detected")
    args, _unknown = parser.parse_known_args()
    return args


async def main():
    """Construct and run the application."""
    _parse_args()  # informational; UnifiedDisplay auto-detects the platform
    from src.app import ThemeParkApp
    app = ThemeParkApp()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
