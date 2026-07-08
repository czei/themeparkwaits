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

    @property
    def last_error(self):
        """Why the last schedule_update() did not stage (None after success)."""
        return getattr(self._progress, "last_error", None)

    def _prep_session(self):
        # The OTA GET opens a TLS context to raw.githubusercontent while the data
        # session holds its own; on the device that double allocation failed the
        # handshake (mbedtls -0x3F80 PK_ALLOC_FAILED). We must reclaim that memory
        # BEFORE the GET, but must NOT use adafruit_connection_manager
        # connection_manager_close_all(): it frees EVERY managed socket globally —
        # including the web server's listening socket (which killed the settings
        # site) and the data session's cached socket, which adafruit_requests then
        # tries to close again -> "RuntimeError: Socket not managed".
        #
        # Instead REBUILD the app's HTTP session: a fresh SocketPool + TLS context
        # discards the old session's socket/TLS (reclaiming the same RAM) and holds
        # NO stale reference to double-free — and touches nothing else, so the web
        # server survives. The data loop reads http_client.session live, so its next
        # fetch transparently uses the new session too.
        if self._http_client is None:
            return
        import sys
        if getattr(sys.implementation, "name", "") == "circuitpython":
            try:
                self._http_client._rebuild_session()
            except Exception as e:
                print("OTA session rebuild skipped:", e)
            import gc
            gc.collect()
        # Pick up the CURRENT session (rebuilt above on device; the one created
        # during WiFi connect on desktop) so the OTA GET uses a live socket pool.
        self.client.session = getattr(self._http_client, "session", None)

    def check_update(self):
        """CHECK ONLY: is a newer release on the channel? No download — the caller
        decides whether to install. Returns ``(available, version, message)``; never
        raises. Splitting this out of schedule_update() is what lets the web UI ask
        the user before touching the device (the fused check+download auto-installed)."""
        self._prep_session()
        # NB: OTAGlue.last_error is a read-only property delegating to _progress, so
        # diagnostics state is set on _progress.last_error (assigning self.last_error
        # raises "no setter").
        self._progress.last_error = None
        try:
            has_update, info = self.client.check_for_updates()
        except Exception as e:  # never crash the request
            msg = "check failed: %s" % (e,)
            self._progress.last_error = msg
            return (False, None, msg)
        if has_update:
            return (True, getattr(info, "version", None), "")
        # ``info`` is the reason string. The up-to-date sentinel is the literal
        # "No updates available" (scrollkit.ota.client.UP_TO_DATE). Compare to the
        # LITERAL rather than importing the name: a device running an OLDER library
        # than this app (the atomic-release mismatch — e.g. app 3.5.2 code against an
        # on-device 0.8.3 that predates the constant) does not export UP_TO_DATE, and
        # a hard ``from ... import UP_TO_DATE`` there raises "can't import name
        # UP_TO_DATE" and fails the whole check. The value is stable; the name is not.
        reason = str(info)
        if reason == "No updates available":
            return (False, None, "You're up to date (%s)."
                    % getattr(self.client, "current_version", "?"))
        # A failed check (fetch/parse/validate) keeps its specific reason, not a lie.
        self._progress.last_error = reason
        return (False, None, reason)

    def stage_update(self):
        """Download the pending release into the staging dir (no reboot). Returns True
        if staged; the caller reboots so ``install_pending()`` applies it next boot.
        Assumes a prior ``check_update()`` found one; ``download_update()`` re-checks
        if needed. Never raises."""
        self._prep_session()
        self._progress.last_error = None      # read-only property on self; set _progress
        try:
            # Re-check to get a FRESH manifest and pass it explicitly, rather than
            # relying on client.available_update from an earlier check (which a session
            # rebuild or an intervening up-to-date check can leave stale/None — then
            # download_update() returns "No update manifest available" silently).
            has_update, info = self.client.check_for_updates()
            if not has_update:
                self._progress.last_error = "stage: no newer release (%s)" % (info,)
                return False
            ok, err = self.client.download_update(info)
            if not ok:
                self._progress.last_error = "download failed: %s" % (err,)
            return bool(ok)
        except Exception as e:
            print("OTA stage failed:", e)
            self._progress.last_error = "stage failed: %s" % (e,)
            return False

    async def show_updating(self):
        """Paint 'Updating / DO NOT / UNPLUG!' on the panel BEFORE the blocking
        download, so the sign shows a clear message instead of freezing mid-content
        (install_pending() shows 'Installing…' later, at apply time). Never raises."""
        try:
            await self._progress._show(["Updating", "DO NOT", "UNPLUG!"])
        except Exception as e:
            print("show_updating skipped:", e)

    async def show_failed(self):
        """Panel message when a staged download fails. Never raises."""
        try:
            await self._progress._show(["Update", "failed"])
        except Exception:
            pass

    def schedule_update(self):
        """Fused check+download in one call (the unattended/boot-check policy). The
        interactive web UI uses check_update()/stage_update() so it can confirm with
        the user first; this stays for any non-interactive caller."""
        self._prep_session()
        return self._progress.schedule_update()

    async def install_pending(self):
        return await self._progress.install_pending()
