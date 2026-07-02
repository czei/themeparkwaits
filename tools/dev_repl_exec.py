# Copyright (c) 2024-2026 Michael Czeiszperger
"""Run a diagnostic code block on the CircuitPython board via the raw REPL."""
import time
import serial

PORT = "/dev/cu.usbmodem84722EB3564F1"

CODE = b'''
import displayio
o = displayio.OnDiskBitmap("src/images/rides/space_mountain.bmp")
ps = o.pixel_shader
print("len", len(ps))
try:
    print("get0", hex(ps[0]), "get1", hex(ps[1]))
except Exception as e:
    print("getitem err", repr(e))
try:
    ps[1] = 0x010203
    print("setitem OK")
except Exception as e:
    print("setitem err", repr(e))
print("has get_rgb888", hasattr(ps, "get_rgb888"))
'''


def drain(ser, secs):
    out = b""
    end = time.monotonic() + secs
    while time.monotonic() < end:
        b = ser.read(512)
        if b:
            out += b
            end = time.monotonic() + 0.4   # extend while data flows
    return out


def wait_for(ser, marker, secs):
    out = b""
    end = time.monotonic() + secs
    while time.monotonic() < end:
        b = ser.read(256)
        if b:
            out += b
            if marker in out:
                return out, True
    return out, False


ser = serial.Serial(PORT, 115200, timeout=0.3)
ser.write(b"\r\x03\x03")                 # interrupt running code
drain(ser, 1.5)
ser.write(b"\r")
wait_for(ser, b">>>", 4)                 # friendly prompt
ser.reset_input_buffer()
ser.write(b"\x01")                       # enter raw REPL
_, ok = wait_for(ser, b"raw REPL", 4)
ser.reset_input_buffer()
ser.write(CODE)
ser.write(b"\x04")                       # execute
out = drain(ser, 12)
ser.write(b"\x02")                       # exit raw REPL
text = out.decode("utf-8", "replace")
print("=== entered_raw:", ok, "===")
# raw-REPL result: 'OK' <stdout> \x04 <stderr> \x04>
body = text
if "OK" in body:
    body = body.split("OK", 1)[1]
parts = body.split("\x04")
print("--- stdout ---")
print(parts[0].strip())
if len(parts) > 1 and parts[1].strip():
    print("--- stderr ---")
    print(parts[1].strip())
ser.close()
