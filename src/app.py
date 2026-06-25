"""ThemeParkWaits application — built on the refactored ScrollKit library.

Port milestone A (in progress). ``ThemeParkApp`` extends ``ScrollKitApp``:
``setup()`` runs the pre-run sequence (currently: splash → fetch park list;
WiFi/onboarding/OTA/NTP land in T018/T027), the data process calls
``update_data()`` every ``update_interval`` to refresh wait times and rebuild the
content queue, and the display process renders the queue.

Copyright 2024 3DUPFitters LLC
"""
from __future__ import annotations

from scrollkit.app.base import ScrollKitApp

from scrollkit.utils.error_handler import ErrorHandler

from src.settings_schema import make_settings
from src.api.theme_park_service import ThemeParkService
from src.ui.content_builder import build_content_queue

logger = ErrorHandler("error_log")


class ThemeParkApp(ScrollKitApp):
    """Theme-park wait-time display application."""

    # Matrix Portal S3 geometry; bit_depth=4 is the recommended fast refresh (FR-022).
    WIDTH = 64
    HEIGHT = 32
    BIT_DEPTH = 4

    def __init__(self, *, enable_web: bool = True, update_interval: int = 300,
                 http_client=None, settings=None) -> None:
        super().__init__(enable_web=enable_web, update_interval=update_interval)
        self.settings = settings or make_settings()
        if http_client is None:
            from scrollkit.network.http_client import HttpClient
            http_client = HttpClient()
        self.http_client = http_client
        self.service = ThemeParkService(self.http_client, self.settings)
        try:
            from src.ota_glue import OTAGlue
            self.ota = OTAGlue()
        except Exception as e:  # OTA is optional; never block construction
            print("OTA unavailable:", e)
            self.ota = None
        # The first data refresh happens at boot while setup()'s "Updating / Parks"
        # frame is still up; later refreshes paint their own indicator (see
        # update_data) since they hit the internet with no boot context on screen.
        self._initial_refresh_done = False

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

    async def setup(self) -> None:
        """Pre-run sequence (boot state machine — partial; T018/T027 add WiFi/OTA/NTP)."""
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
        # looks better) flies in and assembles "THEME PARK WAITS"
        # (scrollkit.effects.swarm_reveal), then disperses and holds. Pixel map
        # stays app-side (reveal_splash.get_theme_park_waits_pixels).
        try:
            from src.ui.reveal_splash import get_theme_park_waits_pixels
            from scrollkit.effects.swarm_reveal import show_swarm_splash
            await show_swarm_splash(self.display, get_theme_park_waits_pixels(),
                                    num_birds=20, bird_speed=5.0, hold_seconds=1.5)
        except Exception as e:
            logger.error(e, "swarm splash failed")

        # Network bring-up (T017/T018). Dev mode auto-connects and skips NTP/mDNS;
        # the AP first-boot onboarding path (no creds) is hardware-only — TODO finish + verify.
        await self._init_network()

        # Install a pending OTA update before fetching (reboots if one is staged).
        if self.ota is not None:
            try:
                self.ota.attach_display(self.display)
                await self.ota.install_pending()
            except Exception as e:
                print("OTA install_pending failed:", e)

        # Park-list fetch is the big blocking call (/destinations + retries) — tell
        # the user before the panel would otherwise go black on it.
        await self._status("Parks")
        try:
            await self.service.initialize()  # fetch park list + load park/vacation settings
        except Exception as e:  # never crash boot (FR-014)
            logger.error(e, "service.initialize failed")

    async def _status(self, step, color=0xFFAA00) -> None:
        """Two-row boot status: a constant "Updating" header over the current step
        ("Wi-Fi" / "Clock" / "Parks"), both horizontally centered.

        Boot makes several blocking network calls between the splash and the first
        data frame while the display loop isn't running yet, so without a frame in
        between the panel sits black for what can be minutes and the user assumes it
        hung. The header says what's happening; the step row says which one (a step
        that lingers points straight at the slow call). Defensive — never raises
        into boot. Keep ``step`` short: ~10 chars fit at the default font.
        """
        disp = self.display
        if not disp:
            return
        try:
            await disp.clear()
            await self._draw_centered(disp, "Updating", 11, color)
            if step:
                await self._draw_centered(disp, step, 27, color)
            await disp.show()
        except Exception:
            pass

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

    async def _init_network(self):
        """WiFi station connect (+ HTTP session, NTP, mDNS) — CircuitPython hardware only.

        Gated on the real platform (NOT the library's ``is_dev_mode()``, which can
        misfire if a stray ``wifi`` package is importable on desktop and would then
        make ``setup()`` block on failing NTP/network calls before the window ever
        renders). On desktop the HttpClient uses urllib directly — no WiFi/NTP/mDNS
        needed. First-boot AP onboarding (no creds) is device-only and still TODO.
        """
        import sys
        if not (hasattr(sys, "implementation") and sys.implementation.name == "circuitpython"):
            return  # desktop / simulator: nothing to bring up
        try:
            from scrollkit.network.wifi_manager import WiFiManager
            self.wifi = WiFiManager(self.settings)
            await self._status("Wi-Fi")
            # connect() reports per-attempt status ("Attempt n/3") on the step row
            # via this callback, so a slow/retrying join shows instead of black.
            connected = await self.wifi.connect(display_callback=self._status)
            if connected:
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
                    await self._status("Clock")
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
                    from src.net.mdns_helper import advertise
                    # Retain the mdns.Server for the app's lifetime: if it is garbage
                    # collected, the responder stops answering and <domain>.local
                    # resolution dies after the first query (intermittent .local).
                    self.mdns_server = advertise(
                        self.settings.get("domain_name", "themeparkwaits"))
                except Exception as e:
                    logger.error(e, "mDNS advertise failed")
        except Exception as e:
            logger.error(e, "network init failed")

    async def update_data(self) -> None:
        """Refresh wait times for the selected park(s) and rebuild the content queue."""
        # Every refresh hits the internet (themeparks.wiki), and the synchronous fetch
        # freezes the display while it runs — so paint a frame first, or a hang/delay
        # looks like a dead screen. Skip only the first (boot) refresh, where
        # setup()'s "Updating / Parks" frame is already up; every later refresh
        # (the 5-min cycle, or a settings-change refresh) shows "Updating / Times".
        if self._initial_refresh_done:
            await self._status("Times")
        else:
            self._initial_refresh_done = True
        pl = self.service.park_list
        try:
            if pl is not None:
                if getattr(pl, "selected_parks", None):
                    await self.service.update_selected_parks()
                elif pl.current_park.is_valid():
                    await self.service.update_current_park()
            build_content_queue(self.content_queue, pl, self.settings, self.service.vacation)
        except Exception as e:  # keep prior queue/snapshot, never crash (FR-014)
            logger.error(e, "update_data failed")
