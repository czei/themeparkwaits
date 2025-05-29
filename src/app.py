"""
Main application for Theme Park Waits.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import json
import gc
import time
import sys

from src.config.settings_manager import SettingsManager
from src.api.theme_park_service import ThemeParkService
from src.ui.message_queue import MessageQueue
from src.utils.error_handler import ErrorHandler
from src.utils.timer import Timer
from src.network.wifi_manager import WiFiManager
from src.utils.url_utils import load_credentials
from src.ui.display_factory import is_dev_mode, is_circuitpython
from src.ota.ota_updater import OTAUpdater

# Initialize logger
logger = ErrorHandler("error_log")

# GitHub repository configuration for OTA updates
GITHUBREPO = 'https://github.com/Czeiszperger/themeparkwaits.release'
# TODO: Move token to a secure location
TOKEN = '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'


class ThemeParkApp:
    """
    Main application class for Theme Park Waits
    """

    def __init__(self, display, http_client):
        """
        Initialize the application
        
        Args:
            display: The display to use
            http_client: The HTTP client for network requests
        """
        self.display = display
        self.http_client = http_client
        self.socket_pool = None
        self.settings_manager = SettingsManager("settings.json")
        self.theme_park_service = ThemeParkService(self.http_client, self.settings_manager)
        self.message_queue = MessageQueue(display, 4)
        self.update_timer = Timer(300)  # Update every 5 minutes
        self.wifi_manager = WiFiManager(self.settings_manager)
        
        # Initialize OTA updater
        # Check for pre-release flag in settings for testing
        use_prerelease = self.settings_manager.get("use_prerelease", False)
        self.ota_updater = OTAUpdater(
            http_client, 
            GITHUBREPO, 
            main_dir="src",
            headers={'Authorization': f'token {TOKEN}'},
            use_prerelease=use_prerelease
        )
        
        # Initialize socket_pool differently based on platform
        if is_dev_mode():
            # In dev mode, socket_pool will be created differently
            self.web_server = None
            logger.info("Development mode - web server will be initialized differently")
        else:
            # In CircuitPython mode
            try:
                import socketpool
                import wifi
                self.web_server = socketpool.SocketPool(wifi.radio)
            except ImportError as e:
                logger.error(e, "Error importing CircuitPython modules")
                self.web_server = None

        # Set up the callback for session updates in the WiFi manager
        self.wifi_manager.update_http_clients = self.update_http_client

    async def initialize_all(self):
        """Initialize the application"""
        logger.info("Initializing Theme Park Waits application")

        # Set display colors from settings
        if hasattr(self.display, 'set_colors'):
            self.display.set_colors(self.settings_manager)

        # Show splash screen first before any network operations
        await self.display.show_splash(12, True)

        # Create a task for network and data initialization (runs in background)
        # TODO: Figure out how to make the initialization process async to talk to an event-drive display to update users.
        # init_task = asyncio.create_task(self._initialize_background_data())

        logger.info("Starting initialization sequence...")
        await self._initialize_wifi_password()
        logger.info("WiFi password initialized")
        await self._initialize_wifi()
        logger.info("WiFi initialized")
        
        # Check for pending OTA update AFTER WiFi is connected
        await self._check_and_install_pending_update()
        
        await self._initialize_clock()
        logger.info("Clock initialized")
        await self._initialize_park_list()
        logger.info("Park list initialized")
        await self._initialize_wait_times()
        logger.info("Wait times initialized")
        logger.info("All initialization complete")

    async def _initialize_wifi_password(self):
        # Load Current Wifi Password
        ssid, password = load_credentials()

        #
        # True when first starting device or the Wifi has been reset
        #
        if ssid != "" and password != "":
            return

        # Skip WiFi configuration in dev mode
        if is_dev_mode():
            logger.info("Dev mode - skipping WiFi configuration")
            return

        # Have to configure Wi-FI before the network will work
        # Run the Wifi configure GUI and the configure message at the same time
        try:
            self.wifi_manager.start_access_point()
            self.wifi_manager.start_web_server()
            #wifimgr.web_server.serve_forever(str(wifi.radio.ipv4_address_ap))

            # Pass a lambda that calls is_wifi_password_configured instead of calling it directly
            asyncio.run(asyncio.gather(
                self.wifi_manager.run_web_server(lambda: self.is_wifi_password_configured()),
                self.run_configure_wifi_message()
            ))

            self.wifi_manager.web_server.stop()
            self.wifi_manager.stop_access_point()

        except OSError as e:
            logger.error(e,"Exception starting wifi access point and web server: {e}")

    async def _initialize_wifi(self):
        """Initialize network and theme park data in the background"""
        # Show WiFi connection message with actual SSID
        ssid = self.wifi_manager.ssid
        logger.debug(f"Display implementation type: {type(self.display)}")
        await self.display.show_scroll_message(f"Connecting to WiFi {ssid}")

        # Initialize networking with status updates
        connected = await self.wifi_manager.connect()

        # Show appropriate message based on connection result
        if connected:
            await self.display.show_scroll_message(f"Connected ...")
            # Create HTTP session after WiFi is connected
            if not is_dev_mode():
                # Only in hardware mode
                import socketpool
                import wifi
                self.socket_pool = socketpool.SocketPool(wifi.radio)
            else:
                # In dev mode, create a mock socket pool if needed
                logger.info("Dev mode - using simulated socket pool")
                self.socket_pool = "DEV_SOCKET_POOL"  # Placeholder value
                
            await self._initialize_http_client(self.socket_pool)
        else:
            if is_dev_mode():
                # In dev mode, proceed anyway
                await self.display.show_scroll_message("Dev mode - continuing without WiFi")
                await self._initialize_http_client(None)
            else:
                await self.display.show_scroll_message("WiFi Failed - Check settings")

    async def run_configure_wifi_message(self):
        while self.is_wifi_password_configured() is False:
            setup_text = f"Connect your phone to Wifi channel {self.wifi_manager.AP_SSID}, password \"{self.wifi_manager.AP_PASSWORD}\". Then load page http://192.168.4.1"
            await self.display.show_scroll_message(setup_text)
    
    async def _check_and_install_pending_update(self):
        """Check if an OTA update was downloaded and needs installation"""
        try:
            if self.ota_updater.update_available_at_boot():
                logger.info("Pending OTA update found, installing...")
                
                # Set progress callback to show on display
                async def show_progress(msg):
                    await self.display.show_scroll_message(msg)
                    await asyncio.sleep(0.1)  # Brief pause for display
                
                self.ota_updater.update_progress_callback = lambda msg: asyncio.create_task(show_progress(msg))
                
                await self.display.show_scroll_message("Installing update... Do not unplug!")
                await asyncio.sleep(2)
                
                # Since we need network for installation, check if WiFi is configured
                if self.is_wifi_password_configured():
                    ssid, password = load_credentials()
                    # Note: install_update_if_available_after_boot expects sync code
                    # We'll need to handle this carefully
                    if self.ota_updater.install_update_if_available_after_boot(ssid, password):
                        await self.display.show_scroll_message("Update complete! Rebooting...")
                        await asyncio.sleep(2)
                        
                        # Reboot the device
                        if is_circuitpython():
                            import supervisor
                            supervisor.reload()
                        else:
                            logger.info("Dev mode - would reboot here")
                else:
                    logger.warning("OTA update pending but WiFi not configured")
                    await self.display.show_scroll_message("Update pending - configure WiFi first")
                    await asyncio.sleep(3)
                    
        except Exception as e:
            logger.error(e, "Error checking for pending OTA update")
            # Continue booting even if OTA check fails

    async def try_wifi_until_connected(self):
        # Skip in dev mode
        if is_dev_mode():
            logger.info("Dev mode - skipping WiFi connection")
            return
            
        ssid, password = load_credentials()

        # Try to connect 3 times before giving up in
        # case the Wifi is unstable.
        attempts = 1
        import wifi
        if wifi.radio.connected is True:
            logger.debug(f"Already connected to wifi {ssid}: at {wifi.radio.ipv4_address}")
        else:
            logger.debug(f"Connecting to wifi {ssid}: at {wifi.radio.ipv4_address}")

        while wifi.radio.connected is not True:
            try:
                await self.display.show_scroll_message(f"Connecting to Wifi: {ssid}")
                wifi.radio.connect(ssid, password)
            except (RuntimeError) as e:
                logger.error(e,f"Wifi runtime error: {str(e)} at {wifi.radio.ipv4_address}")
                await self.display.show_scroll_message(f"Wifi runtime error: {str(e)}")
            except (ConnectionError) as e:
                logger.error(e, f"Wifi connection error: {str(e)} at {wifi.radio.ipv4_address}")
                if "Authentication" in str(e):
                    await self.display.show_scroll_message(f"Bad password.  Please reset the LED scroller using the INIT button as described in the instructions.")
                else:
                    await self.display.show_scroll_message(f"Wifi connection error: {str(e)}")
            except (ValueError) as e:
                logger.error(e, "Wifi value error")
                # logger.error(f"Wifi value error: {str(e)} at {wifi.radio.ipv4_address}")
                await self.display.show_scroll_message(f"Wifi value error: {str(e)}")

            except OSError as e:
                logger.error(e, "Unknown error connecting to Wifi")


    async def _initialize_park_list(self):
        # Initialize theme park service
        # await self.display.show_scroll_message("Downloading list of theme parks...")
        await self.theme_park_service.initialize()

    async def _initialize_wait_times(self):
        # Update data for the first time, not checking timer
        # (This will show its own update message)
        await self.update_data(True)

        # Get accurate wait until next update
        self.update_timer.reset()

    async def _initialize_clock(self):
        # Skip system clock in dev mode
        if is_dev_mode():
            logger.info("Dev mode - skipping system clock setup")
            return
            
        # Takes too much time
        await self.display.show_scroll_message("Setting time...")
        try:
            logger.info("Setting system clock...")
            # Get the actual socket pool, not from HTTP client
            import wifi
            
            # Import set_system_clock function
            from src.utils.system_utils import set_system_clock
            
            # Pass both HTTP client and socketpool for flexibility
            await set_system_clock(self.http_client, self.socket_pool)
        except Exception as clock_error:
            logger.error(clock_error, "Warning: Could not set system clock, continuing without it")
            # Continue initialization even if clock setting fails

    async def update_data(self, ignore_timer):
        """Update theme park data from the API"""
        # Check if there's a valid park selected
        has_selected_parks = (hasattr(self.theme_park_service.park_list, 'selected_parks') and 
                             self.theme_park_service.park_list.selected_parks)
        has_current_park = (self.theme_park_service.park_list and 
                           self.theme_park_service.park_list.current_park.is_valid())
        
        if not has_selected_parks and not has_current_park:
            # No parks selected, no need to update data
            # Just regenerate message queue to show prompt to select park
            self.message_queue.init()
            # No park selected - show message to choose a park
            domain_name = self.settings_manager.get("domain_name", "themeparkwaits")
            await self.message_queue.add_scroll_message(f"Choose theme park at http://{domain_name}.local", 1)
            await self.message_queue.add_splash(4, True)  # Use reveal animation
            return

        # Check for forced update flag in theme_park_service
        force_update = False
        if hasattr(self.theme_park_service, 'update_needed'):
            force_update = self.theme_park_service.update_needed
            # Reset the flag
            self.theme_park_service.update_needed = False
        
        # Check if we just need to rebuild the queue (e.g., after sort settings change)
        queue_rebuild_only = False
        if hasattr(self.theme_park_service, 'queue_rebuild_needed'):
            queue_rebuild_only = self.theme_park_service.queue_rebuild_needed
            # Reset the flag
            self.theme_park_service.queue_rebuild_needed = False

        # Check if update is needed
        timer_ready = self.update_timer.finished()
        cycle_complete = self.message_queue.has_completed_cycle
        
        # If we only need to rebuild the queue (no data fetch needed)
        if queue_rebuild_only:
            logger.info("Rebuilding message queue after settings change")
            # Log current settings before rebuild
            group_by_park = self.settings_manager.get("group_by_park", False)
            sort_mode = self.settings_manager.get("sort_mode", "alphabetical")
            logger.debug(f"Settings before queue rebuild: group_by_park={group_by_park}, sort_mode={sort_mode}")
            # Skip the data fetch, jump straight to rebuilding the queue
            self.message_queue.init()
            await self.build_messages()
            return
        
        # Don't update unless: timer is ready AND (cycle is complete OR we're forcing/ignoring timer)
        if not timer_ready and not ignore_timer and not force_update:
            return
        
        # Even if timer is ready, wait for message queue to complete at least one cycle
        # (unless we're forcing the update or ignoring timer)
        if timer_ready and not cycle_complete and not ignore_timer and not force_update:
            logger.debug("Timer ready but waiting for message queue to complete cycle")
            return

        logger.info("Updating theme park data")

        # Show scrolling message that data is being updated
        if has_selected_parks:
            num_parks = len(self.theme_park_service.park_list.selected_parks)
            if num_parks == 1:
                park_name = self.theme_park_service.park_list.selected_parks[0].name
                await self.display.show_scroll_message(f"Updating {park_name} wait times from queue-times.com...")
            else:
                await self.display.show_scroll_message(f"Updating {num_parks} parks from queue-times.com...")
        else:
            park_name = self.theme_park_service.park_list.current_park.name
            await self.display.show_scroll_message(f"Updating {park_name} wait times from queue-times.com...")

        # Reset the timer immediately to prevent multiple updates
        self.update_timer.reset()

        # Update park data
        if has_selected_parks:
            await self.theme_park_service.update_selected_parks()
        else:
            await self.theme_park_service.update_current_park()

        # Regenerate the message queue
        self.message_queue.init()
        await self.build_messages()

        # Force garbage collection to free memory
        gc.collect()

    async def build_messages(self):
        """Build the message queue for displaying information"""

        # Always add splash screen at front
        await self.message_queue.add_splash(4, True)  # Use reveal animation

        # Get domain name for configuration URL
        domain_name = self.settings_manager.get("domain_name", "themeparkwaits")
        
        # Check if parks are selected
        has_selected_parks = (hasattr(self.theme_park_service.park_list, 'selected_parks') and 
                             self.theme_park_service.park_list.selected_parks)
        has_current_park = (self.theme_park_service.park_list and 
                           self.theme_park_service.park_list.current_park.is_valid())
        
        if not has_selected_parks and not has_current_park:
            return
        
        # Park is selected - show regular configuration message
        await self.message_queue.add_scroll_message(f"Configure at http://{domain_name}.local", 1)

        # Add vacation information if set
        await self.message_queue.add_vacation(self.theme_park_service.vacation)

        # Add park data
        await self.message_queue.add_rides(self.theme_park_service.park_list)

        # Add attribution message(s)
        if has_selected_parks:
            # Add attribution for each selected park
            for park in self.theme_park_service.park_list.selected_parks:
                await self.message_queue.add_required_message(park.name)
        else:
            await self.message_queue.add_required_message(
                self.theme_park_service.park_list.current_park.name)

    async def _initialize_http_client(self, socket_pool):
        """Initialize the HTTP client with a fresh session after WiFi is connected"""
        try:
            if is_dev_mode():
                # In dev mode, use urllib-based session (no need for socket pool)
                logger.info("Dev mode - using urllib-based HTTP client")
                
                # The HttpClient will automatically use urllib when adafruit_requests is unavailable
                # We don't need to create a session, the HttpClient will handle it
                self.update_http_client(None)
                logger.info("HTTP client successfully initialized in dev mode")
                return
                
            # Import necessary modules for CircuitPython
            import ssl
            import socketpool
            import wifi
            import adafruit_requests

            # Create a socket pool and session
            logger.info("Creating new socket pool and HTTP session after WiFi connection")
            # pool = socketpool.SocketPool(wifi.radio)
            ssl_context = ssl.create_default_context()
            session = adafruit_requests.Session(socket_pool, ssl_context)

            # Update the HTTP client with the new session
            self.update_http_client(session)
            logger.info("HTTP client successfully initialized with new session")

        except Exception as e:
            logger.error(e, "Failed to initialize HTTP client")

    def update_http_client(self, session):
        """
        Update the HTTP client with a new session
        
        Args:
            session: The new HTTP session
        """
        try:
            if hasattr(self.http_client, 'session'):
                self.http_client.session = session
                logger.info("HTTP client session updated")

        except Exception as e:
            logger.error(e, "Error updating HTTP client session")

    async def handle_web_request(self, request_path, query_params):
        """
        Handle a web request from the configuration interface
        
        Args:
            request_path: The requested path
            query_params: Query parameters from the request
            
        Returns:
            A dictionary with response data
        """
        if query_params:
            self.theme_park_service.parse_query_params(query_params)

            # Clear the message queue and rebuild it
            self.message_queue.init()
            await self.build_messages()

        # Prepare response data
        response = {
            "success": True,
            "settings": self.settings_manager.settings
        }

        if self.theme_park_service.park_list:
            park_list = []
            for park in self.theme_park_service.park_list.park_list:
                park_list.append({
                    "id": park.id,
                    "name": park.name
                })
            response["parks"] = park_list

            if self.theme_park_service.park_list.current_park.is_valid():
                response["current_park"] = {
                    "id": self.theme_park_service.park_list.current_park.id,
                    "name": self.theme_park_service.park_list.current_park.name,
                    "ride_count": len(self.theme_park_service.park_list.current_park.rides)
                }

        return response

    def start_web_server(self, socket_pool):
        """
        Start the web server with enhanced reliability features

        Args:
            socket_pool: The socket pool to use

        Returns:
            The web server instance
        """
        # Use development web server in dev mode
        if is_dev_mode():
            try:
                from src.network.dev_web_server import DevThemeParkWebServer
                logger.info("Dev mode - starting development web server")
                dev_server = DevThemeParkWebServer(self)
                dev_server.start()
                logger.info("Development web server started at http://localhost:8080")
                return dev_server
            except Exception as e:
                logger.error(e, "Failed to start development web server")
                return None
            
        # Apply HTTP response patch to handle client disconnections gracefully
        # try:
        #     from src.network.http_response_patch import apply_http_response_patch
        #     patch_result = apply_http_response_patch()
        #     if patch_result:
        #         logger.info("HTTP response patch applied successfully")
        #     else:
        #         logger.warning("HTTP response patch could not be applied")
        # except ImportError:
        #     logger.warning("HTTP response patch module not found")
        
        from src.network.web_server import ThemeParkWebServer

        # Create and start web server
        web_server = ThemeParkWebServer(socket_pool, self)

        try:
            import wifi
            ip_address = wifi.radio.ipv4_address
            logger.info(f"Starting web server on IP: {ip_address}")

            # Start the web server with explicit IP binding
            web_server.start(ip_address)

            # Verify if server is running
            if web_server.is_running:
                logger.info(f"Web server successfully started at http://{ip_address}")
            else:
                logger.error(ValueError("Web server failed to start"), "Web server did not start properly")

            return web_server
        except Exception as e:
            logger.error(e, "Failed to start web server")
            return None

    async def run_display_loop(self):
        """Run the display update loop"""
        while True:
            try:
                # Update data if needed
                await self.update_data(False)

                # Show the next message in the queue
                await self.message_queue.show()

                # Small delay to prevent CPU hogging
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(e, "Error in display loop")
                await asyncio.sleep(1)  # Delay to prevent rapid error loops

    async def run_web_server_loop(self, web_server):
        """Run the web server polling loop with improved reliability"""
        if not web_server:
            return

        # Track server health
        consecutive_errors = 0
        max_consecutive_errors = 5
        last_restart_time = 0
        restart_cooldown = 60  # seconds between full server restarts

        while True:
            try:
                # Check if web server is running
                if not web_server.is_running:
                    # Server is not running - attempt to restart it
                    logger.info("Web server not running, attempting restart")
                    
                    # Check cooldown period
                    current_time = time.monotonic()
                    if current_time - last_restart_time > restart_cooldown:
                        last_restart_time = current_time
                        
                        # Create a new web server instance
                        new_server = self.start_web_server(self.socket_pool)
                        if new_server and new_server.is_running:
                            web_server = new_server
                            logger.info("Successfully created new web server instance")
                            consecutive_errors = 0
                        else:
                            logger.debug("Failed to create new web server instance")
                            # Longer pause before next attempt
                            await asyncio.sleep(5)
                    else:
                        # Still in cooldown period
                        logger.debug(f"In restart cooldown period ({restart_cooldown - (current_time - last_restart_time):.1f}s remaining)")
                        await asyncio.sleep(10)
                    continue

                # Poll web server for requests
                poll_result = await web_server.poll()

                # If polling was successful, reset error counter
                if poll_result is not None:
                    consecutive_errors = 0

                # Small delay to prevent CPU hogging
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(e, "Error in web server loop")
                consecutive_errors += 1
                
                # If we have too many consecutive errors, try restarting the server
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(None, f"Too many consecutive errors ({consecutive_errors}), restarting web server")
                    try:
                        web_server.stop()
                        
                        # Only attempt restart if cooldown period has passed
                        current_time = time.monotonic()
                        if current_time - last_restart_time > restart_cooldown:
                            last_restart_time = current_time
                            # Try to create a new web server
                            new_server = self.start_web_server(self.socket_pool)
                            if new_server and new_server.is_running:
                                web_server = new_server
                                logger.info("Successfully created new web server after consecutive errors")
                                consecutive_errors = 0
                    except Exception as restart_error:
                        logger.error(restart_error, "Failed to restart web server after consecutive errors")
                
                # Delay to prevent rapid error loops - longer delay with more errors
                await asyncio.sleep(min(1 + consecutive_errors * 0.5, 5))

    async def run(self):
        """Run the main application loop with concurrent tasks"""
        await self.initialize_all()

        # Start web server (will use appropriate implementation based on mode)
        web_server = None
        try:
            web_server = self.start_web_server(self.socket_pool)
            if web_server:
                logger.info(f"Web server started successfully: {type(web_server).__name__}")
            else:
                logger.warning("Web server failed to start")
        except Exception as e:
            logger.error(e, "Error starting web server")

        if web_server:
            # Run display and web server concurrently
            if is_dev_mode():
                # In dev mode, web server runs in its own thread, so we only need the display loop
                logger.info("Development mode: Running display loop with threaded web server")
                await self.run_display_loop()
            else:
                # In hardware mode, run both loops concurrently
                logger.info("Hardware mode: Starting display and web server concurrently")
                await asyncio.gather(
                    self.run_display_loop(),
                    self.run_web_server_loop(web_server)
                )
        else:
            # Just run the display loop if no web server
            logger.info("Running display loop only (no web server)")
            await self.run_display_loop()

    @staticmethod
    def is_wifi_password_configured() -> bool:
        # Always return True in dev mode to skip configuration
        if is_dev_mode():
            return True
            
        ssid, password = load_credentials()
        # logger.debug(f"SSID: {ssid} Password: {password}")
        is_configured = ssid != "" and password != ""
        return is_configured