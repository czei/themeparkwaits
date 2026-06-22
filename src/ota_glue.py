"""OTA glue — wires scrollkit.ota.OTAClient to the app (T027).

Public-branch model (T005/research D8): no device-side token. The release lives
on a public `releases` branch as `manifest.json` + `files/<device-path>` (built
by scripts/make_manifest.py). Flow:

  * web `/update` (or a boot check) -> ``schedule_update()`` checks + downloads to
    /updates, then the caller reboots;
  * on next boot ``setup()`` -> ``install_pending()`` applies the staged update
    (backup -> install -> reboot) with "Installing… do not unplug" on the display.

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

import os

# The release repo (public, single repo for dev + releases — T005).
# NOTE: GitHub renamed Czeiszperger/themeparkwaits.release -> czei/themeparkwaits.
# raw.githubusercontent.com does NOT follow renames, so this must be the CURRENT name.
# The device reads a FIXED channel branch `live` (the hybrid OTA model): publish a
# release by creating a `release-MAJOR.MINOR` branch, then CI/script mirrors its
# manifest.json + files/ onto `live` (kept distinct from the `release-*` archives
# to avoid the releases/release-2.1 name clash). `live` must exist + be public.
DEFAULT_OWNER = "czei"
DEFAULT_REPO = "themeparkwaits"
DEFAULT_BRANCH = "live"


def read_current_version(default="0.0.0"):
    """Read the shipped version from src/.version."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, ".version")) as f:
            return f.read().strip() or default
    except OSError:
        return default


class OTAGlue:
    """Thin wrapper over OTAClient with display progress + a staged-install flow."""

    def __init__(self, current_version=None, *, owner=DEFAULT_OWNER, repo=DEFAULT_REPO,
                 branch=DEFAULT_BRANCH, display=None):
        from scrollkit.ota.client import OTAClient
        self.current_version = current_version or read_current_version()
        self.client = OTAClient.for_github(owner, repo, branch=branch,
                                           current_version=self.current_version)
        self.display = display
        self._last_msg = None
        self.client.set_callbacks(on_progress=self._on_progress, on_error=self._on_error)

    def attach_display(self, display):
        self.display = display

    # ---- callbacks (sync; the OTAClient calls these) ----
    def _on_progress(self, message, progress):
        self._last_msg = message
        print("OTA: %s (%.0f%%)" % (message, (progress or 0) * 100))

    def _on_error(self, message):
        print("OTA error:", message)

    # ---- staged install flow ----
    def has_pending(self):
        """True if an update has been downloaded to the staging dir."""
        return os.path.exists("%s/manifest.json" % self.client.update_dir)

    def schedule_update(self):
        """Check for + download a newer release. Returns True if one is staged.

        Synchronous (callable from the web request thread). The caller reboots so
        ``install_pending()`` applies it on the next boot.
        """
        try:
            has_update, info = self.client.check_for_updates()
            if not has_update:
                return False
            ok, _err = self.client.download_update(info)
            return bool(ok)
        except Exception as e:  # never crash the request/app
            print("OTA schedule failed:", e)
            return False

    async def install_pending(self):
        """If an update is staged, show progress, apply it, and reboot. Returns bool."""
        if not self.has_pending():
            return False
        await self._show("Installing update... Do not unplug!")
        try:
            ok, err = self.client.apply_update()
        except Exception as e:
            print("OTA apply failed:", e)
            return False
        if ok:
            await self._show("Update complete! Rebooting...")
            self.client.reboot_device()
            return True
        print("OTA apply error:", err)
        return False

    async def _show(self, text):
        if not self.display:
            return
        try:
            await self.display.clear()
            await self.display.draw_text(text, 1, 12, 0xFFAA00)
            await self.display.show()
        except Exception:
            pass
