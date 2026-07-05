# Copyright (c) 2024-2026 Michael Czeiszperger


import board
import digitalio
import storage
import os
import time


# See if we need to mount the drive read-only on the Matrix S3
# side so the computer side can edit files.
button_pin = board.BUTTON_DOWN  # Change this to the actual pin connected to your button

# Create a digital input object for the button
button = digitalio.DigitalInOut(button_pin)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP  # You may need to adjust the pull direction based on your circuit
# Sampling immediately after enabling the pull-up read a not-yet-charged line as
# LOW — four consecutive hands-free boots "saw" DOWN pressed and mounted the
# drive Mac-writable, so the device could never stage an OTA update. Let the
# line settle, then require a SOLID low (every sample) to enter deploy mode.
time.sleep(0.05)
drive_state = all(not button.value for _ in range(3))

# False makes the USB drive read-only to the computer
# storage.remount("/", False)
print(f"Drive mount logic is: {drive_state}")
storage.remount("/", drive_state)


# ---- OTA crash recovery ------------------------------------------------------
# Power loss while an OTA apply rewrote /code.py or /src can leave the app
# unparseable (SyntaxError -> REPL), so recovery must run HERE, before code.py.
# This file is deliberately NOT shipped OTA: it is the flash-frozen anchor.
# Marker contract (see scrollkit/ota/client.py APPLY_STARTED/BACKUP_COMPLETE):
#   /updates/apply_started   = an apply began; the live tree may be torn
#   /updates/backup_complete = /backup holds a complete pre-update snapshot
def _ota_recover(root="", readonly=False):
    def _exists(p):
        try:
            os.stat(p)
            return True
        except OSError:
            return False

    def _rm(p):
        try:
            os.remove(p)
        except OSError:
            pass

    upd = root + "/updates"
    if not _exists(upd + "/apply_started"):
        return                      # normal boot: total cost is this one os.stat
    if readonly:
        print("OTA recovery needed, but drive is read-only (DOWN held); skipped")
        return
    try:
        has_backup = (_exists(upd + "/backup_complete")
                      and len(os.listdir(root + "/backup")) > 0)
    except OSError:
        has_backup = False
    if has_backup:
        # Interrupted mid-install: roll BACK to the last known-good-running
        # code (never roll forward here — a deterministic install failure
        # would boot-loop in the one layer with no display or safe mode).
        print("OTA: interrupted install detected - restoring backup")

        def _copy(src, dst):        # chunked recursive copy /backup/** -> /**
            for name in os.listdir(src):
                s, d = src + "/" + name, dst + "/" + name
                if os.stat(s)[0] & 0x4000:      # directory bit
                    try:
                        os.mkdir(d)
                    except OSError:
                        pass
                    _copy(s, d)
                else:
                    with open(s, "rb") as fi, open(d, "wb") as fo:
                        while True:
                            buf = fi.read(512)
                            if not buf:
                                break
                            fo.write(buf)

        _copy(root + "/backup", root)   # dst "" -> "/name" absolute paths
        # Staged manifest first (kills the auto-retry), trigger marker last, so
        # a crash DURING recovery converges on a re-runnable state.
        _rm(upd + "/manifest.json")
        _rm(upd + "/backup_complete")
        _rm(upd + "/apply_started")
        print("OTA: restore complete, booting restored app")
    elif not _exists(upd + "/manifest.json"):
        # Leftovers from an interrupted cleanup/rollback — nothing to retry.
        _rm(upd + "/backup_complete")
        _rm(upd + "/apply_started")
    else:
        # Interrupted during backup: the live tree was only READ, never written,
        # so the app is intact and install_pending() will retry normally.
        print("OTA: interrupted before backup completed; app will retry")


_ota_recover(readonly=drive_state)


def remove_file(filename):
    try:
        os.remove(filename)
    except OSError:
        print(f"File {filename} could not be deleted.")

# See if the user wants to reset the Wifi and default settings
button = digitalio.DigitalInOut(board.BUTTON_UP)
if button.value is False:
    remove_file("secrets.py")
    remove_file("settings.json")
    remove_file("error_log")
    # Physical escape hatch for a stuck/looping update transaction.
    remove_file("/updates/manifest.json")
    remove_file("/updates/apply_started")
    remove_file("/updates/backup_complete")


