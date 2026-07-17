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

# The update CHECK reads a ~6-byte version.txt from themeparkwaits.com, NOT
# from raw.githubusercontent.com (ledger attempt #5, 2026-07-15): GitHub raw
# serves an RSA-2048 chain whose mbedtls PK verify needs more internal SRAM
# than the running app has free (OSError -16256 on EVERY check, fresh boot
# included), while themeparkwaits.com is ECDSA P-256 — the same chain shape as
# the park API that has never failed a handshake. publish.sh pushes
# version.txt to the server on every release; the GitHub manifest/files are
# only fetched at EARLY BOOT (see stage_pending_request), where headroom is
# maximal.
DEFAULT_CHECK_URL = "https://themeparkwaits.com/ota/version.txt"


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
                 branch=DEFAULT_BRANCH, display=None, http_client=None,
                 check_url=DEFAULT_CHECK_URL):
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
                                      session=getattr(http_client, "session", None),
                                      check_url=check_url)
        self._progress = OTAProgressDisplay(client, display=display)

    def _heap_probe(self):
        """One-line heap snapshot for the serial log around OTA GETs.

        The espidf calls take NO arguments on CircuitPython (verified on-device
        10.2.1) and report the WHOLE IDF heap including PSRAM — there is no
        internal-SRAM filter. So read them as an upper bound: a TLS handshake
        failing with MemoryError while gc_free and idf_largest both look huge
        means the starved region is the ~320 KB internal SRAM (where mbedtls
        contexts must live; hardware crypto can't touch PSRAM)."""
        import gc
        if not hasattr(gc, "mem_free"):
            return "gc_free=n/a (desktop)"
        parts = ["gc_free=%d" % gc.mem_free()]
        try:
            import espidf
            parts.append("idf_free=%d" % espidf.heap_caps_get_free_size())
            parts.append("idf_largest=%d"
                         % espidf.heap_caps_get_largest_free_block())
        except Exception:
            pass
        return " ".join(parts)

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
        """Point the OTA client at the app's LIVE session. READ-ONLY: never
        rebuild it, never evict its pooled sockets.

        History, because this exact spot has now caused THREE eras of OTA
        failure: (1) it used to call http_client._rebuild_session() before
        every GET — each rebuild orphaned a native socket + mbedtls TLS context
        in internal SRAM until checks died (fixed 2026-07-09 by reusing the one
        session). (2) It then evicted the data session's pooled sockets before
        every check to free SRAM for GitHub's RSA-2048 handshake — but in the
        selective wedge (new outbound connects dead, POOLED park socket alive;
        ledger 2026-07-16) that eviction killed the one connection still
        working, turning a parks-alive box into a parks-dead box. The ECDSA
        check_url made the eviction pointless anyway: the check's handshake is
        as cheap as a park fetch, and the RSA fetches moved to early boot.
        3-model consensus, 2026-07-16: the check must be read-only with respect
        to the data path.
        """
        if self._http_client is None:
            return
        self.client.session = getattr(self._http_client, "session", None)

    def check_update(self):
        """CHECK ONLY: is a newer release on the channel? No download — the caller
        decides whether to install. Returns ``(available, version, message)``; never
        raises. Splitting this out of schedule_update() is what lets the web UI ask
        the user before touching the device (the fused check+download auto-installed)."""
        # Timed on every exit path: a slow click's serial line lands in sequence
        # with the park-refresh log lines, so "the box froze for 30 s" events
        # name their culprit instead of spawning theories.
        import time
        t0 = time.monotonic()
        try:
            return self._check_update_timed()
        finally:
            # Idle with zero open outbound sockets (owner's rule, 2026-07-16):
            # don't leave the check's connection parked in the shared pool —
            # a stale pooled socket masks the wedge and rots across the idle
            # gap. The next check pays one cheap ECDSA handshake instead.
            try:
                closer = getattr(self._http_client, "close_pooled_sockets", None)
                if closer is not None:
                    closer()
            except Exception:
                pass
            print("OTA check took %.1fs" % (time.monotonic() - t0))

    def _check_update_timed(self):
        # ONE attempt, read-only, no recovery. The old 3-rung in-handler ladder
        # (evict -> evict -> radio bounce + session rebuild) blocked the single
        # asyncio loop for 40-45 s, destroyed the pooled park socket the
        # selective wedge had left alive, and — per the soak evidence — never
        # cured the wedge it targeted. Recovery is now out-of-band: the app's
        # note_check_result() counts consecutive failures and escalates to a
        # budgeted cold reset AFTER the HTTP response flushes (the one proven
        # cure). 3-model consensus, 2026-07-16.
        self._prep_session()
        print("OTA check heap:", self._heap_probe())
        # NB: OTAGlue.last_error is a read-only property delegating to _progress, so
        # diagnostics state is set on _progress.last_error (assigning self.last_error
        # raises "no setter").
        self._progress.last_error = None
        try:
            has_update, info = self.client.check_for_updates()
        except Exception as e:  # never crash the request
            has_update, info = False, "check failed: %s" % (e,)
        if has_update:
            return (True, getattr(info, "version", None), "")
        # ``info`` is the reason string. The up-to-date sentinel is the literal
        # "No updates available" (scrollkit.ota.client.UP_TO_DATE). Compare to
        # the LITERAL rather than importing the name: a device running an OLDER
        # library than this app does not export UP_TO_DATE, and a hard import
        # there raises "can't import name UP_TO_DATE" and fails the whole
        # check. The value is stable; the name is not.
        reason = str(info)
        if reason == "No updates available":
            return (False, None, "You're up to date (%s)."
                    % getattr(self.client, "current_version", "?"))
        print("OTA check FAILED, heap: %s" % self._heap_probe())
        # A failed check (fetch/parse/validate) keeps its specific reason, not a lie.
        self._progress.last_error = reason
        return (False, None, reason)

    # ---------------------------------------------------------------- #
    # Boot-time staging (ledger attempt #5)
    #
    # A RUNTIME download from raw.githubusercontent.com dies with mbedtls
    # PK_ALLOC_FAILED (-16256): its RSA-2048 chain needs more internal SRAM
    # than the running app leaves free. So /install no longer downloads —
    # it persists a flag and reboots; setup() calls stage_pending_request()
    # right after network bring-up, BEFORE parks/content/web allocate, where
    # the same handshake provably succeeds (bare-REPL falsification,
    # 2026-07-15). The flag is cleared BEFORE the attempt: one download try
    # per user request, never a failed-download boot loop.
    # ---------------------------------------------------------------- #

    def _stage_request_path(self):
        return self.client.update_dir + "/.stage_request"

    def request_stage(self):
        """Persist the user's install request (the download runs next boot).
        Returns False (never raises) if the flag can't be written."""
        import os
        try:
            try:
                os.mkdir(self.client.update_dir)
            except OSError:
                pass  # already exists (or unwritable — the open below decides)
            with open(self._stage_request_path(), "w") as f:
                f.write("requested\n")
            return True
        except OSError as e:
            print("OTA: could not write stage request:", e)
            return False

    def has_stage_request(self):
        import os
        try:
            os.stat(self._stage_request_path())
            return True
        except OSError:
            return False

    def clear_stage_request(self):
        import os
        try:
            os.remove(self._stage_request_path())
        except OSError:
            pass

    async def stage_pending_request(self):
        """EARLY-BOOT: honor a persisted install request. Returns True if the
        release was downloaded to the staging dir (the caller's existing
        ``install_pending()`` then applies it). Never raises."""
        if not self.has_stage_request():
            return False
        self.clear_stage_request()          # one attempt per request
        try:
            await self.show_updating()
            staged = self.stage_update()
            if not staged:
                print("OTA: boot-time stage failed:", self.last_error)
                await self.show_failed()
            return staged
        except Exception as e:
            print("OTA: boot-time stage crashed:", e)
            return False

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
