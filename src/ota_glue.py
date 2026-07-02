"""OTA glue — app-specific GitHub channel config over the library's OTA adapter.

The display-progress + staged-install mechanism now lives in
``scrollkit.ota.display_progress.OTAProgressDisplay`` (generic, reusable). This
module keeps only what is THIS app's policy:

  * the public release channel (owner/repo/branch), and
  * ``read_current_version()`` reading ``src/.version`` relative to THIS file —
    which must stay in the app, since ``__file__`` resolves to ``src/`` here but
    would point into ``lib/scrollkit/`` if it lived in the library.

Public-branch model (T005/research D8): no device-side token. The device reads a
fixed public `live` channel branch as `manifest.json` + `files/<device-path>`
(published by scripts/publish.sh; see RELEASING.md). Flow:

  * web `/update` (or a boot check) -> ``schedule_update()`` checks + downloads to
    /updates, then the caller reboots;
  * on next boot ``setup()`` -> ``install_pending()`` applies the staged update
    (backup -> install -> reboot) with "Installing… do not unplug" on the display.

Copyright (c) 2024-2026 Michael Czeiszperger
"""
from __future__ import annotations

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
    Stays app-side: ``__file__`` resolves to ``src/`` here (it would point into
    ``lib/scrollkit/`` if this moved into the library).
    """
    here = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
    try:
        with open(here + "/.version") as f:
            return f.read().strip() or default
    except OSError:
        return default


class OTAGlue:
    """Build a GitHub-channel OTAClient and drive it through the library's
    display-progress + staged-install adapter. Thin: config + delegation."""

    def __init__(self, current_version=None, *, owner=DEFAULT_OWNER, repo=DEFAULT_REPO,
                 branch=DEFAULT_BRANCH, display=None, http_client=None):
        from scrollkit.ota.client import OTAClient
        from scrollkit.ota.display_progress import OTAProgressDisplay
        self.current_version = current_version or read_current_version()
        # OTA reuses the app's HttpClient session: on CircuitPython adafruit_requests
        # is Session-based (no module-level get), so the OTAClient needs a Session.
        # The session is created later (during WiFi connect) and can be rebuilt, so
        # we keep the HttpClient and read its live session in schedule_update().
        self._http_client = http_client
        client = OTAClient.for_github(owner, repo, branch=branch,
                                      current_version=self.current_version,
                                      session=getattr(http_client, "session", None))
        self._progress = OTAProgressDisplay(client, display=display)

    @property
    def client(self):
        return self._progress.client

    @property
    def display(self):
        return self._progress.display

    def attach_display(self, display):
        self._progress.attach_display(display)

    def has_pending(self):
        return self._progress.has_pending()

    def schedule_update(self):
        # Pick up the HttpClient's CURRENT session (created during WiFi connect,
        # and possibly rebuilt since this glue was constructed) so the OTA GET uses
        # a live socket pool rather than the None captured at construction time.
        if self._http_client is not None:
            self.client.session = getattr(self._http_client, "session", None)
        return self._progress.schedule_update()

    async def install_pending(self):
        return await self._progress.install_pending()
