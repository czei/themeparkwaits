"""OTA glue — wires scrollkit.ota.OTAClient to the app (T027).

Public-branch model (T005/research D8): no device-side token. The device reads a
fixed public `live` channel branch as `manifest.json` + `files/<device-path>`
(published by scripts/publish.sh; see RELEASING.md). Flow:

  * web `/update` (or a boot check) -> ``schedule_update()`` checks + downloads to
    /updates, then the caller reboots;
  * on next boot ``setup()`` -> ``install_pending()`` applies the staged update
    (backup -> install -> reboot) with "Installing… do not unplug" on the display.

Copyright (c) 2024-2026 Michael Winslow Czeiszperger
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
    """Read the shipped version from src/.version.

    Uses string ops, not ``os.path`` — CircuitPython's ``os`` has no ``path``
    submodule (this ran on desktop but raised ``AttributeError`` on the device).
    """
    here = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
    try:
        with open(here + "/.version") as f:
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
        """True if an update has been downloaded to the staging dir.

        ``os.stat`` (not ``os.path.exists``) — CircuitPython has no ``os.path``.
        """
        try:
            os.stat("%s/manifest.json" % self.client.update_dir)
            return True
        except OSError:
            return False

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
        await self._show(["Installing", "DO NOT", "UNPLUG!"])
        try:
            ok, err = self.client.apply_update()
        except Exception as e:
            print("OTA apply failed:", e)
            return False
        if ok:
            await self._show(["Updated!", "Reboot..."])
            self.client.reboot_device()
            return True
        print("OTA apply error:", err)
        return False

    async def _show(self, lines, color=0xFFAA00):
        """Paint a short multi-line status frame, vertically centered.

        Keep each line <= ~10 chars: the 64px panel fits ~10 at the default font,
        so the old single-line "Installing update... Do not unplug!" ran off the
        edge and clipped — exactly the message the user must be able to read. The
        install is one blocking call (no display loop), so a horizontal scroll
        couldn't animate; stacked short lines keep it legible. ``lines`` may be a
        single string. Defensive — never raises into the OTA flow.
        """
        if not self.display:
            return
        if isinstance(lines, str):
            lines = [lines]
        try:
            await self.display.clear()
            line_h = 9                      # ~8px glyphs + 1px gap
            height = getattr(self.display, "height", 32)
            top = max(0, (height - len(lines) * line_h) // 2)
            for i, line in enumerate(lines):
                # draw_text y is the BASELINE; sit it near the bottom of each band.
                await self.display.draw_text(line, 1, top + i * line_h + 7, color)
            await self.display.show()
        except Exception:
            pass
