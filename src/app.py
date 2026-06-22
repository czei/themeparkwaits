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

    async def create_display(self):
        """Return our display (UnifiedDisplay + scaled-text), auto-detects sim/hardware."""
        from src.ui.tpw_display import ThemeParkDisplay
        return ThemeParkDisplay(width=self.WIDTH, height=self.HEIGHT, bit_depth=self.BIT_DEPTH)

    async def create_web_server(self):
        """Return the config web server (library server + our handler/page).

        On CircuitPython the adafruit_httpserver ``Server`` needs a socket pool
        from the WiFi radio; the library expects the app to inject it (it owns
        networking). On desktop the dev adapter uses stdlib http.server and
        ignores it. The ``wifi``/``socketpool`` imports stay behind the platform
        guard so the simulator never touches them.
        """
        try:
            from scrollkit.web import SLDKWebServer
            from src.web.config_server import make_handler_class
            socket_pool = None
            import sys
            if hasattr(sys, "implementation") and sys.implementation.name == "circuitpython":
                import socketpool
                import wifi
                socket_pool = socketpool.SocketPool(wifi.radio)
            return SLDKWebServer(app=self, handler_class=make_handler_class(self),
                                 static_dir="src/www", socket_pool=socket_pool)
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

        # Opening reveal splash (every LED on -> wink off to "THEME PARK WAITS").
        # This also realizes the window immediately (it refreshes each step).
        try:
            from src.ui.reveal_splash import show_reveal_splash
            await show_reveal_splash(self.display)
        except Exception as e:
            logger.error(e, "reveal splash failed")

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

        try:
            await self.service.initialize()  # fetch park list + load park/vacation settings
        except Exception as e:  # never crash boot (FR-014)
            logger.error(e, "service.initialize failed")

    async def show_loading(self) -> None:
        """Pre-flush a static 'updating' frame before the blocking fetch (B2/FR-029)."""
        if not self.display:
            return
        try:
            await self.display.clear()
            await self.display.draw_text("Updating...", 2, 12, 0xFFAA00)
            await self.display.show()
        except Exception:
            pass

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
            connected = await self.wifi.connect()
            if connected:
                try:
                    session = self.wifi.create_http_session()
                    if session is not None and hasattr(self.http_client, "session"):
                        self.http_client.session = session
                except Exception as e:
                    logger.error(e, "create_http_session failed")
                try:
                    from scrollkit.utils.system_utils import set_system_clock
                    await set_system_clock(self.http_client)
                except Exception as e:
                    logger.error(e, "set_system_clock failed")
                try:
                    from src.net.mdns_helper import advertise
                    advertise(self.settings.get("domain_name", "themeparkwaits"))
                except Exception as e:
                    logger.error(e, "mDNS advertise failed")
        except Exception as e:
            logger.error(e, "network init failed")

    async def update_data(self) -> None:
        """Refresh wait times for the selected park(s) and rebuild the content queue."""
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
