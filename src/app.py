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

    def __init__(self, *, enable_web: bool = True, update_interval: int = 300,
                 http_client=None, settings=None) -> None:
        # enable_watchdog=True: opt this app into the hardware watchdog (CircuitPython
        # only; a no-op in the simulator) so a true freeze — e.g. a hung synchronous
        # socket — self-recovers via reset instead of sitting black until a
        # power-cycle. The timeout (and its clamp to the ESP32-S3 hardware max) and
        # the HTTP request timeout are the library's defaults now.
        # enable_auto_reboot: last-resort self-heal, fed via note_refresh_result()
        # in update_data(). 12 consecutive failures at the 60 s stale-retry cadence
        # ≈ 12+ minutes of continuous outage before the hammer — long enough that a
        # brief API/server blip never reboot-loops the box, short enough that the
        # 2026-07-15 outbound-EBUSY wedge (which stranded the box for 90+ min with
        # no self-heal rung at all) ends without a hand on the reset button. The
        # radio bounce at every 3rd failure (see _escalate_fetch_failures) should
        # cure that wedge long before this fires.
        super().__init__(enable_web=enable_web, update_interval=update_interval,
                         enable_watchdog=True, enable_auto_reboot=True,
                         max_refresh_failures=12)
        self.settings = settings or make_settings()
        if http_client is None:
            from scrollkit.network.http_client import HttpClient
            http_client = HttpClient()
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
        # Set when repeated fault-reboots tripped the breaker: skip network fetches
        # and just keep the config UI reachable so the user can fix the cause.
        self._safe_mode = False

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
                self.ota.attach_display(self.display)
                # A persisted /install request downloads HERE — right after
                # network bring-up, before parks/content/web allocate — because
                # the GitHub RSA-2048 handshake dies at runtime (mbedtls
                # PK_ALLOC_FAILED; ledger attempt #5). Staging success makes
                # has_pending() true and install_pending() applies it below.
                try:
                    await self.ota.stage_pending_request()
                except AttributeError:
                    pass  # older glue without boot-time staging
                had_pending = self.ota.has_pending()
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
        # fetching and just show a reconfigure message while the web/AP config UI
        # stays reachable (network was brought up above). Prevents an endless
        # reboot cycle from the watchdog / last-resort reset.
        if self.diagnostics.safe_mode:
            self._safe_mode = True
            logger.error(None, "entering safe mode after repeated reboots")
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
                # Healthy boot: clear the reboot-loop streak so a single past crash
                # never accumulates toward safe mode.
                self.diagnostics.note_clean_run()
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
        """Replace the queue with a safe-mode notice when the boot-loop breaker
        trips, pointing the user at the still-reachable config UI. Never raises."""
        try:
            q = self.content_queue
            if q is None:
                return
            q.clear()
            from scrollkit.display.content import ScrollingText
            domain = self.settings.get("domain_name", "themeparkwaits")
            q.add(ScrollingText("Safe mode - reconfigure at %s.local" % domain,
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
                try:
                    session = self.wifi.create_http_session()
                    if session is not None and hasattr(self.http_client, "session"):
                        self.http_client.session = session
                except Exception as e:
                    logger.error(e, "create_http_session failed")
                # Give the OTA check its rung-3 radio bounce (see ota_glue).
                if self.ota is not None:
                    self.ota.wifi_manager = self.wifi
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
            return  # boot-loop breaker tripped: no fetching until reconfigured
        if self._skip_initial_update:
            self._skip_initial_update = False
            return
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

        # Track staleness and retry faster while stale, so a transient network
        # blip doesn't strand the user on hours-old times.
        self._data_stale = not ok
        if ok:
            self._consecutive_fetch_failures = 0
            self.update_interval = self._default_update_interval
        else:
            self._consecutive_fetch_failures += 1
            self.update_interval = self._stale_retry_interval
            logger.error(None, "refresh failed; keeping last-good content "
                               "(consecutive=%d)" % self._consecutive_fetch_failures)
            await self._escalate_fetch_failures()
        # Feed the base watchdog ladder (enable_auto_reboot): without this call
        # the last-resort reboot can never fire — exactly how the 2026-07-15
        # wedge stranded the box.
        try:
            self.note_refresh_result(ok, reason=None if ok else "fetch failed")
        except Exception:
            pass
        try:
            self.diagnostics.note_fetch_result(ok, self._consecutive_fetch_failures)
        except Exception:
            pass

    # Radio-bounce escalation: every this-many consecutive fetch failures, force
    # a WiFi disconnect+reassociate before the base watchdog's last-resort
    # reboot (which fires at max_refresh_failures=12). Proven cure for the
    # 2026-07-15 wedge: outbound connects all EBUSY while inbound worked, so
    # nothing that watches "is the link up" ever acted.
    RADIO_BOUNCE_EVERY = 3

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

    async def _escalate_fetch_failures(self) -> None:
        """Rung 2 of the failure ladder (rung 1 = retries/session rebuild inside
        HttpClient; rung 3 = the base auto-reboot). Never raises."""
        n = self._consecutive_fetch_failures
        if n == 0 or n % self.RADIO_BOUNCE_EVERY != 0:
            return
        if n >= self.max_refresh_failures:
            return  # the auto-reboot fires right after — don't waste a bounce
        wifi_mgr = getattr(self, "wifi", None)
        bounce = getattr(wifi_mgr, "bounce", None)
        if bounce is None:
            return  # desktop, or an older library without bounce()
        logger.error(None, "escalation: bouncing the radio after %d consecutive "
                           "fetch failures (bssid=%s)" % (n, self._bssid()))
        try:
            ok = await bounce()
            # Reassociation alone does NOT cure the wedge: a session built on
            # the pre-bounce association keeps its stale SocketPool plumbing
            # (2026-07-15 overnight: bounces at 3/6/9 logged "reassociated",
            # fetches kept failing, the box rode the ladder to auto-reboot).
            # A FULL session rebuild — fresh pool + ssl + Session — is what the
            # REPL cure always did.
            rebuild = getattr(self.http_client, "rebuild_session", None)
            if rebuild is not None:
                rebuild()
            else:  # older library: best effort
                closer = getattr(self.http_client, "close_pooled_sockets", None)
                if closer is not None:
                    closer()
            import gc
            gc.collect()
            logger.error(None, "escalation: radio bounce %s, session rebuilt "
                               "(bssid=%s)"
                               % ("reassociated" if ok else "FAILED", self._bssid()))
        except Exception as e:
            logger.error(e, "escalation: radio bounce crashed")

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
