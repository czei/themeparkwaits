"""On-device crash/boot diagnostics, persisted in ``microcontroller.nvm``.

Why this exists: the previous field release went black with no usable logs — the
log filled flash and was wiped on every reboot, so a crash erased its own
evidence. NVM survives BOTH soft resets and power loss and is independent of the
filesystem, so a compact fixed-size record here lets us:

  * **break a reboot loop** from a deterministic fault (bad settings, an API
    change that crashes every boot): after a few fault-resets with no clean run,
    drop into *safe mode* (no fetch; keep the config web UI up) instead of
    resetting forever;
  * **explain "why it went black"** on the config web UI without a serial cable
    (reset reason, last exception, consecutive failures, last success).

NVM is wear-limited, so we write SPARINGLY: once per boot and only on state
changes (first clean run, a crash) — never per refresh.

The store takes an injectable ``backend`` (anything that behaves like a mutable
``bytearray``) so the boot-loop logic is unit-tested on desktop; on hardware the
backend is ``microcontroller.nvm``. On desktop with no NVM, ``open()`` returns a
no-op store so callers never need platform checks.
"""

# Fixed binary layout at the head of NVM. Tiny and stable; bump _VERSION if it
# changes (a version/magic mismatch resets the record).
_MAGIC = 0x7A
_VERSION = 1

_OFF_MAGIC = 0
_OFF_VERSION = 1
_OFF_BOOT_COUNT = 2          # 2 bytes, wraps
_OFF_RAPID_BOOTS = 4         # 1 byte: boots since the last clean run
_OFF_RESET_REASON = 5        # 1 byte: code from _REASON_CODES
_OFF_CONSEC_FAILS = 6        # 1 byte: consecutive fetch failures (last known)
_OFF_FLAGS = 7              # 1 byte: bit0 = entered safe mode last boot
_OFF_MSG_LEN = 8           # 1 byte
_OFF_MSG = 9               # ascii crash/exception text
MSG_MAX = 180
_SIZE = _OFF_MSG + MSG_MAX

# After this many resets with no intervening clean run, enter safe mode.
RAPID_BOOT_LIMIT = 4

_FLAG_SAFE_MODE = 0x01

# microcontroller.ResetReason names we care about -> small codes (and back, for
# display). Stored as a code so we don't depend on the enum at read time.
_REASON_NAMES = ("UNKNOWN", "POWER_ON", "BROWNOUT", "SOFTWARE",
                 "DEEP_SLEEP_ALARM", "RESET_PIN", "WATCHDOG")


class Diagnostics:
    """Compact NVM-backed boot/crash record. All methods are failure-tolerant."""

    def __init__(self, backend):
        self._nvm = backend
        # Per-boot snapshot, filled by record_boot().
        self.boot_count = 0
        self.rapid_boots = 0
        self.reset_reason = "UNKNOWN"
        self.safe_mode = False
        self.last_message = ""
        self.consecutive_failures = 0

    # --- low-level helpers ---------------------------------------------------
    def _read(self):
        try:
            n = self._nvm
            if n is None or len(n) < _SIZE:
                return None
            if n[_OFF_MAGIC] != _MAGIC or n[_OFF_VERSION] != _VERSION:
                return None
            return bytes(n[0:_SIZE])
        except Exception:
            return None

    def _write_byte(self, offset, value):
        try:
            self._nvm[offset] = value & 0xFF
        except Exception:
            pass

    def _write_u16(self, offset, value):
        try:
            self._nvm[offset] = value & 0xFF
            self._nvm[offset + 1] = (value >> 8) & 0xFF
        except Exception:
            pass

    def _init_blank(self):
        try:
            self._nvm[_OFF_MAGIC] = _MAGIC
            self._nvm[_OFF_VERSION] = _VERSION
            for off in (_OFF_BOOT_COUNT, _OFF_BOOT_COUNT + 1, _OFF_RAPID_BOOTS,
                        _OFF_RESET_REASON, _OFF_CONSEC_FAILS, _OFF_FLAGS,
                        _OFF_MSG_LEN):
                self._nvm[off] = 0
        except Exception:
            pass

    # --- public API ----------------------------------------------------------
    def record_boot(self, reset_reason_name="UNKNOWN"):
        """Call once at the very start of boot. Increments counters, classifies
        whether we're in a reboot loop, and returns ``self`` for chaining.

        ``reset_reason_name`` is the ``microcontroller.cpu.reset_reason`` name
        (the caller reads it; we just store the code so the web UI can show it)."""
        raw = self._read()
        if raw is None:
            self._init_blank()
            raw = self._read() or bytes(_SIZE)

        self.boot_count = (raw[_OFF_BOOT_COUNT] | (raw[_OFF_BOOT_COUNT + 1] << 8)) + 1
        # A fault reset (watchdog/software/brownout) with no clean run since the
        # last boot is what we count toward a loop; a clean power-on shouldn't.
        self.rapid_boots = raw[_OFF_RAPID_BOOTS] + 1
        self.reset_reason = reset_reason_name
        self.consecutive_failures = raw[_OFF_CONSEC_FAILS]
        msg_len = min(raw[_OFF_MSG_LEN], MSG_MAX)
        try:
            self.last_message = bytes(raw[_OFF_MSG:_OFF_MSG + msg_len]).decode("ascii")
        except Exception:
            self.last_message = ""

        self.safe_mode = self.rapid_boots > RAPID_BOOT_LIMIT

        self._write_u16(_OFF_BOOT_COUNT, self.boot_count)
        self._write_byte(_OFF_RAPID_BOOTS, min(self.rapid_boots, 255))
        try:
            self._write_byte(_OFF_RESET_REASON, _REASON_NAMES.index(reset_reason_name))
        except (ValueError, Exception):
            self._write_byte(_OFF_RESET_REASON, 0)
        flags = _FLAG_SAFE_MODE if self.safe_mode else 0
        self._write_byte(_OFF_FLAGS, flags)
        return self

    def note_clean_run(self):
        """Call once the device is healthy (first successful fetch / stable run).
        Zeroes the reboot-loop counter so transient single crashes never
        accumulate into safe mode."""
        self.rapid_boots = 0
        self._write_byte(_OFF_RAPID_BOOTS, 0)

    def note_fetch_result(self, ok, consecutive_failures=0):
        """Record refresh outcome (state-change only — cheap). A success also
        counts as a clean run."""
        self.consecutive_failures = 0 if ok else consecutive_failures
        self._write_byte(_OFF_CONSEC_FAILS, min(self.consecutive_failures, 255))
        if ok:
            self.note_clean_run()

    def record_crash(self, message):
        """Persist the last fatal exception text (truncated) before a reset."""
        try:
            text = "".join(c for c in str(message) if 32 <= ord(c) < 128)[:MSG_MAX]
            data = text.encode("ascii")
            self._write_byte(_OFF_MSG_LEN, len(data))
            for i, b in enumerate(data):
                self._nvm[_OFF_MSG + i] = b
            self.last_message = text
        except Exception:
            pass

    def summary(self):
        """Dict for the config web UI / logs."""
        return {
            "boot_count": self.boot_count,
            "reboot_streak": self.rapid_boots,
            "reset_reason": self.reset_reason,
            "safe_mode": self.safe_mode,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_message,
        }


class _NullDiagnostics(Diagnostics):
    """No-op store for desktop / when NVM is unavailable."""
    def __init__(self):
        super().__init__(None)

    def record_boot(self, reset_reason_name="UNKNOWN"):
        return self

    def note_clean_run(self):
        pass

    def note_fetch_result(self, ok, consecutive_failures=0):
        pass

    def record_crash(self, message):
        pass


def read_reset_reason():
    """Return the microcontroller reset-reason NAME, or 'UNKNOWN' off-device."""
    try:
        import microcontroller
        return str(microcontroller.cpu.reset_reason).rsplit(".", 1)[-1]
    except Exception:
        return "UNKNOWN"


def open():
    """Return a Diagnostics bound to NVM on hardware, else a no-op store."""
    try:
        import microcontroller
        nvm = microcontroller.nvm
        if nvm is not None and len(nvm) >= _SIZE:
            return Diagnostics(nvm)
    except Exception:
        pass
    return _NullDiagnostics()
