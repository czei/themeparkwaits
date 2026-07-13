#!/usr/bin/env python3
"""Prepare a USB-attached box for a customer: pre-load parks, strip credentials.

Puts the device in the "gift" state: ``settings.json`` keeps every display
preference and gets the chosen parks, but ``wifi_ssid``/``wifi_password`` and
``secrets.py`` are removed. On its next boot the box finds parks configured but
no credentials, so it opens the WiFi onboarding portal indefinitely (panel
instructions + its own access point) — the customer joins from a phone, and the
portal saves their credentials INTO the existing settings, parks intact.

The device must be in normal run mode (no button held at boot): its own
filesystem is writable then, and this script drives the edit through the serial
REPL — char-paced writes (the board drops characters at full speed), explicit
close() + os.sync(), and a read-back verification of every change (the
unclosed-write lesson of 2026-07-09 is law).

Usage:
    python3 tools/prep_customer_box.py                 # 4 WDW parks (default)
    python3 tools/prep_customer_box.py --parks <uuid>,<uuid>,...
    python3 tools/prep_customer_box.py --keep-wifi     # parks only, keep creds
    python3 tools/prep_customer_box.py --reboot        # boot into the portal now

Copyright (c) 2024-2026 Michael Czeiszperger
"""
import argparse
import glob
import json
import sys
import time

import serial

PACE = 0.02          # s/char — the REPL drops characters when pasted faster

# Walt Disney World's four theme parks (themeparks.wiki UUIDs).
WDW_PARKS = [
    "75ea578a-adc8-4116-a54d-dccb60765ef9",   # Magic Kingdom
    "47f90d2c-e191-4239-a466-5892ef59a88b",   # EPCOT
    "288747d1-8b4f-4a64-867e-ea7c9b27bad8",   # Hollywood Studios
    "1c84a229-8862-4648-9c71-378ddd2c7693",   # Animal Kingdom
]


def _send(ser, line, settle=0.5):
    for ch in line:
        ser.write(ch.encode())
        time.sleep(PACE)
    ser.write(b"\r")
    time.sleep(settle)


def _drain(ser, quiet=1.2):
    out, last = b"", time.time()
    while time.time() - last < quiet:
        chunk = ser.read(4096)
        if chunk:
            out += chunk
            last = time.time()
    return out.decode(errors="replace")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--parks", default=",".join(WDW_PARKS),
                    help="comma-separated park UUIDs (default: the 4 WDW parks)")
    ap.add_argument("--port", default=None,
                    help="serial port (default: first /dev/cu.usbmodem*)")
    ap.add_argument("--keep-wifi", action="store_true",
                    help="only set parks; keep wifi creds and secrets.py")
    ap.add_argument("--reboot", action="store_true",
                    help="reset the box afterwards (boots into the portal)")
    args = ap.parse_args()

    parks = [p.strip() for p in args.parks.split(",") if p.strip()]
    if not parks:
        sys.exit("no park UUIDs given")

    port = args.port or next(iter(glob.glob("/dev/cu.usbmodem*")), None)
    if not port:
        sys.exit("no usbmodem serial port found — is the box attached (normal "
                 "run mode, no button held)?")

    lines = [
        ("pass", 0.4),
        ("import json, os", 0.5),
        ("s = json.load(open('/settings.json'))", 0.8),
        ("s['selected_park_ids'] = %s" % json.dumps(parks), 0.8),
        ("s['current_park_id'] = %s" % json.dumps(parks[0]), 0.5),
    ]
    if not args.keep_wifi:
        lines += [
            ("s.pop('wifi_ssid', None)", 0.4),
            ("s.pop('wifi_password', None)", 0.4),
        ]
    lines += [
        ("f = open('/settings.json', 'w')", 0.4),
        ("n = f.write(json.dumps(s))", 1.0),
        ("f.close()", 1.0),
        ("os.sync()", 1.0),
        ("v = json.load(open('/settings.json'))", 0.8),
        ("print('PREP parks:', len(v['selected_park_ids']), "
         "'| wifi keys present:', 'wifi_ssid' in v)", 0.8),
    ]
    if not args.keep_wifi:
        lines += [
            # One-liner on purpose: multi-line try/except through the raw REPL
            # fights its auto-indent (the `except` line lands indented ->
            # SyntaxError). Short-circuit remove is REPL-safe.
            ("('secrets.py' in os.listdir('/')) and os.remove('/secrets.py')", 0.8),
            ("os.sync()", 1.0),
            ("print('PREP secrets.py present:', 'secrets.py' in os.listdir('/'))", 0.6),
        ]

    ser = serial.Serial(port, 115200, timeout=0.2)
    try:
        ser.write(b"\x03"); time.sleep(0.5)          # interrupt the running app
        ser.write(b"\x03"); time.sleep(0.5)
        _drain(ser, quiet=0.5)
        for line, settle in lines:
            _send(ser, line, settle)
        out = _drain(ser, quiet=1.5)
        results = [l for l in out.splitlines() if l.startswith("PREP")]
        for l in results:
            print(l)
        ok = (any("parks: %d" % len(parks) in l for l in results)
              and (args.keep_wifi
                   or (any("wifi keys present: False" in l for l in results)
                       and any("secrets.py present: False" in l for l in results))))
        if not ok:
            sys.exit("VERIFICATION FAILED — device state unclear; inspect by hand "
                     "before shipping. Raw output:\n" + out)
        if args.reboot:
            _send(ser, "import microcontroller", 0.5)
            _send(ser, "microcontroller.reset()", 0.5)
            print("rebooting — the panel should show the WiFi setup portal")
        else:
            print("done — box is prepped; it enters the setup portal on its next boot")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
