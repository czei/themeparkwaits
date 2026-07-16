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
        # Late-bound by the app after _init_network (WiFi doesn't exist at
        # construction). Enables the check's last rung: a radio bounce — the
        # only cure for the warm-radio EBUSY state (2026-07-15, ledger).
        self.wifi_manager = None

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
        """Point the OTA client at the app's LIVE session — and NEVER rebuild it.

        History, because this exact spot has now caused two eras of OTA failure:
        this used to call http_client._rebuild_session() before every GET (fresh
        SocketPool + TLS context), a defense from the EBUSY socket-leak era.
        That leak was later properly fixed at the source (responses are closed),
        but the rebuild survived — and became the disease: every rebuild drops
        the old pool to the GC WITHOUT native teardown, orphaning its socket and
        its mbedtls TLS context in the ESP32-S3's ~320 KB internal SRAM (TLS
        cannot live in the 2 MB PSRAM — hardware crypto can't reach it). Each
        button press leaked another; the starvation surfaced as
        "MemoryError" (internal SRAM) or "RuntimeError: Out of sockets"
        (global socket table) on the NEXT handshake. Observed live: 2 checks
        passed then 3 consecutive "Out of sockets" as back-to-back checks ate
        the table. Reusing the one long-lived session lets the pooled GitHub
        socket be REUSED instead of leaked. Multi-model consensus + on-device
        falsification, 2026-07-09.
        """
        if self._http_client is None:
            return
        # Evict pooled sockets BEFORE every check, not only on failure: it frees
        # the previous check's GitHub TLS context (~40 KB of internal SRAM)
        # instead of pinning it between checks, and removes the pooled-corpse
        # variable entirely — every check pays one predictable fresh handshake
        # rather than gambling on whether GitHub kept an idle socket alive.
        self._evict_data_sockets()
        import gc
        gc.collect()
        self.client.session = getattr(self._http_client, "session", None)

    def _evict_data_sockets(self):
        """Properly close every socket pooled by the app's data session, freeing
        their native TLS contexts (~40 KB of internal SRAM each) ahead of a
        fresh handshake. This is the consensus 'Phase B': when internal SRAM is
        too tight to allocate the GitHub TLS context alongside the park API's
        (mbedtls -0x3F80 PK_ALLOC_FAILED / OSError -16256), evict the park
        socket first — its fetch loop reconnects on the next 5-minute tick and
        retries 3x, so a miss there is invisible, unlike the user's button.

        Scoped strictly to the DATA pool: the web server builds its own
        SocketPool (config_server.py:16), and connection_manager_close_all is
        per-pool, so the listening socket is untouchable from here. Digs the
        pool out of the session via vendored-bundle internals — acceptable
        because the bundle is USB-frozen (version-locked to this flash)."""
        # Prefer the library's supported API (scrollkit >= the 2026-07-11
        # hygiene fix); fall back to the direct dig for an older on-device lib
        # (releases ship app+lib atomically, so the skew window is boot-time
        # only).
        closer = getattr(self._http_client, "close_pooled_sockets", None)
        if closer is not None:
            ok = bool(closer())
            import gc
            gc.collect()
            if ok:
                print("OTA: evicted data-session sockets (native TLS contexts freed)")
            return ok
        session = getattr(self._http_client, "session", None)
        if session is None:
            return False
        try:
            from adafruit_connection_manager import connection_manager_close_all
            pool = session._connection_manager._socket_pool
            connection_manager_close_all(socket_pool=pool)
            import gc
            gc.collect()
            print("OTA: evicted data-session sockets (native TLS contexts freed)")
            return True
        except Exception as e:
            print("OTA: socket eviction skipped:", e)
            return False

    @staticmethod
    def _is_transient(reason):
        """Allocation-shaped failures worth one evict-and-retry."""
        r = str(reason)
        return ("MemoryError" in r or "Out of sockets" in r or "OSError" in r)

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
            print("OTA check took %.1fs" % (time.monotonic() - t0))

    def _check_update_timed(self):
        self._prep_session()
        print("OTA check heap:", self._heap_probe())
        # NB: OTAGlue.last_error is a read-only property delegating to _progress, so
        # diagnostics state is set on _progress.last_error (assigning self.last_error
        # raises "no setter").
        self._progress.last_error = None
        reason = ""
        for attempt in (1, 2, 3):
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
            print("OTA check FAILED (attempt %d), heap: %s"
                  % (attempt, self._heap_probe()))
            if not self._is_transient(reason):
                break
            # Rung 2 — allocation-shaped first failure: free the park TLS
            # context and give the handshake one more shot with maximum native
            # headroom. The first attempt deliberately doesn't evict — the warm
            # pooled socket is the fast path.
            if attempt == 1:
                self._evict_data_sockets()
                continue
            # Rung 3 — the warm-radio EBUSY state: new outbound connects fail
            # while pooled flows work; eviction can't touch it, only a radio
            # bounce does (verified on hardware 2026-07-15, 3-for-3 both ways).
            # bounce_sync blocks ~3-6 s inside the handler; the check already
            # freezes the display and is timed/logged, so a slow-but-definitive
            # answer beats a fast failure.
            if attempt == 2:
                bounce = getattr(self.wifi_manager, "bounce_sync", None)
                if bounce is None:
                    break  # no wifi manager attached (desktop/tests)
                print("OTA check: bouncing the radio (rung 3)")
                if not bounce():
                    break
                self._evict_data_sockets()  # pooled sockets died with the radio
                continue
            break
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
        self._prep_session()                  # includes the pre-check eviction
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
