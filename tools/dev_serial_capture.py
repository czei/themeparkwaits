"""Capture the CircuitPython serial console for a while, reconnecting across resets.

Usage: python capture_serial.py [seconds] [--reload]
  --reload : send Ctrl-C then Ctrl-D to interrupt + soft-reboot (re-runs code.py)
"""
import sys
import time

import serial

PORT = "/dev/cu.usbmodem84722EB3564F1"
secs = float(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].replace(".", "").isdigit() else 60.0
reload = "--reload" in sys.argv

deadline = time.monotonic() + secs
ser = None
sent_reload = False
while time.monotonic() < deadline:
    try:
        if ser is None:
            ser = serial.Serial(PORT, 115200, timeout=0.4)
            if reload and not sent_reload:
                time.sleep(0.3)
                ser.write(b"\x03")      # Ctrl-C: stop running code
                time.sleep(0.3)
                ser.write(b"\x04")      # Ctrl-D: soft reboot -> re-run code.py
                sent_reload = True
        data = ser.read(4096)
        if data:
            sys.stdout.write(data.decode("utf-8", "replace"))
            sys.stdout.flush()
    except (OSError, serial.SerialException):
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        ser = None
        time.sleep(0.5)               # port dropped (reset) — wait and reopen
print("\n[capture ended after %.0fs]" % secs)
