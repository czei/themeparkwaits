# Copyright (c) 2024-2026 Michael Winslow Czeiszperger
"""Compatibility shim — NVM boot/crash diagnostics moved into ScrollKit.

The implementation now lives in ``scrollkit.utils.diagnostics`` (it is generic
infrastructure, reusable by any ScrollKit app). This module re-exports it so any
remaining ``from src.diagnostics import ...`` / ``from src import diagnostics``
callers keep working, and so it remains a one-file rollback seam: if the library
copy ever misbehaves on a device, restore the full implementation here.

Active code imports ``scrollkit.utils.diagnostics`` directly.
"""
from scrollkit.utils.diagnostics import *  # noqa: F401,F403  (re-export public API)

# ``import *`` skips underscore-prefixed names; re-export the ones callers/tests use.
from scrollkit.utils.diagnostics import (  # noqa: F401
    _NullDiagnostics, _SIZE, MSG_MAX, RAPID_BOOT_LIMIT, Diagnostics,
    read_reset_reason, open,
)
