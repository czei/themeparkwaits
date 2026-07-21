"""ThemeParkWaits application — built on the refactored ScrollKit library.

Port milestone A (in progress). ``ThemeParkApp`` extends ``ScrollKitApp``:
``setup()`` runs the pre-run sequence (currently: splash → fetch park list;
WiFi/onboarding/OTA/NTP land in T018/T027), the data process calls
``update_data()`` every ``update_interval`` to refresh wait times and rebuild the
content queue, and the display process renders the queue.

Copyright (c) 2024-2026 Michael Czeiszperger
"""
from __future__ import annotations

import asyncio

from scrollkit.app.base import ScrollKitApp

from scrollkit.utils.error_handler import ErrorHandler

from src.settings_schema import make_settings
from src.api.theme_park_service import ThemeParkService
from src.ui.content_builder import build_content_queue
from scrollkit.utils import diagnostics

logger = ErrorHandler("error_log")


class ThemeParkApp(ScrollKitApp):
    """Theme-park wait-time display application."""

    # Matrix Portal S3 geometry; bit_depth=4 is the recommended fast refresh (FR-022).
    WIDTH = 64
    HEIGHT = 32
    BIT_DEPTH = 4

    # --- WiFi onboarding policy (boot-time; hardware only) --------------------
    # When a boot-time join fails with KNOWN credentials, retry as a station this
    # many times (each a full WiFiManager.connect() = 3 radio attempts) with a
    # growing grace between them BEFORE flipping the radio into setup-AP mode.
    # This is the power-outage self-heal: when mains returns, the sign boots
    # faster than the router's AP, so the first join fails; waiting the router out
    # here reconnects with no portal and no reboot. Tests override to () / (0,).
    WIFI_RECONNECT_BACKOFF_S = (10, 20, 30)
    # How long to hold the setup portal's AP open for a physically-present user to
    # fix a wrong password before rebooting (a slow-to-return router then
    # reconnects on the next boot instead of the sign sitting in setup mode).
    WIFI_PORTAL_TIMEOUT_S = 300

    # --- availability policy (2026-07-19 fault-tolerance redesign) ------------
    # Design invariant: from any state the device returns to a normal-operation
    # attempt within bounded time, forever, with no human intervention.
    # "The app survived this long" IS a clean run: an uptime timer clears the
    # NVM boot-loop counter and /safemode.py's escape-hatch streak, so
    # deliberate reboots (outage auto-reboots, wedge cold resets, watchdog
    # bites) can never accumulate into safe mode — only boots that die YOUNG
    # (a genuine crash loop) still trip the breaker. Health for the breaker is
    # "the app runs", never "the network works" (the old fetch-success
    # definition walked a ~70-min internet outage into a bricked box).
    STABLE_UPTIME_S = 600
    # Recovery mode (the former terminal safe mode) self-heals: a guarded
    # probation fetch every PROBE interval (success exits via clean-run +
    # cold reset), plus a full reboot after SAFE_MODE_REBOOT_S that re-tests
    # the whole boot path. Saving settings remains the immediate manual exit.
    SAFE_MODE_PROBE_INTERVAL_S = 1800
    SAFE_MODE_REBOOT_S = 3600
    # A continuous hour of DEGRADED refreshes (any park failing, or full
    # failure, or wedge evidence) earns one reboot attempt — the known cure for
    # the CP9 fragmentation MemoryErrors is a fresh heap, and before 2026-07-19
    # a partial refresh counted as full health so nothing ever fired while
    # three of four parks sat frozen for hours. Per-boot timer = natural
    # ~hourly rate limit; the never-park invariant holds (uptime clean-runs).
    PARTIAL_ESCALATION_S = 3600

    # Refresh cadence: wait times move slowly; ~10 minutes is the product's
    # intent (owner, 2026-07-16). Halving network activity also halves the
    # box's exposure to the connect-path wedge. Stale retry stays at 60 s.
    def __init__(self, *, enable_web: bool = True, update_interval: int = 600,
                 http_client=None, settings=None) -> None:
        # enable_watchdog=True: opt this app into the hardware watchdog (CircuitPython
        # only; a no-op in the simulator) so a true freeze — e.g. a hung synchronous
        # socket — self-recovers via reset instead of sitting black until a
        # power-cycle.
        # watchdog_timeout=60: the timeout MUST exceed the app's longest LEGITIMATE
        # event-loop block, and this app's is ~20 s (a synchronous update check in
        # the web handler — 18-19 s observed in the soak log; a slow 90 KB park
        # fetch can also breach 8 s). The library's 8 s default put v3.5.15 into a
        # hardware-watchdog reset loop the moment always-arm shipped — the old
        # serial-connected arming guard had masked the misfit for months (this
        # box's port was held, so it never actually ran armed). 60 s still turns a
        # frozen box into a self-heal within a minute, which is what matters; the
        # 8 s figure was precision the workload never supported.
        # NOTE (2026-07-19): the library arms ONE window for boot AND runtime at
        # max(watchdog_timeout, BOOT_WATCHDOG_TIMEOUT=120) — CP 9.2.8 rejects
        # retightening a running watchdog (EINVAL, hardware-observed). So the
        # effective device window is 120 s; this value is the floor/intent.
        # enable_auto_reboot: last-resort self-heal, fed via note_refresh_result()
        # in update_data(). 12 consecutive failures at the 60 s stale-retry cadence
        # ≈ 12+ minutes of continuous outage before the hammer — long enough that a
        # brief API/server blip never reboot-loops the box, short enough that the
        # 2026-07-15 outbound-EBUSY wedge (which stranded the box for 90+ min with
        # no self-heal rung at all) ends without a hand on the reset button.
        # A cold reset is the ONLY automatic recovery this app performs: the
        # 2026-07-16 3-model consensus removed every in-band rung (socket
        # eviction, radio bounce, session rebuild) after the soak showed they
        # destroyed the surviving park connection without curing the wedge.
        super().__init__(enable_web=enable_web, update_interval=update_interval,
                         enable_watchdog=True, watchdog_timeout=60,
                         enable_auto_reboot=True, max_refresh_failures=12)
        self.settings = settings or make_settings()
        if http_client is None:
            from scrollkit.network.http_client import HttpClient
            # session_rebuild_threshold: effectively OFF. Auto-rebuild was the
            # third uncoordinated recovery actor (with the app's failure budget
            # and the OTA check's old ladder) mutating one shared session; the
            # long-uptime wedge lives BELOW the session, so a rebuild can't
            # cure it — the failure budget's cold reset does. Response/socket
            # cleanup in the client is unaffected.
            http_client = HttpClient(session_rebuild_threshold=1_000_000)
        self.http_client = http_client
        self.service = ThemeParkService(self.http_client, self.settings)
        # Feed the watchdog between sequential per-park fetches: a multi-park
        # refresh can block the event loop longer than the watchdog timeout, so the
        # display loop alone can't keep it fed across the whole fetch.
        self.service.watchdog_feed = self._feed_watchdog
        try:
            from src.ota_glue import OTAGlue
            # Reuse the app's HttpClient session for OTA GETs (adafruit_requests is
            # Session-based on CircuitPython — no module-level get).
            self.ota = OTAGlue(http_client=self.http_client)
            self.ota_error = None
        except Exception as e:  # OTA is optional; never block construction
            # This print lands in the first seconds of boot — BEFORE a serial
            # monitor can usually attach — so also keep the reason for the
            # diagnostics web panel (the field-visible surface).
            print("OTA unavailable:", e)
            self.ota = None
            self.ota_error = str(e)
        # The first data refresh happens at boot while setup()'s "Updating / Parks"
        # frame is still up; later refreshes paint their own indicator (see
        # update_data) since they hit the internet with no boot context on screen.
        self._initial_refresh_done = False
        # The boot swarm splash's reveal, held on screen so the first boot status
        # frame can WIPE it away (a real transition, not a hard cut). Detached the
        # first time _status(..., transition=True) runs. See setup()/_status().
        self._boot_splash = None
        # setup() fetches + builds + reveals the first content itself (so the
        # status->first-content handoff is a real transition, done before the
        # concurrent display loop owns the screen). This makes the data loop's
        # very first update_data() a no-op so it doesn't immediately re-fetch.
        self._skip_initial_update = False
        # Render suspension during a refresh's status frame now lives in the base
        # ScrollKitApp (suspend_render()/suspended_render(); the base
        # prepare_display_content() returns None while suspended). See update_data().
        # The _suspend_queue_render property below is a back-compat alias for it.
        #
        # Set when the most recent refresh failed: the queue is showing stale
        # data. Drives a faster retry and is surfaced for diagnostics.
        self._data_stale = False
        self._consecutive_fetch_failures = 0
        # Kept for the diagnostics log line only; escalation now runs on the
        # windowed wedge ledger below (see note_wedge_strike).
        self._consecutive_check_failures = 0
        # The wedge ledger: monotonic timestamps of classified errno-16 events
        # (refreshes AND checks). Windowed, not consecutive — the 2026-07-16
        # night proved the wedge FLAPS: brief healthy phases (or one park
        # succeeding on a surviving pooled socket) reset every consecutive
        # counter forever, so the box never qualified for its own cure.
        # Strikes expire only by TIME; success never erases them.
        self._wedge_strikes = []
        # Refresh cadence: the normal interval, plus a shorter one used to retry
        # quickly while data is stale (a flaky network shouldn't make the user
        # wait a full cycle for fresh times). The base data loop reads
        # self.update_interval before each sleep, so swapping it takes effect on
        # the next cycle.
        self._default_update_interval = update_interval
        self._stale_retry_interval = min(60, update_interval)
        # Crash/boot diagnostics in NVM: boot-loop breaker + post-mortem surfaced
        # on the config web UI. No-op on desktop. record_boot() runs in setup().
        self.diagnostics = diagnostics.open()
        # Boot banner: anchor every subsequent error_log line to a boot. The
        # 2026-07-16 debugging session could not tell which boot wrote which
        # log line (entries carry no timestamps) — that ambiguity cost hours.
        try:
            from src.ota_glue import read_current_version
            logger.error(None, "boot: v%s reason=%s boot#%s"
                         % (read_current_version(),
                            self.diagnostics.summary().get("reset_reason", "?"),
                            getattr(self.diagnostics, "boot_count", "?")))
        except Exception:
            pass
        # Set when repeated fault-reboots tripped the breaker. NOT a parking
        # lot: recovery mode keeps the config UI reachable AND self-heals via
        # probation fetches + a timed full reboot (_recovery_mode_tick).
        self._safe_mode = False
        self._safe_mode_last_probe = None      # monotonic of the last probation fetch
        self._safe_mode_reboot_fired = False   # the timed reboot fires once (sim no-op)
        # Coalesce concurrent refreshes: a settings save schedules an extra
        # update_data() task which could interleave with the periodic one
        # (teardown/status/queue races). One runs; overlaps are dropped — the
        # queue was already rebuilt synchronously and the next tick fetches.
        self._refresh_busy = False
        # Monotonic stamp of when continuous degradation (partial/failed/wedge
        # refreshes) began; None while fully healthy. Drives the hourly
        # degraded-streak reboot cure (PARTIAL_ESCALATION_S).
        self._partial_since = None

    async def create_display(self):
        """Return the ScrollKit display (auto-detects sim/hardware).

        Scaled text (``draw_text_scaled``) now lives in the library's
        ``UnifiedDisplay``, so the old ``ThemeParkDisplay`` subclass is gone.
        """
        from scrollkit.display.unified import UnifiedDisplay
        return UnifiedDisplay(width=self.WIDTH, height=self.HEIGHT, bit_depth=self.BIT_DEPTH)

    async def create_web_server(self):
        """Return the config web server (native ``adafruit_httpserver``).

        The SAME server runs on desktop and device; only the socket pool differs.
        On CircuitPython the ``Server`` needs a pool from the WiFi radio; on
        desktop the stdlib ``socket`` module IS a valid pool (the server falls
        back to it when ``socket_pool`` is None). The ``wifi``/``socketpool``
        imports stay behind the platform guard so the simulator never touches
        them. (The old library web abstraction is gone — see config_server.py.)
        """
        try:
            from src.web.config_server import ThemeParkConfigServer
            socket_pool = None
            import sys
            if hasattr(sys, "implementation") and sys.implementation.name == "circuitpython":
                import socketpool
                import wifi
                socket_pool = socketpool.SocketPool(wifi.radio)
            return ThemeParkConfigServer(self, static_dir="src/www", socket_pool=socket_pool)
        except Exception as e:  # never block boot on web setup
            print("web server unavailable:", e)
            return None

    @property
    def _suspend_queue_render(self):
        """Back-compat alias for the base ScrollKitApp render-suspend flag.

        Render suspension during a refresh's status frame moved into the library:
        the base ``prepare_display_content()`` returns None while suspended, so this
        app no longer overrides it — it uses ``self.suspended_render()`` in
        update_data(). Kept as a read/write alias so existing checks still work."""
        return self._render_suspended

    @_suspend_queue_render.setter
    def _suspend_queue_render(self, value):
        self._render_suspended = bool(value)

    async def setup(self) -> None:
        """Pre-run sequence (boot state machine — partial; T018/T027 add WiFi/OTA/NTP)."""
        # Record this boot in NVM and classify reboot loops up front. reset_reason
        # lets the UI report e.g. a recovery from a watchdog reset (device-only;
        # a no-op in the simulator).
        try:
            self.diagnostics.record_boot(diagnostics.read_reset_reason())
        except Exception as e:
            logger.error(e, "diagnostics.record_boot failed")
        # Stable-uptime clean run: scheduled unconditionally (recovery mode
        # included) so ANY boot that stays alive STABLE_UPTIME_S stops counting
        # toward the boot-loop breaker and re-arms /safemode.py's fast retries.
        # running is False when tests drive setup() directly — skip then (they
        # call _note_stable_runtime themselves) so no orphan task outlives the
        # test loop.
        if self.running:
            try:
                asyncio.create_task(self._note_stable_runtime())
            except Exception as e:
                logger.error(e, "stable-runtime task failed to schedule")
        if hasattr(self.display, "create_window"):
            try:
                await self.display.create_window("ThemeParkWaits")
            except Exception:
                pass

        # Apply configured brightness.
        try:
            await self.display.set_brightness(float(self.settings.get("brightness_scale", "0.5")))
        except (TypeError, ValueError):
            pass

        # Opening splash: a small, sparse flock of birds (keep it to ~20 — fewer
        # looks better) flies in and assembles "THEME PARK WAITS". Driven here
        # frame-by-frame (instead of the blocking show_swarm_splash, which detaches
        # at the end) so the assembled name STAYS on screen and the first boot
        # status frame can wipe it away with a real transition. The reveal is held
        # in self._boot_splash and detached by the first transitioned _status().
        await self._play_boot_splash()

        # Network bring-up. Dev mode auto-connects and skips NTP/mDNS; on hardware
        # a failed join runs onboarding (first-boot setup portal, or retry-then-
        # portal-then-reboot for known creds) — see _init_network/_run_wifi_onboarding.
        await self._init_network()

        # Install a pending OTA update before fetching (reboots if one is staged).
        if self.ota is not None:
            try:
                # Boot-time staging downloads now run under the armed boot
                # watchdog: feed it per downloaded chunk (large release on
                # slow WiFi can outlast any fixed timeout).
                client = getattr(self.ota, "client", None)
                if client is not None:
                    client.watchdog_feed = self._feed_watchdog
            except Exception:
                pass
            try:
                self.ota.attach_display(self.display)
                # A persisted /install request downloads HERE — right after
                # network bring-up, before parks/content/web allocate — because
                # the GitHub RSA-2048 handshake dies at runtime (mbedtls
                # PK_ALLOC_FAILED; ledger attempt #5). Staging success makes
                # has_pending() true and install_pending() applies it below.
                # getattr, not except AttributeError: an AttributeError raised
                # INSIDE the method must surface, not read as "older glue".
                stage_pending = getattr(self.ota, "stage_pending_request", None)
                if stage_pending is not None:
                    await stage_pending()
                had_pending = self.ota.has_pending()
                if had_pending:
                    # Record what we're running BEFORE the apply: install_pending()
                    # reboots on success and never returns, so this is the only
                    # moment the "came from" version can be captured. Proves on
                    # the diagnostics page that an OTA replaced running code.
                    try:
                        from src.ota_glue import (note_pre_update_version,
                                                  read_current_version)
                        note_pre_update_version(read_current_version())
                    except Exception as e:
                        print("pre-update version stamp failed:", e)
                installed = await self.ota.install_pending()
                if had_pending and not installed:
                    # A staged update failed to apply — persist it (the panel
                    # frame is transient and serial may not be watched).
                    logger.error(None, "OTA apply failed: %s"
                                 % (self.ota.last_error or "unknown"))
            except Exception as e:
                print("OTA install_pending failed:", e)

        # Boot-loop breaker: if we've fault-rebooted repeatedly with no healthy run
        # in between (a deterministic crash — bad settings, an API change), stop
        # fetching wait times and just show a reconfigure message while the web/AP
        # config UI stays reachable (network was brought up above). Prevents an
        # endless reboot cycle from the watchdog / last-resort reset.
        if self.diagnostics.safe_mode:
            self._safe_mode = True
            logger.error(None, "entering recovery mode after repeated reboots")
            # Recovery mode guards the NORMAL data cadence, not reconfiguration
            # or self-healing. The park CATALOG must still be fetched, or the
            # "reconfigure at themeparkwaits.local" page can offer nothing but
            # "(none)" and the box is unrescuable (the 2026-07-17 customer
            # trap: pre-3.5.16 firmware watchdog-reset its way here, then the
            # exit — a clean run — was unreachable because safe mode skipped
            # all fetching). Guarded: if THIS fetch is the crasher, the breaker
            # re-trips and we are no worse off than skipping it.
            # NOT a parking lot (2026-07-19): update_data() now runs
            # _recovery_mode_tick() — a guarded probation fetch every 30 min
            # (success exits via clean-run + cold reset) and a full reboot at
            # 60 min that re-tests the whole boot path; the stable-uptime task
            # above clears the breaker so that next boot is a NORMAL one.
            # Saving settings remains the immediate manual exit
            # (config_server POST /settings -> note_clean_run + reboot).
            try:
                import time
                self._safe_mode_last_probe = time.monotonic()
            except Exception:
                pass
            try:
                await self.service.initialize()
            except Exception as e:
                logger.error(e, "recovery-mode catalog fetch failed")
            self._show_safe_mode_message()
            try:
                await self._transition_to_first_queue_content()
            except Exception:
                pass
            return

        # Park-list fetch is the big blocking call (/destinations + retries) — tell
        # the user before the panel would otherwise go black on it. transition=True
        # wipes the splash (on desktop) / the prior status frame into "Parks".
        await self._status("Parks", transition=True)
        try:
            await self.service.initialize()  # fetch park list + load park/vacation settings
        except Exception as e:  # never crash boot (FR-014)
            logger.error(e, "service.initialize failed")

        # Fetch wait times + build the queue HERE (the "Parks" frame stays up during
        # the fetch), then WIPE "Parks" into the first content screen. Done in setup
        # so this status->content handoff is a real transition — before the display
        # loop starts and becomes the screen's owner. The data loop's first
        # update_data() is then a no-op (it would otherwise immediately re-fetch).
        try:
            ok = await self._fetch_and_build()
            self._initial_refresh_done = True
            self._skip_initial_update = True
            if self.content_queue.is_empty:
                # Offline at boot with no content yet: show a message instead of
                # stranding on the splash, and retry sooner than the full cycle.
                self._show_offline_fallback()
            if ok:
                # Healthy boot: count it as a REAL fetch success, not just a
                # clean run — "Last fetch OK" must include the boot fetch, or
                # the page reads "(never)" for the first 10 min after every
                # reboot while showing fresh data (2026-07-17). The session
                # stamp feeds seconds_since_last_refresh_success(); the NVM
                # stamp survives reboots; note_fetch_result's ok-path also
                # clears the reboot-loop streak (note_clean_run).
                try:
                    self.note_refresh_result(True)
                except Exception:
                    pass
                boot_full = not getattr(self.service, "last_failed_parks", None)
                # rearm only on FULL success: a partial boot fetch stamps the
                # success time but must not clean-run / end the failure-reboot
                # epoch (review 2026-07-19).
                self.diagnostics.note_fetch_result(True, 0, rearm=boot_full)
                if not boot_full:
                    # Boot-time PARTIAL: some park(s) failed even though the
                    # fetch "succeeded" — show degraded and retry hot from the
                    # first cycle (the full policy lives in _do_refresh).
                    self._data_stale = True
                    self.update_interval = self._stale_retry_interval
            else:
                self._data_stale = True
                self.update_interval = self._stale_retry_interval
            await self._transition_to_first_queue_content()
        except Exception as e:
            logger.error(e, "boot first-content build failed")
            try:
                self._show_offline_fallback()
                self.update_interval = self._stale_retry_interval
                await self._transition_to_first_queue_content()
            except Exception:
                pass

    def _show_offline_fallback(self) -> None:
        """Put a 'retrying' message on an EMPTY queue so first boot with no network
        shows something instead of the frozen splash / black panel. Never displaces
        real content (only acts when the queue is empty). Never raises into boot."""
        try:
            q = self.content_queue
            if q is None or not q.is_empty:
                return
            from scrollkit.display.content import ScrollingText
            q.add(ScrollingText("Offline - retrying...", y=13, color=0xFFAA00, speed=20))
        except Exception as e:
            logger.error(e, "offline fallback failed")

    def _show_safe_mode_message(self) -> None:
        """Replace the queue with a recovery-mode notice when the boot-loop
        breaker trips, pointing the user at the still-reachable config UI.
        Honest about the self-heal: the box IS retrying on its own. Never
        raises."""
        try:
            q = self.content_queue
            if q is None:
                return
            q.clear()
            from scrollkit.display.content import ScrollingText
            domain = self.settings.get("domain_name", "themeparkwaits")
            q.add(ScrollingText(
                "Recovering - retrying soon; config at %s.local" % domain,
                y=13, color=0xFF0000, speed=20))
        except Exception as e:
            logger.error(e, "safe mode message failed")

    async def _draw_status_frame(self, step, color=0xFFAA00) -> None:
        """Draw (without show) the two-row boot status: "Updating" over the step row.

        Two lines with a 4px gap, centered on the panel. NOTE: draw_text renders ~2
        rows HIGHER on the actual hardware than the geometry suggests (calibrated from
        on-device photos), so the block is placed 2px low here (line1 y=9, line2 y=20)
        to land vertically centered on the real display.
        """
        disp = self.display
        await disp.clear()
        await self._draw_centered(disp, "Updating", 9, color)
        if step:
            await self._draw_centered(disp, step, 20, color)

    async def _status(self, step, color=0xFFAA00, *, transition=False) -> None:
        """Two-row boot status ("Updating" + step), shown before a blocking boot call.

        Boot makes several blocking network calls between the splash and the first
        data frame while the display loop isn't running yet, so without a frame in
        between the panel sits black and looks hung. ``transition=True`` WIPES the
        previous full-screen frame (the splash, or the prior status) into this one
        via the direct-display driver — these boot handoffs are not content-queue
        advances, so the queue's transition system can't animate them. Default False
        so the per-attempt Wi-Fi retry callback doesn't wipe-spam. Defensive — never
        raises into boot. Keep ``step`` short: ~10 chars fit at the default font.
        """
        # Boot now runs under an armed (boot-sized) watchdog; every stage
        # transition paints a status frame, so feeding here marks boot
        # progress. Safe when disarmed/desktop.
        self._feed_watchdog()
        disp = self.display
        if not disp:
            return

        async def _draw():
            # The first status frame wipes the held boot splash away for good.
            sp = self._boot_splash
            if sp is not None:
                try:
                    sp.detach()
                except Exception:
                    pass
                self._boot_splash = None
            await self._draw_status_frame(step, color)

        try:
            if transition:
                await self._play_direct_transition(_draw)
            else:
                await _draw()
                await disp.show()
        except Exception:
            pass

    async def _play_boot_splash(self, num_birds=20, bird_speed=5.0, hold_seconds=1.5) -> None:
        """Assemble the THEME PARK WAITS swarm and HOLD it on screen (don't detach),
        so the first boot status frame can wipe it away with a real transition.

        Driven frame-by-frame here instead of the blocking ``show_swarm_splash``
        (which detaches at the end, leaving nothing to wipe). The reveal is stored
        in ``self._boot_splash``. Never raises into boot.
        """
        self._boot_splash = None
        disp = self.display
        if disp is None:
            return
        try:
            from src.ui.reveal_splash import (get_theme_park_waits_pixels,
                                              LOGO_TEXT_COLORS, LOGO_COLOR_AXIS)
            from scrollkit.effects.swarm_reveal import SwarmReveal
            splash = SwarmReveal(get_theme_park_waits_pixels(),
                                 text_colors=LOGO_TEXT_COLORS,
                                 color_axis=LOGO_COLOR_AXIS,
                                 num_birds=num_birds, bird_speed=bird_speed)
            splash.start(disp)
            steps = 0
            while not splash.is_complete and steps < 2000:
                steps += 1
                splash.step()
                if await disp.show() is False:
                    splash.detach()
                    return
                await asyncio.sleep(0.05)
            await asyncio.sleep(hold_seconds)      # hold the assembled name
            self._boot_splash = splash             # held on screen; wiped by next _status
        except Exception as e:
            logger.error(e, "swarm splash failed")
            self._boot_splash = None

    def _boot_transition(self, style=None):
        """A transition for a boot / direct-display handoff. The ``transition_style``
        setting gates the off-switch ("None" -> no transition); ``style`` chooses
        which transition to use WHEN ON. Pass a scroll-safe transition
        ("Horizontal Wipe") when revealing SCROLLING content; leave None for the
        STATIC, held boot status frames, which get a full-screen wipe (Iris Snap) —
        full-screen transitions are [best on: fullscreen], i.e. for static screens.
        """
        setting = self.settings.get("transition_style", "None")
        if not setting or setting == "None":
            return None
        name = style or ("Iris Snap" if setting == "Auto" else setting)
        try:
            from scrollkit.effects.transitions import transition_factory
        except ImportError:
            return None
        return transition_factory(name)

    async def _play_direct_transition(self, draw_next, *, style=None) -> None:
        """Wipe whatever is on screen into a freshly-drawn full-screen frame, using
        the generic transition primitive DIRECTLY (independent of the content queue).

        ``draw_next`` is an async callable that draws the destination frame; it runs
        once while the transition is fully covered (so the swap is hidden), then the
        transition reveals it. Paced at ~20 fps. Falls back to a plain draw on any
        error — boot must never crash on a transition. MUST only be called while the
        display loop is not concurrently drawing (i.e. during setup, before the
        loop starts) — the transition and the loop are both display drivers.
        """
        disp = self.display
        if disp is None:
            return
        t = self._boot_transition(style)
        if t is None:                              # transitions off: just show it
            await draw_next()
            try:
                await disp.show()
            except Exception:
                pass
            return
        try:
            await t.start(disp, draw_next)         # swap_callback may be async (awaited)
            guard = 0
            while not t.is_complete and guard < 120:
                guard += 1
                await t.render(disp)
                if await disp.show() is False:
                    return
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(e, "boot transition failed")
            try:
                await draw_next()
                await disp.show()
            except Exception:
                pass

    async def _transition_to_first_queue_content(self) -> None:
        """Wipe the boot status frame into the FIRST content item (e.g. "Configure").

        The library's display loop deliberately skips the transition on the first
        queue item, so we drive it here (in setup, before the loop runs): start the
        first item via the queue's public ``get_current()`` (which leaves the queue
        positioned on it with advance_count=1, so the loop continues naturally and
        the NEXT advance still transitions), and reveal it with the direct driver.
        """
        q = self.content_queue
        disp = self.display
        if q is None or disp is None:
            return
        try:
            content = await q.get_current()        # starts item 0; advance_count -> 1
        except Exception:
            content = None
        if content is None:
            return

        async def _draw():
            await disp.clear()
            await content.render(disp)
        # The first content ("Configure") is SCROLLING text, so reveal it with the
        # scroll-safe transition, not the full-screen one used for static frames.
        await self._play_direct_transition(_draw, style="Horizontal Wipe")

    async def _fetch_and_build(self) -> bool:
        """Refresh wait times for the selected park(s) and rebuild the content queue.
        Shared by boot (setup) and the periodic refresh (update_data).

        Returns True only if the refresh actually got fresh data. The HTTP client
        SWALLOWS network errors (it returns a 500 response, not an exception), so
        success cannot be inferred from "no exception raised" — we check the update
        count / flag. On failure the existing queue is left UNTOUCHED (build is
        skipped) so the caller keeps last-good content and the stale flag/retry
        cadence stay truthful instead of flapping back to "fresh". An UNconfigured
        device (no park selected) is not a failure: it builds the Configure prompt
        and reports success."""
        pl = self.service.park_list
        try:
            if pl is not None and getattr(pl, "selected_parks", None):
                ok = (await self.service.update_selected_parks()) > 0
            elif pl is not None and pl.current_park.is_valid():
                ok = bool(await self.service.update_current_park())
            else:
                ok = True  # nothing to fetch (unconfigured) — show Configure prompt
            if ok:
                q = self.content_queue
                # Preserve the rotation position across a data refresh. Rebuilding
                # calls queue.clear(), which resets the cycle to index 0; for a board
                # whose full cycle outlasts update_interval (a big park, or a max_wait
                # sort that parks every closed ride at the tail) that meant the tail
                # was never reached before the next 5-min refresh restarted at the top
                # — so those screens (notably all the "Closed" rides) never showed.
                # Resume where the rotation was so the cycle runs uninterrupted and
                # every screen gets airtime; the fetched wait times update underneath.
                prev_index = getattr(q, "_current_index", 0)
                build_content_queue(q, pl, self.settings, self.service.vacation)
                # _current_content is None right after clear()+rebuild, so setting the
                # index alone makes the next get_current() resume at that screen.
                new_len = len(getattr(q, "_items", ()))
                if new_len:
                    q._current_index = min(prev_index, new_len - 1)
            return ok
        except Exception as e:  # keep prior queue/snapshot, never crash (FR-014)
            logger.error(e, "fetch_and_build failed")
            return False

    async def _draw_centered(self, disp, text, y, color) -> None:
        """draw_text ``text`` horizontally centered on ``disp`` at baseline ``y``."""
        measure = getattr(disp, "measure_text", None)
        w = measure(text) if measure is not None else len(text) * 6
        await disp.draw_text(text, max(0, (disp.width - w) // 2), y, color)

    async def show_loading(self) -> None:
        """No-op. The two-row boot frames ("Updating" + step) cover the long
        blocking boot calls, and update_data() paints "Updating / Times" before each
        later refresh — so this base hook has nothing to add."""
        return

    def _get_transition(self):
        """Per-content screen transition (app policy), without touching the library.

        The base reads a single global ``transition_style`` and returns one
        transition for every content advance. We add an ``"Auto"`` mode that picks
        a transition per the INCOMING content: each major scrolling-text message is
        tagged in build_content_queue with ``_tpw_transition`` (the splash, rides,
        and their overlay-bearing content are left untagged → no transition, since
        their number/swarm overlay layers composite ABOVE the transition mask and
        would not wipe cleanly). ``"None"`` keeps transitions off; any other value
        is a specific transition applied globally (library behavior via super()).
        """
        style = self.settings.get("transition_style", "None")
        if not style or style == "None":
            return None
        if style != "Auto":
            return super()._get_transition()
        content = getattr(self, "_current_content", None)
        name = getattr(content, "_tpw_transition", None)
        if not name:
            return None
        try:
            from scrollkit.effects.transitions import transition_factory
        except ImportError:
            return None
        return transition_factory(name)

    async def _init_network(self):
        """WiFi station connect (+ HTTP session, NTP, mDNS) — CircuitPython hardware only.

        Gated on the real platform (NOT the library's ``is_dev_mode()``, which can
        misfire if a stray ``wifi`` package is importable on desktop and would then
        make ``setup()`` block on failing NTP/network calls before the window ever
        renders). On desktop the HttpClient uses urllib directly — no WiFi/NTP/mDNS
        needed. First-boot AP onboarding (no creds) and bad-credential recovery
        run here via _connect_wifi/_run_wifi_onboarding (device-only — the guard
        above means the setup portal never fires on desktop).
        """
        import sys
        if not (hasattr(sys, "implementation") and sys.implementation.name == "circuitpython"):
            return  # desktop / simulator: nothing to bring up
        try:
            from scrollkit.network.wifi_manager import WiFiManager
            # ap_name brands the onboarding portal's access point: the customer
            # joins "ThemeParkWaits-XXXX" (MAC tail appended by the library for
            # uniqueness), not a generic "WifiManager_..." mystery network.
            self.wifi = WiFiManager(self.settings, ap_name="ThemeParkWaits")
            await self._status("Wi-Fi", transition=True)
            # Join the network; on failure fall through to onboarding (the setup
            # portal for a first boot, or retry-then-portal-then-reboot for known
            # creds). connect() reports per-attempt status ("Attempt n/3") on the
            # step row via the callback threaded through in _connect_wifi.
            connected = await self._connect_wifi(self.wifi)
            if connected:
                # Disable WiFi modem power-save (the A/B discriminator for the
                # wedge, 2026-07-16): ESP32 station firmware naps between
                # beacons by default, and that doze/wake handshake against
                # certain APs/mesh nodes is a known source of degraded-
                # connectivity states. If the wedge stops recurring with this
                # off, we've found the trigger. Costs a little power; this is
                # a mains-powered sign. Older CircuitPython without the API
                # just logs and moves on.
                try:
                    import wifi as _wifi
                    _wifi.radio.power_management = _wifi.PowerManagement.NONE
                    logger.error(None, "wifi power-save: disabled (NONE)")
                except Exception as e:
                    print("wifi power-save disable unavailable:", e)
                try:
                    session = self.wifi.create_http_session()
                    if session is not None and hasattr(self.http_client, "session"):
                        self.http_client.session = session
                except Exception as e:
                    logger.error(e, "create_http_session failed")
                # Always sync the clock via NTP (fast, ~1-2s). The vacation
                # countdown is its only consumer, but setting it unconditionally
                # means it's already correct if a vacation is ever configured — no
                # need to turn time on later. NTP needs a socket pool; without one
                # set_system_clock skips NTP and falls back to the slow multi-host
                # HTTP Date header (kept as the fallback for networks blocking UDP/123).
                try:
                    from scrollkit.utils.system_utils import set_system_clock
                    await self._status("Clock", transition=True)
                    pool = None
                    try:
                        import socketpool
                        import wifi
                        pool = socketpool.SocketPool(wifi.radio)
                    except Exception as e:
                        logger.error(e, "NTP socket pool unavailable")
                    await set_system_clock(self.http_client, socket_pool=pool)
                except Exception as e:
                    logger.error(e, "set_system_clock failed")
                try:
                    from scrollkit.network.mdns import advertise
                    # Retain the mdns.Server for the app's lifetime: if it is garbage
                    # collected, the responder stops answering and <domain>.local
                    # resolution dies after the first query (intermittent .local).
                    self.mdns_server = advertise(
                        self.settings.get("domain_name", "themeparkwaits"))
                except Exception as e:
                    logger.error(e, "mDNS advertise failed")
        except Exception as e:
            logger.error(e, "network init failed")

    async def _connect_wifi(self, wm) -> bool:
        """Join WiFi, falling back to onboarding on failure. Returns True if online.

        Factored out of _init_network() as a platform-agnostic seam (no hardware
        guard, no NTP/mDNS) so the connect->onboarding decision is unit-testable
        with a mock WiFiManager.
        """
        if await wm.connect(display_callback=self._status):
            return True
        return await self._run_wifi_onboarding(wm)

    async def _run_wifi_onboarding(self, wm) -> bool:
        """Bring a device online after the initial WiFi join fails (hardware only).

        Failure policy, keyed on whether credentials exist (``wm.ssid``):

        * **No credentials (first boot).** There is nothing to retry, so hold the
          library's no-file-editing setup portal open indefinitely
          (``timeout_s=None``) until the user picks a network + password from a
          phone. The library saves to settings.json (never a code file) and
          REBOOTS on save — so on hardware this call never returns; on desktop
          ``run_setup_portal()`` just returns (but the platform guard in
          _init_network means we never get here off-device in production).

        * **Credentials exist but the join failed.** Most often transient — after
          a power blip the router is still rebooting and the sign, which boots
          faster, comes up first. Retry as a STATION a few times with growing
          grace (WIFI_RECONNECT_BACKOFF_S) BEFORE disturbing the radio with AP
          mode, so a returning router self-heals with no portal and no reboot. If
          it's still down (a wrong password, or an outage longer than our grace),
          open the portal for a bounded window (WIFI_PORTAL_TIMEOUT_S) so a
          present user can fix the password; if nobody does, reboot via
          ``wm.reset()`` so a slow-to-return router reconnects on the next boot
          instead of the sign sitting in setup mode forever.

        This runs inside _init_network()'s try/except and before the watchdog is
        armed (the library arms it only after setup() returns), so a blocking
        portal here is safe. Returns True only if a station retry reconnected
        (the caller then sets up the HTTP session / NTP / mDNS).
        """
        if not wm.ssid:
            # First boot: no creds to retry — wait in the portal until configured.
            await wm.run_setup_portal(display=self.display, timeout_s=None)
            return False  # unreachable on hardware (the library reboots on save)

        # Known creds that didn't connect: give a rebooting router time to return
        # before flipping to AP mode. A healthy boot never reaches here (the first
        # connect() succeeded), so these grace sleeps only cost time when offline.
        rounds = self.WIFI_RECONNECT_BACKOFF_S
        for i, backoff in enumerate(rounds, 1):
            await self._status("Wi-Fi %d/%d" % (i, len(rounds)))
            await asyncio.sleep(backoff)
            if await wm.connect(display_callback=self._status):
                return True

        # Still offline with known creds. Offer the portal to a present user, then
        # reboot so a router that's merely slow to return reconnects next boot.
        saved = await wm.run_setup_portal(
            display=self.display, timeout_s=self.WIFI_PORTAL_TIMEOUT_S)
        if not saved:
            await wm.reset()  # HW reboot; desktop/dev: a harmless ~4s no-op
        return False

    async def update_data(self) -> None:
        """Refresh wait times for the selected park(s) and rebuild the content queue.

        setup() already did the first fetch/build/reveal, so the data loop's very
        first call here is a no-op (otherwise it would immediately re-fetch). Every
        later refresh (the 5-min cycle, or a settings-change refresh) tears down the
        on-screen content and WIPES it into the "Updating / Times" frame — the
        ``_status(..., transition=True)`` runs in the data loop, but only after
        _teardown_active_content() has cleared the previous content, so there is no
        concurrent display-loop drawing the same screen.
        """
        if self._safe_mode:
            # Boot-loop breaker tripped — but recovery mode is NOT a parking
            # lot (2026-07-19): probation fetches + a timed full reboot
            # self-heal it without a human.
            await self._recovery_mode_tick()
            return
        if self._skip_initial_update:
            self._skip_initial_update = False
            return
        # Coalesce concurrent refreshes: a settings save fire-and-forgets an
        # extra update_data() task (_schedule_refresh); if one is already
        # mid-flight, drop the overlap — the save already rebuilt the queue
        # synchronously and the next tick fetches the new park.
        if self._refresh_busy:
            return
        self._refresh_busy = True
        try:
            await self._do_refresh()
        finally:
            self._refresh_busy = False

    async def _do_refresh(self) -> None:
        """One full refresh: status frame, fetch/build, health accounting,
        wedge ledger, socket drain, and (when the ledger says so) the budgeted
        cold reset. Runs only via update_data()'s coalescing guard."""
        # Every refresh hits the internet (themeparks.wiki); the synchronous fetch
        # freezes the display, so paint a frame first or a hang looks like a dead screen.
        if self._initial_refresh_done:
            # Suspend queue rendering across teardown + status frame + the blocking
            # fetch: _teardown_active_content() awaits current.stop(), which yields to
            # the display loop — without suspending, the loop could render one more
            # frame of the old ride over the status frame. The queue keeps its items,
            # so a failed fetch resumes last-good content (never black). The context
            # manager always resumes, even if the fetch raises.
            with self.suspended_render():
                await self._teardown_active_content()
                await self._status("Times", transition=True)
                ok = await self._fetch_and_build()
        else:
            self._initial_refresh_done = True
            ok = await self._fetch_and_build()

        # Heap telemetry after the build (the leak-vs-frag gate): the service
        # stamped cycle-start/after-parks; this adds the post-UI-rebuild point.
        try:
            from src.api.theme_park_service import _heap_note
            note = _heap_note()
            if note:
                self.service.heap_stats["after build"] = note
        except Exception:
            pass

        # Wedge evidence for THIS run: any park whose terminal error carried
        # the errno-16 signature. Checked on success too — a refresh that
        # updated one park over a surviving pooled socket while another died
        # EBUSY is NOT healthy; treating it as healthy is exactly how the box
        # sat wedged for hours with every counter at zero (2026-07-16).
        errors = getattr(self.service, "last_refresh_errors", None) or []
        wedge_evidence = any(self._is_wedge_error(e) for e in errors)
        # Per-park failures for THIS run (parse failures included — they never
        # reach last_refresh_errors, which feeds the wedge classifier only).
        failed_parks = getattr(self.service, "last_failed_parks", None) or []

        # Track staleness and retry faster while stale, so a transient network
        # blip doesn't strand the user on hours-old times. Wedge evidence OR
        # any per-park failure makes a "success" degraded, not healthy — three
        # big parks failed MemoryError for hours behind an all-green dashboard
        # because partial success rode the full-health path (2026-07-19).
        self._data_stale = (not ok) or wedge_evidence or bool(failed_parks)
        # FULL health is the only state that re-arms recovery machinery
        # (budget, safemode streak, clean run, failure-reboot epoch) — a
        # partial success must never masquerade as it (review 2026-07-19).
        full_health = ok and not wedge_evidence and not failed_parks
        reset_wanted = False
        if ok:
            self._consecutive_fetch_failures = 0
            if wedge_evidence:
                # Partial success with wedge evidence: keep the content, but
                # keep the short retry cadence and count the strike. Stamp THIS
                # refresh's success to NVM first: the strike's escalating
                # record_crash flushes the last-ok epoch, and a cold reset right
                # here would otherwise lose the freshest success to the 30-min
                # persist throttle — the page would understate "Last fetch OK"
                # (review, 2026-07-17).
                self.update_interval = self._stale_retry_interval
                try:
                    # Stamp the time only (rearm=False): a wedge-partial is
                    # degraded — it must not clean-run or end the epoch.
                    self.diagnostics.note_fetch_result(True, 0, rearm=False)
                except Exception:
                    pass
                reset_wanted = self.note_wedge_strike(
                    "refresh-partial", errors[-1] if errors else "?")
            elif failed_parks:
                # PARTIAL, non-wedge (the CP9 fragmentation shape): degraded.
                # Stay on the hot retry cadence — the repeated gc across 60 s
                # retries is what lets fragmentation self-heal in-session — and
                # do NOT re-arm the budget or the safemode streak (full health
                # only). Escalation is time-based below.
                self.update_interval = self._stale_retry_interval
                logger.error(None, "partial refresh: %d park(s) failed (%s)"
                                   % (len(failed_parks), ", ".join(failed_parks)))
            else:
                self.update_interval = self._default_update_interval
                self._write_recovery_reset_count(0)   # full health re-arms budget
                self._clear_safemode_streak()         # /safemode.py's loop guard
        else:
            self._consecutive_fetch_failures += 1
            self.update_interval = self._stale_retry_interval
            # BSSID in the failure log: the site WiFi is a two-AP mesh — if the
            # failure-onset BSSID differs from boot's, the wedge followed a
            # ROAM (the open roam-correlation question in the ledger).
            logger.error(None, "refresh failed; keeping last-good content "
                               "(consecutive=%d bssid=%s)"
                               % (self._consecutive_fetch_failures, self._bssid()))
            if wedge_evidence:
                reset_wanted = self.note_wedge_strike(
                    "refresh", errors[-1] if errors else "?")
        # Feed the base watchdog ladder (enable_auto_reboot): the 12-consecutive
        # budget stays as the total-outage backstop behind the windowed wedge
        # ledger. ``ok`` (any park succeeded) is the right diet for THAT counter
        # — it measures total outages; partial degradation is the degraded-hour
        # escalation's job. No intermediate radio bounce (falsified on hardware).
        try:
            self.note_refresh_result(ok, reason=None if ok else "fetch failed")
        except Exception:
            pass
        try:
            # rearm gated on FULL health: a partial stamps "Last fetch OK"
            # but leaves clean-run and the failure-reboot epoch untouched.
            self.diagnostics.note_fetch_result(
                ok, self._consecutive_fetch_failures, rearm=full_health)
        except Exception:
            pass
        # Idle with ZERO open outbound sockets (owner's design rule, 2026-07-16):
        # a keep-alive socket parked across the 10-minute gap is unreliable on
        # this stack, and a surviving one actively MASKS the wedge from the
        # ledger. Sockets are closed until needed; the next burst reconnects
        # (ECDSA handshakes — cheap, never failed for memory). The web server
        # owns a separate pool; this cannot touch its listening socket.
        try:
            closer = getattr(self.http_client, "close_pooled_sockets", None)
            if closer is not None:
                closer()
        except Exception:
            pass
        if reset_wanted:
            # The one proven cure, applied from the data loop (not a handler —
            # nothing to flush). Brief sleep lets the log line reach flash.
            logger.error(None, "wedge confirmed: cold reset now")
            await asyncio.sleep(0.5)
            self._hardware_reset()   # cold reset on device; no-op on desktop

        # Degraded-streak escalation (2026-07-19): a continuous hour of ANY
        # degradation — partial, full failure, or wedge evidence — earns one
        # reboot attempt (fresh heap = the known fragmentation cure). The
        # per-boot timer is the rate limit; full health clears it.
        import time
        now = time.monotonic()
        if full_health:
            self._partial_since = None
        elif self._partial_since is None:
            self._partial_since = now
        if (self._partial_since is not None
                and now - self._partial_since >= self.PARTIAL_ESCALATION_S):
            reason = ("degraded for %dmin (failed: %s) — reboot cure"
                      % (int((now - self._partial_since) // 60),
                         ", ".join(failed_parks) or "all"))
            logger.error(None, "escalation: " + reason)
            try:
                self.diagnostics.record_crash(reason)
                self.diagnostics.note_deliberate_reboot()
            except Exception:
                pass
            await asyncio.sleep(0.5)
            self._hardware_reset()               # never returns on device
            self._partial_since = time.monotonic()   # desktop/sim: re-arm timer

    async def _note_stable_runtime(self) -> None:
        """Uptime-based clean run — the 2026-07-19 root fix.

        Surviving STABLE_UPTIME_S of running IS health for the boot-loop
        breaker: it zeroes rapid_boots and /safemode.py's escape-hatch streak,
        so deliberate reboots (outage auto-reboots, wedge cold resets, watchdog
        bites) never accumulate into safe mode — only boots that die YOUNG (a
        genuine crash loop) still trip it. Deliberately does NOT clear the
        failure-reboot epoch flag (that needs a real fetch success — it exists
        to rate-limit reboots of a box that stays up but keeps failing) and
        does NOT re-arm the wedge reset budget (same reason)."""
        try:
            await asyncio.sleep(self.STABLE_UPTIME_S)
        except Exception:
            return
        if not self.running:
            return
        try:
            self.diagnostics.note_clean_run()
        except Exception:
            pass
        self._clear_safemode_streak()
        logger.error(None, "stable %ds uptime: boot-loop counter and safemode "
                           "streak cleared" % self.STABLE_UPTIME_S)

    async def _recovery_mode_tick(self) -> None:
        """Self-heal while in recovery mode (the former TERMINAL safe mode).

        Runs on the data loop's normal cadence instead of fetching. Two rungs,
        both keyed on uptime (recovery mode is entered at boot, so monotonic
        time ≈ time in recovery):
          * a PROBATION fetch every SAFE_MODE_PROBE_INTERVAL_S — fully
            guarded; success proves the crash cause cleared (a transient API
            break, corrupted payload...), so prove health to NVM and cold
            reset into a clean NORMAL boot;
          * a full re-test reboot at SAFE_MODE_REBOOT_S — covers crashers that
            live in setup() where a probe can't reach; the stable-uptime task
            cleared the breaker minutes ago, so that boot IS normal. If the
            cause persists, the box young-crashes back here and the cycle
            repeats forever at ~hourly cost: retry-forever, never parked.
        Saving settings remains the immediate manual exit."""
        import time
        now = time.monotonic()
        up = self._uptime_s()   # app-relative: raw monotonic is huge on desktop
        if (not self._safe_mode_reboot_fired) and up >= self.SAFE_MODE_REBOOT_S:
            self._safe_mode_reboot_fired = True   # reset is a no-op on desktop
            logger.error(None, "recovery mode: timed re-test reboot")
            try:
                self.diagnostics.record_crash("recovery mode: timed re-test reboot")
            except Exception:
                pass
            await asyncio.sleep(0.5)
            self._hardware_reset()
            return
        last = self._safe_mode_last_probe
        if last is not None and now - last < self.SAFE_MODE_PROBE_INTERVAL_S:
            return
        self._safe_mode_last_probe = now
        logger.error(None, "recovery mode: probation fetch")
        try:
            ok = await self._fetch_and_build()
        except Exception as e:
            logger.error(e, "recovery-mode probation fetch failed")
            return
        if not ok:
            return
        # Probation success: prove health (note_fetch_result's ok-path zeroes
        # the breaker and ends the failure-reboot epoch), then reboot into a
        # clean normal boot — known-good state beats resuming mid-recovery.
        try:
            self.diagnostics.note_fetch_result(True, 0)
        except Exception:
            pass
        try:
            self.note_refresh_result(True)
        except Exception:
            pass
        self._clear_safemode_streak()
        logger.error(None, "recovery mode: probation fetch succeeded - "
                           "rebooting to normal")
        await asyncio.sleep(0.5)
        self._hardware_reset()
        # Desktop/sim (the reset above is a no-op): exit recovery in place so
        # the simulator and tests observe the recovery without a reboot.
        self._safe_mode = False
        self._data_stale = False
        self.update_interval = self._default_update_interval
        try:
            await self._transition_to_first_queue_content()
        except Exception:
            pass

    @staticmethod
    def _bssid() -> str:
        """Current AP's BSSID, or '?'. The site WiFi is a multi-node mesh (two
        APs, same SSID): if the BSSID in the failure-onset log differs from the
        boot-time one, the wedge follows a ROAM — the leading theory for why
        onset intervals vary (26 h stationary vs <1 h after the box moved)."""
        try:
            import wifi
            return ":".join("%02x" % b for b in wifi.radio.ap_info.bssid)
        except Exception:
            return "?"

    # ----- the wedge ledger: windowed, classified escalation -----------------
    # The one failure this box cannot repair in place is the local-stack wedge:
    # the ESP32's WiFi/lwIP session degrades until NEW outbound connects fail
    # OSError 16 (EBUSY) while surviving pooled flows and inbound keep working.
    # In-band repairs (session rebuild, socket eviction, radio bounce) were all
    # falsified on hardware; the only 100% cure is a cold reset. The ledger's
    # job is therefore pure DETECTION: classified errno-16 events from BOTH
    # refreshes and checks add timestamped strikes; enough strikes inside a
    # rolling window prove the wedge and buy exactly one budgeted cold reset.
    # Two hard-won rules (2026-07-16 night):
    #   * Windowed, never consecutive — the wedge FLAPS, and healthy moments
    #     (or one park riding a surviving pooled socket) reset any consecutive
    #     counter forever. Strikes expire ONLY by time; success never erases.
    #   * Classified, never generic — DNS failures, 5xx, a down check host,
    #     or the RSA PK_ALLOC error (-16256) are NOT cured by a reset and
    #     must never trigger one.
    WEDGE_STRIKES_MAX = 6         # ~6 min of full wedge (60 s stale retry), or
                                  # a flapping half-hour — both self-cure
    WEDGE_WINDOW_S = 30 * 60      # rolling evidence window
    RECOVERY_RESET_BUDGET = 3     # resets per unhealthy epoch; health re-arms
    # Exhausted budget is a RATE LIMIT, not a terminal fuse (2026-07-19): after
    # this much uptime one more reset is allowed anyway. Stateless — monotonic
    # restarts at boot, so each cooled-down reset first requires surviving
    # another 6 h. The old behavior ("not resetting", forever, until a healthy
    # run the wedge itself may prevent) left a persistently wedged box stale
    # for good.
    RECOVERY_BUDGET_COOLDOWN_S = 6 * 3600
    RECOVERY_BUDGET_PATH = "/check_reset_count"   # keep the fielded 3.5.17 name

    @staticmethod
    def _is_wedge_error(reason) -> bool:
        """True when a failure string carries the errno-16 (EBUSY) signature.

        Matches the shapes CircuitPython actually produces ("OSError: 16",
        "[Errno 16]", HttpClient's "...failed after 3 attempts: 16") and
        explicitly rejects mbedtls -16256 (PK_ALLOC — a memory condition,
        not the wedge)."""
        r = str(reason)
        if "-16256" in r:
            return False
        return ("OSError: 16" in r or "Errno 16" in r
                or r.rstrip().endswith(": 16"))

    def _read_recovery_reset_count(self) -> int:
        try:
            with open(self.RECOVERY_BUDGET_PATH) as f:
                return int(f.read().strip() or 0)
        except (OSError, ValueError):
            return 0

    def _write_recovery_reset_count(self, n: int) -> None:
        # Written only on escalation (rare) and cleared on health, so flash
        # wear is negligible. Unwritable FS (USB-deploy mode, desktop without
        # permission) just means the budget isn't persisted.
        import os
        try:
            if n <= 0:
                os.remove(self.RECOVERY_BUDGET_PATH)
            else:
                with open(self.RECOVERY_BUDGET_PATH, "w") as f:
                    f.write("%d\n" % n)
        except OSError:
            pass

    def _clear_safemode_streak(self) -> None:
        # /safemode.py auto-resets the board out of CircuitPython safe mode
        # (watchdog bites etc.) with a consecutive-reset counter in NVM as its
        # loop guard. A fully healthy refresh proves the app runs, so the
        # streak starts over. Same NVM offsets as safemode.py (240/241).
        try:
            import microcontroller
            nvm = microcontroller.nvm
            if nvm is not None and nvm[240] == 0x5A and nvm[241]:
                nvm[241] = 0
        except Exception:
            pass

    def note_wedge_strike(self, source: str, reason) -> bool:
        """Record one classified wedge event. Returns True when the caller
        should perform ONE budgeted cold reset (web handlers schedule it AFTER
        their response flushes; the data loop resets directly). Never raises."""
        try:
            import time
            now = time.monotonic()
            self._wedge_strikes.append(now)
            self._wedge_strikes = [t for t in self._wedge_strikes
                                   if now - t <= self.WEDGE_WINDOW_S][-16:]
            n = len(self._wedge_strikes)
            logger.error(None, "wedge strike %d/%d (%s t=%d bssid=%s): %s"
                               % (n, self.WEDGE_STRIKES_MAX, source, int(now),
                                  self._bssid(), reason))
            if n < self.WEDGE_STRIKES_MAX:
                return False
            self._wedge_strikes = []          # count afresh toward the next reset
            spent = self._read_recovery_reset_count()
            if spent >= self.RECOVERY_RESET_BUDGET:
                if self._uptime_s() < self.RECOVERY_BUDGET_COOLDOWN_S:
                    logger.error(None, "recovery reset budget exhausted (%d/%d) — "
                                       "not resetting"
                                       % (spent, self.RECOVERY_RESET_BUDGET))
                    return False
                # Cooled-down trickle: the budget bounds reset BURSTS; it must
                # never end recovery outright (design invariant 2026-07-19).
                logger.error(None, "recovery reset budget exhausted but %dh "
                                   "uptime — allowing one cooled-down reset"
                                   % int(self._uptime_s() // 3600))
            else:
                self._write_recovery_reset_count(spent + 1)
            logger.error(None, "escalation: %d wedge strikes in %d min -> cold "
                               "reset (budget %d/%d)"
                               % (self.WEDGE_STRIKES_MAX,
                                  self.WEDGE_WINDOW_S // 60,
                                  min(spent + 1, self.RECOVERY_RESET_BUDGET),
                                  self.RECOVERY_RESET_BUDGET))
            # Stamp WHY+WHEN to NVM before the reset: without this the config
            # page's "Last error" still shows some OLDER message after a wedge
            # reset, which misreads as a different failure (2026-07-17).
            try:
                self.diagnostics.record_crash(
                    "wedge cold reset (%s): %s" % (source, reason))
            except Exception:
                pass
            return True
        except Exception:
            return False

    def note_check_result(self, definitive: bool, reason: str = "") -> bool:
        """Feed one update-check outcome into the health accounting.

        A definitive answer (update available / up to date) re-arms the
        recovery-reset budget — it does NOT erase wedge strikes (the wedge
        flaps; one lucky check between episodes must not destroy the
        evidence). A failed check adds a wedge strike only when its reason
        carries the errno-16 signature; other failures (DNS, host down, TLS
        memory) are logged but never rebooted for. Returns True when the
        caller should schedule ONE budgeted cold reset AFTER its HTTP
        response flushes. Never raises."""
        try:
            if definitive:
                self._consecutive_check_failures = 0
                self._write_recovery_reset_count(0)   # health re-arms the budget
                return False
            self._consecutive_check_failures += 1
            logger.error(None, "update check failed (consecutive=%d): %s"
                               % (self._consecutive_check_failures, reason))
            if self._is_wedge_error(reason):
                return self.note_wedge_strike("check", reason)
            return False
        except Exception:
            return False

    async def _teardown_active_content(self) -> None:
        """Release the on-screen content's persistent overlay before a status frame.

        A ride's large wait NUMBER is a display *layer* (RideScreenContent's
        DripReveal/SwarmReveal), which the per-frame ``display.clear()``
        deliberately leaves untouched so an effect can span frames — it is only
        released by the content's ``stop()``. The "Updating / Times" status frame
        (_status) is drawn from this data task, OUTSIDE the display loop, and is
        immediately followed by the *blocking* fetch; so without stopping the
        current content here, the previous ride's number ghosts on top of
        "Updating / Times".

        We stop the overlay but DELIBERATELY DO NOT clear the queue: clearing it
        meant a failed refresh (flaky network) left the queue empty and the panel
        BLACK until a later refresh happened to succeed — the field "goes black"
        bug. Ghosting during the status frame is instead prevented by suspending
        render (``self.suspended_render()`` in update_data; the base display loop
        skips drawing the queue while suspended), which keeps the loop from
        redrawing the old content while leaving the items in place, so a failed
        fetch resumes last-good (stale) content.
        build_content_queue() rebuilds the queue in place on success.
        Defensive — never raises into the refresh."""
        queue = self.content_queue
        if queue is None:
            return
        try:
            current = queue.get_current_content()
            if current is not None:
                await current.stop()
        except Exception as e:
            logger.error(e, "teardown active content failed")
