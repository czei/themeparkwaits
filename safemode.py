# Copyright (c) 2024-2026 Michael Czeiszperger
"""Safe-mode escape hatch: turn a watchdog bite back into a reboot — forever.

CircuitPython treats a watchdog reset as "your code is broken" and boots into
safe mode WITHOUT running code.py — on a fielded, headless box that means a
dark panel until a human pulls the plug (observed 2026-07-19: a >60 s network
stall bit the 60 s watchdog around 04:00 and the box sat dark until morning).
The watchdog is the app's universal backstop — any network call can hang at
any time — so its bite must end in a reboot into the app, never a parking lot.
This file runs INSTEAD of code.py in safe mode and, for every reason except a
deliberate USER-requested safe mode, resets the board back into the normal
boot path after a delay.

There is NO park limit (design invariant 2026-07-19: nothing ever parks; the
device is a frivolous wait-times display and availability trumps everything).
Instead the delay ESCALATES with the consecutive-reset counter in NVM (bytes
240/241, above the diagnostics ledger — see scrollkit.utils.diagnostics
SAFEMODE_RESERVED_START): fast first, so a transient bite self-heals in
seconds, then backing off so a persistently sick build settles into a slow
forever-retry (dark at most ~15 min per cycle) instead of a fast reboot loop.
The app zeroes the counter after 10 minutes of stable running or a healthy
refresh (ThemeParkApp._clear_safemode_streak).

Before the reset the radio is forced off (warm-radio law: WiFi-driver state
can ride through a bare microcontroller.reset() and poison the next session
with errno-16 connect failures — the reset must be COLD).

Ships with the app as a root file (like boot.py) and is OTA-deliverable
(allowlisted 2026-07-19). Safe mode SKIPS boot.py, so the flash is
host-writable here — this file must never write to the filesystem; NVM only.
"""
import time

import microcontroller
import supervisor

_OFF_MAGIC = 240          # one byte: 0x5A marks the counter as initialized
_OFF_COUNT = 241          # one byte: consecutive safe-mode auto-resets
_MAGIC = 0x5A
DELAYS = ((5, 10), (10, 60))   # (count ceiling, delay s); beyond -> DELAY_MAX_S
DELAY_MAX_S = 900         # slow forever-retry: dark <= 15 min per cycle, never parks


def _delay_for(count):
    """Escalating auto-reset delay: resets 1-5 wait 10 s (a transient watchdog
    bite self-heals in seconds, and the pause is a developer USB window),
    6-10 wait 60 s, and everything after waits 15 min — forever."""
    for ceiling, delay in DELAYS:
        if count <= ceiling:
            return delay
    return DELAY_MAX_S


reason = supervisor.runtime.safe_mode_reason
print("safemode.py: reason =", reason)

# Deliberate (button/user-requested) safe mode is the ONE respected park.
# Prefer the enum identity; fall back to the name for CP versions where the
# enum shape differs.
_user = False
try:
    _user = reason == supervisor.SafeModeReason.USER
except Exception:
    _user = str(reason).upper().endswith("USER")

if _user:
    print("safemode.py: user-requested safe mode - not auto-resetting")
else:
    nvm = microcontroller.nvm
    count = 0
    if nvm is not None and len(nvm) > _OFF_COUNT:
        if nvm[_OFF_MAGIC] != _MAGIC:
            nvm[_OFF_MAGIC] = _MAGIC
            nvm[_OFF_COUNT] = 0
        count = nvm[_OFF_COUNT]
        nvm[_OFF_COUNT] = min(count + 1, 255)   # saturate, never wrap
    count += 1
    delay = _delay_for(count)
    print("safemode.py: auto-reset #%d in %d s - rebooting to the app"
          % (count, delay))
    time.sleep(delay)
    # Warm-radio law: drop the radio before the reset so wedged WiFi-driver
    # state cannot ride into the next session. Best-effort — the radio is
    # usually uninitialized in safe mode and the import may fail; reset anyway.
    try:
        import wifi
        wifi.radio.enabled = False
        time.sleep(0.5)
    except Exception:
        pass
    microcontroller.reset()
