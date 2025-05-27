"""
WiFi connection management.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import sys
import os

# Check if running on CircuitPython
is_circuitpython = hasattr(sys, 'implementation') and sys.implementation.name == 'circuitpython'

# Only import platform if not running on CircuitPython
if not is_circuitpython:
    import platform

from src.config.settings_manager import SettingsManager
from src.utils.error_handler import ErrorHandler
from src.utils.url_utils import load_credentials
from src.ui.display_factory import is_dev_mode

# Initialize logger
logger = ErrorHandler("error_log")

class WiFiManager:
    """
    Manages WiFi connections for the application
    """
    
    def __init__(self, settings_manager):
        """
        Initialize the WiFi manager
        
        Args:
            settings_manager: The settings manager
        """
        self.settings_manager = settings_manager
        self.ssid, self.password = load_credentials()
        self.is_connected = False
        self.wifi_client = None
        self.ap_enabled = False
        self.web_server = None

        # Development mode values
        self.AP_SSID = "WifiManager_DEV"
        self.AP_PASSWORD = "password"

        try:
            # Check if in development mode
            if is_dev_mode():
                # In dev mode, simulate WiFi capabilities
                logger.info("Running in development mode, using simulated WiFi")
                self.wifi = None
                self.HAS_WIFI = False
                # Set dummy values for development
                self.AP_SSID = "WifiManager_DEV"
                self.AP_PASSWORD = "password"
                return
                
            # Try to import CircuitPython specific modules
            import wifi
            self.wifi = wifi
            self.HAS_WIFI = True
            # extract access point mac address
            mac_ap = ' '.join([hex(i) for i in self.wifi.radio.mac_address_ap])
            mac_ap = mac_ap.replace('0x', '').replace(' ', '').upper()
            # access point settings
            self.AP_SSID = "WifiManager_" + mac_ap[5:10] + mac_ap[1:2]
            self.AP_PASSWORD = "password"
            self.AP_AUTHMODES = [self.wifi.AuthMode.WPA2, self.wifi.AuthMode.PSK]
            
        except ImportError:
            # Mock for non-CircuitPython environments
            self.wifi = None
            self.HAS_WIFI = False
            logger.debug("WiFi module not available, using mock implementation")

    async def reset(self):
        """Reset the microcontroller after delay"""
        await asyncio.sleep(4)
        if not is_dev_mode():
            try:
                import microcontroller
                microcontroller.reset()
            except ImportError:
                logger.debug("Microcontroller module not available, skipping reset")
                # In non-hardware environments, just simulate a reset
                os._exit(0)

    async def connect(self, display_callback=None):
        """
        Connect to WiFi
        
        Args:
            display_callback: Optional callback function to update display during connection attempts
            
        Returns:
            True if connected, False otherwise
        """
        if is_dev_mode() or not self.HAS_WIFI:
            logger.debug("WiFi not available or in dev mode, simulating connection")
            self.is_connected = True
            return True
            
        try:
            if not self.ssid or not self.password:
                logger.error(ValueError("Missing WiFi credentials"), "WiFi credentials not found")
                return False
                
            logger.info(f"Connecting to WiFi network: {self.ssid}")
            
            # Maximum connection attempts
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Connect to the network
                    self.wifi.radio.connect(self.ssid, self.password)
                    self.is_connected = True
                    break
                except Exception as conn_err:
                    # Only log on final attempt, otherwise just try again
                    if attempt == max_attempts - 1:
                        logger.error(conn_err, f"Failed to connect to WiFi after {max_attempts} attempts")
                    
                    # Update display if callback provided
                    if display_callback:
                        await display_callback(f"Attempt {attempt+1}/{max_attempts}")
                    
                    # Short delay before retry
                    await asyncio.sleep(1)
            
            if self.is_connected:
                # Log connection info
                ip_address = self.wifi.radio.ipv4_address
                logger.info(f"Connected to WiFi. IP address: {ip_address}")
                
                # Now that we're connected, create the HTTP session
                # This should only happen AFTER a successful WiFi connection
                try:
                    session = self.create_http_session()
                    logger.info("Created HTTP session after WiFi connection")
                except Exception as session_error:
                    logger.error(session_error, "Failed to create HTTP session after WiFi connection")
                
                return True
            else:
                return False
            
        except Exception as e:
            logger.error(e, "Error connecting to WiFi")
            self.is_connected = False
            return False
            
    def create_http_session(self):
        """
        Create and return a new HTTP session
        This should only be called after WiFi is connected
        
        Returns:
            A new adafruit_requests.Session or None if not available
        """
        if is_dev_mode() or not self.HAS_WIFI or not self.is_connected:
            logger.debug("Cannot create HTTP session without WiFi connection or in dev mode")
            return None
            
        try:
            import ssl
            import socketpool
            import adafruit_requests
            
            # Create a fresh socket pool from the radio
            pool = socketpool.SocketPool(self.wifi.radio)
            
            # Create a new SSL context
            ssl_context = ssl.create_default_context()
            
            # Create and return the session
            session = adafruit_requests.Session(pool, ssl_context)
            
            # Update any HTTP clients that need the session
            self.update_http_clients(session)
            
            return session
            
        except Exception as e:
            logger.error(e, "Error creating HTTP session")
            return None
            
    def update_http_clients(self, session):
        """
        Update any HTTP clients with the new session
        Mainly used by ThemeParkApp to update its HTTP client
        
        Args:
            session: The new adafruit_requests.Session
        """
        # This function will be called from the app to update HTTP clients
        # The implementation is in the app class
            
    async def disconnect(self):
        """Disconnect from WiFi"""
        if is_dev_mode() or not self.HAS_WIFI or not self.is_connected:
            return
            
        try:
            logger.info("Disconnecting from WiFi")
            # Some CircuitPython versions may not have the disconnect method
            if hasattr(self.wifi.radio, 'disconnect'):
                self.wifi.radio.disconnect()
            self.is_connected = False
            
        except Exception as e:
            logger.error(e, "Error disconnecting from WiFi")
            
    async def reconnect(self):
        """
        Reconnect to WiFi if disconnected
        
        Returns:
            True if connected, False otherwise
        """
        if self.is_connected:
            return True
            
        # Try to reconnect
        return await self.connect()
        
    def is_available(self):
        """
        Check if WiFi is available
        
        Returns:
            True if WiFi is available, False otherwise
        """
        return self.HAS_WIFI or is_dev_mode()
        
    def is_connected(self):
        """
        Check if connected to WiFi
        
        Returns:
            True if connected, False otherwise
        """
        if is_dev_mode():
            # In dev mode, always report as connected
            return True
            
        if not self.HAS_WIFI:
            return self.is_connected
            
        try:
            return self.wifi.radio.connected
        except Exception:
            return False
            
    def get_ip_address(self):
        """
        Get the current IP address
        
        Returns:
            The IP address as a string, or None if not connected
        """
        if is_dev_mode():
            # In dev mode, return a dummy IP
            return "127.0.0.1"
            
        if not self.HAS_WIFI or not self.is_connected:
            return None
            
        try:
            return str(self.wifi.radio.ipv4_address)
        except Exception:
            return None
            
    def save_credentials(self):
        """
        Save WiFi credentials to settings manager
        """
        if hasattr(self, 'settings_manager') and self.settings_manager:
            try:
                # Save SSID and password to settings
                self.settings_manager.settings["wifi_ssid"] = self.ssid
                self.settings_manager.settings["wifi_password"] = self.password
                
                # Save settings to disk
                self.settings_manager.save_settings()
                logger.info(f"Saved WiFi credentials to settings manager")
                
                # Also try to save to a secrets.py file for CircuitPython
                if not is_dev_mode():
                    try:
                        self._save_to_secrets_file()
                    except Exception as secrets_err:
                        logger.error(secrets_err, "Could not save to secrets.py file")
                    
            except Exception as e:
                logger.error(e, "Failed to save WiFi credentials to settings manager")
                
    def _save_to_secrets_file(self):
        """
        Save WiFi credentials to secrets.py file
        """
        if is_dev_mode():
            logger.debug("Skipping secrets.py file update in dev mode")
            return
            
        try:
            # Read existing secrets file if it exists
            secrets_content = ""
            try:
                with open("/secrets.py", "r") as f:
                    secrets_content = f.read()
            except OSError:
                # Create a new secrets file with default structure
                secrets_content = """# This file is automatically generated - do not edit manually
secrets = {
    # WiFi credentials
    'ssid': '',
    'password': '',
}
"""

            # Update the SSID and password values
            import re
            
            # Pattern to match the SSID line
            ssid_pattern = r"('ssid'|\"ssid\")\s*:\s*('.*'|\".*\")"
            if re.search(ssid_pattern, secrets_content):
                # Replace existing SSID
                secrets_content = re.sub(ssid_pattern, f"'ssid': '{self.ssid}'", secrets_content)
            else:
                # Add SSID if not found
                secrets_content = secrets_content.replace("secrets = {", "secrets = {\n    'ssid': '" + self.ssid + "',")
                
            # Pattern to match password line
            password_pattern = r"('password'|\"password\")\s*:\s*('.*'|\".*\")"
            if re.search(password_pattern, secrets_content):
                # Replace existing password
                secrets_content = re.sub(password_pattern, f"'password': '{self.password}'", secrets_content)
            else:
                # Add password if not found
                secrets_content = secrets_content.replace("secrets = {", "secrets = {\n    'password': '" + self.password + "',")
            
            # Write the updated contents back to the file
            with open("/secrets.py", "w") as f:
                f.write(secrets_content)
                
            logger.info("Updated secrets.py file with new WiFi credentials")
            
        except Exception as e:
            logger.error(e, "Failed to save WiFi credentials to secrets.py file")

    def start_access_point(self,port=80):
        """Start the WiFi access point"""
        if is_dev_mode() or not self.HAS_WIFI:
            logger.debug("Cannot start access point in dev mode or without WiFi hardware")
            self.ap_enabled = True
            return
            
        self.wifi.radio.enabled = True
        if self.ap_enabled is False:
            # to use encrypted AP, use authmode=[wifi.AuthMode.WPA2, wifi.AuthMode.PSK]
            if (self.AP_AUTHMODES[0] == self.wifi.AuthMode.OPEN):
                self.wifi.radio.start_ap(ssid=self.AP_SSID, authmode=self.AP_AUTHMODES)
            else:
                self.wifi.radio.start_ap(ssid=self.AP_SSID, password=self.AP_PASSWORD, authmode=self.AP_AUTHMODES)
            self.ap_enabled = True

    def stop_access_point(self):
        """Stop the WiFi access point"""
        if is_dev_mode() or not self.HAS_WIFI:
            logger.debug("Cannot stop access point in dev mode or without WiFi hardware")
            self.ap_enabled = False
            return
            
        self.wifi.radio.stop_ap()
        self.ap_enabled = False
        
    def scan_networks(self):
        """
        Scan for available WiFi networks
        
        Returns:
            List of network info (SSID, RSSI, channel, security)
        """
        if is_dev_mode() or not self.HAS_WIFI:
            logger.debug("WiFi not available or in dev mode, returning mock networks")
            # Return mock data for testing
            return [
                {"ssid": "HomeNetwork", "rssi": -65, "channel": 6},
                {"ssid": "GuestWiFi", "rssi": -70, "channel": 11}
            ]
            
        try:
            logger.debug("Scanning for WiFi networks...")
            networks = []
            
            # Scan for networks
            for network in self.wifi.radio.start_scanning_networks():
                # Skip hidden networks
                if not network.ssid:
                    continue
                    
                net_info = {
                    "ssid": network.ssid,
                    "rssi": network.rssi,
                    "channel": network.channel
                }
                networks.append(net_info)
                
            # Sort networks by signal strength (strongest first)
            networks.sort(key=lambda x: x["rssi"], reverse=True)
            
            self.wifi.radio.stop_scanning_networks()
            logger.debug(f"Found {len(networks)} WiFi networks")
            return networks
            
        except Exception as e:
            logger.error(e, "Error scanning for WiFi networks")
            # Return empty list on error
            return []
            
    def generate_wifi_setup_page(self):
        """
        Generate a WiFi setup page with available networks
        
        Returns:
            HTML content as string
        """
        # Scan for networks
        networks = self.scan_networks()
        
        # Create a clean modern HTML page
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>WiFi Setup</title>
            <link rel="stylesheet" href="/wifi_style.css">
            <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        </head>
        <body>
            <h1>WiFi Setup</h1>
            <form action="configure" method="post">
        """
        
        # Add networks as dropdown menu
        html += """
        <div class="select-container">
            <label for="ssid-select">Select your WiFi network:</label>
            <select id="ssid-select" name="ssid" class="network-select">
        """

        if networks:
            # Add default option
            html += '<option value="" disabled selected>Choose a network...</option>'

            # Add each network to the dropdown
            for network in networks:
                ssid = network["ssid"]
                rssi = network["rssi"]
                # Convert RSSI to signal bars (1-4)
                bars = min(4, max(1, int((network["rssi"] + 100) / 15)))

                html += f'<option value="{ssid}">{ssid} ({bars} bars, {rssi} dBm)</option>'

            html += """
            </select>
        </div>
        """
        else:
            html += """
            </select>
            <p>No networks found. Please scan again.</p>
        </div>
        """
        
        # Password field
        html += """
                <div class="password-container">
                    <label for="password">Password:</label>
                    <input class="text" id="password" name="password" type="password" placeholder="WiFi Password">
                </div>
                
                <div class="button-container">
                    <button type="submit">Connect</button>
                </div>
            </form>
        </body>
        </html>
        """
        
        return html

    def start_web_server(self):
        """Start the web server for WiFi configuration"""
        if is_dev_mode() or not self.HAS_WIFI:
            logger.debug("Skipping web server in dev mode or without WiFi hardware")
            return
            
        logger.debug("starting web server..")
        import socketpool
        import wifi
        import adafruit_httpserver
        
        pool = socketpool.SocketPool(wifi.radio)
        self.web_server = adafruit_httpserver.Server(pool, "/www", debug=False)
        
        # Register routes for WiFi setup
        self.register_routes()
        
        # Start the server
        self.web_server.start(str(wifi.radio.ipv4_address_ap), 80)
        logger.debug("Listening on http://%s:80" % str(wifi.radio.ipv4_address_ap))

    async def run_web_server(self, termination_func):
        """
        Run the web server in a loop until termination function returns True
        
        Args:
            termination_func: A function that returns True when the server should stop
        """
        if is_dev_mode() or not self.HAS_WIFI:
            logger.debug("Skipping web server loop in dev mode or without WiFi hardware")
            # In dev mode, simulate the termination function return after a few seconds
            await asyncio.sleep(5)
            return
            
        # Don't call termination_func here, just log the function reference
        logger.debug(f"Starting web server loop with termination function")
        
        if not hasattr(self, 'web_server') or self.web_server is None:
            logger.error("Web server not initialized")
            return
            
        # If you want you can stop the server by calling server.stop() anywhere in your code
        while not termination_func() and not self.web_server.stopped:
            try:
                # Process any waiting HTTP requests
                self.web_server.poll()
                await asyncio.sleep(1)
            except OSError as error:
                logger.error(f"Web server loop stopped with error: {str(error)}")
                # traceback.print_exc()
                continue
        logger.debug(f"Exiting wifimgr:run_web_server()")


    def register_routes(self):
        """Register HTTP routes for WiFi setup"""
        if is_dev_mode() or not self.HAS_WIFI:
            logger.debug("Skipping route registration in dev mode or without WiFi hardware")
            return
            
        from adafruit_httpserver import (
            Status,
            REQUEST_HANDLED_RESPONSE_SENT,
            Request,
            Response,
            Headers,
            GET,
            POST,
            Server
        )

        @self.web_server.route("/", [GET])
        def root(request: Request):
            """Handle root endpoint - show WiFi setup page with networks list"""
            try:
                # Check if scan requested
                query_params = str(request.query_params) if request.query_params else ""
                if "scan=true" in query_params:
                    logger.debug("Network scan requested")
                    # Force a fresh scan before generating the page
                    self.wifi.radio.stop_scanning_networks()

                # Generate a dynamic page with available networks
                html_content = self.generate_wifi_setup_page()
                logger.debug("Serving dynamic WiFi setup page")
                return Response(request, html_content, content_type="text/html")
            except OSError as e:
                logger.error(e, "Error serving WiFi setup page")
                error_html = "<html><body><h1>Error loading WiFi setup page</h1></body></html>"
                return Response(request, error_html, content_type="text/html")

        @self.web_server.route("/wifi_style.css", [GET])
        def wifi_style(request: Request):
            """Serve WiFi CSS styles"""
            try:
                # Try different possible locations for the CSS file
                css_paths = [
                    "/src/www/wifi_style.css",  # Primary location
                    "/www/wifi_style.css",      # Alternate location
                    "/wifi_style.css"           # Root location
                ]
                
                content = None
                for path in css_paths:
                    try:
                        with open(path, "r") as f:
                            content = f.read()
                            logger.debug(f"Successfully served wifi_style.css from {path}")
                            break
                    except OSError:
                        continue
                
                if content:
                    return Response(request, content, content_type="text/css")
                else:
                    raise OSError("Could not find wifi_style.css in any location")
                    
            except OSError as e:
                logger.error(e, "Error serving wifi_style.css")
                # Provide a minimal fallback CSS if file can't be found
                fallback_css = """
                body {
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: #faa538;
                    color: white;
                }
                h1 { text-align: center; padding: 20px 0; }
                .select-container { margin: 20px 0; width: 100%; }
                .network-select { width: 100%; padding: 12px; border: 2px solid white; border-radius: 30px;
                    background: transparent; color: white; margin-top: 8px; cursor: pointer;
                    appearance: none; -webkit-appearance: none; -moz-appearance: none;
                    background-image: url("data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22292.4%22%20height%3D%22292.4%22%3E%3Cpath%20fill%3D%22%23FFFFFF%22%20d%3D%22M287%2069.4a17.6%2017.6%200%200%200-13-5.4H18.4c-5%200-9.3%201.8-12.9%205.4A17.6%2017.6%200%200%200%200%2082.2c0%205%201.8%209.3%205.4%2012.9l128%20127.9c3.6%203.6%207.8%205.4%2012.8%205.4s9.2-1.8%2012.8-5.4L287%2095c3.5-3.5%205.4-7.8%205.4-12.8%200-5-1.9-9.2-5.5-12.8z%22%2F%3E%3C%2Fsvg%3E");
                    background-repeat: no-repeat; background-position: right 12px center; background-size: 12px;
                    padding-right: 30px; box-sizing: border-box;
                }
                .network-select option { background-color: #faa538; color: white; }
                input.text { width: 100%; padding: 12px; border-radius: 30px; margin: 10px 0; border: 2px solid white; background: transparent; color: white; }
                button { background: white; color: #faa538; border: none; padding: 12px 30px; border-radius: 30px; margin-top: 20px; font-weight: bold; }
                .scan-button { background: #4285f4; color: white; padding: 12px; border-radius: 30px; text-decoration: none; display: inline-block; }
                .button-container { display: flex; justify-content: space-between; margin-top: 20px; }
                form { padding: 0 20px; }
                """
                return Response(request, fallback_css, content_type="text/css")

        @self.web_server.route("/configure", [POST])
        def configure(request: Request):
            """Handle WiFi configuration form submission"""
            try:
                # Get form data from request
                content_length = int(request.headers.get("Content-Length", 0))
                
                # Fix for the 'bytes' object has no attribute 'read' error
                # In CircuitPython/Adafruit's HTTP server, request.body is already the bytes,
                # not a file-like object with a read method
                if isinstance(request.body, bytes):
                    form_data = request.body.decode("utf-8")
                else:
                    form_data = request.body.read(content_length).decode("utf-8")
                
                logger.debug(f"Received form data: {form_data}")

                # Parse form data to get SSID and password
                ssid = None
                password = None

                # Simple parsing of form data
                params = form_data.split("&")
                for param in params:
                    if "=" in param:
                        key, value = param.split("=", 1)
                        if key == "ssid":
                            ssid = value
                        elif key == "password":
                            password = value

                if ssid and password:
                    # Update credentials
                    self.ssid = ssid.replace("+", " ")  # Replace + with space in form-encoded data
                    self.password = password
                    # Save credentials to settings manager
                    self.save_credentials()
                    logger.info(f"Updated WiFi credentials, SSID: {self.ssid}")

                    # Try to connect
                    response_html = f"""
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <title>WiFi Configuration</title>
                        <meta http-equiv="refresh" content="10;url=/" />
                        <link rel="stylesheet" href="/wifi_style.css">
                        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
                        <style>
                            .connection-box {{
                                background: rgba(255, 255, 255, 0.1);
                                border-radius: 12px;
                                padding: 20px;
                                margin: 20px;
                            }}
                            h2 {{
                                margin-top: 0;
                            }}
                        </style>
                    </head>
                    <body>
                        <h1>WiFi Configuration</h1>
                        <div class="connection-box">
                            <h2>Connecting to WiFi</h2>
                            <p>Network: <strong>{self.ssid}</strong></p>
                            <p>The device will attempt to connect to the network.</p>
                            <p>If successful, you will need to connect to your regular WiFi network to access the device.</p>
                            <p>If connection fails, the access point will remain active and you can try again.</p>
                        </div>
                    </body>
                    </html>
                    """

                    # Create a task to connect to the new network (after sending response)
                    # This won't block the response
                    # TODO: Come up with better solution
                    #asyncio.create_task(self.connect())
                    asyncio.create_task(self.reset())

                    return Response(request, response_html, content_type="text/html")
                else:
                    error_html = """
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <title>Error</title>
                        <meta http-equiv="refresh" content="5;url=/" />
                        <link rel="stylesheet" href="/wifi_style.css">
                        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
                        <style>
                            .error-box {
                                background: rgba(255, 0, 0, 0.2);
                                border-radius: 12px;
                                padding: 20px;
                                margin: 20px;
                            }
                        </style>
                    </head>
                    <body>
                        <h1>Configuration Error</h1>
                        <div class="error-box">
                            <p>Missing SSID or password.</p>
                            <p>Returning to setup page in 5 seconds...</p>
                        </div>
                    </body>
                    </html>
                    """
                    return Response(request, error_html, content_type="text/html")

            except Exception as e:
                logger.error(e, "Error processing WiFi configuration")
                error_html = """
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <title>Error</title>
                    <meta http-equiv="refresh" content="5;url=/" />
                    <link rel="stylesheet" href="/wifi_style.css">
                    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
                    <style>
                        .error-box {
                            background: rgba(255, 0, 0, 0.2);
                            border-radius: 12px;
                            padding: 20px;
                            margin: 20px;
                        }
                    </style>
                </head>
                <body>
                    <h1>Configuration Error</h1>
                    <div class="error-box">
                        <p>An error occurred while processing your request.</p>
                        <p>Returning to setup page in 5 seconds...</p>
                    </div>
                </body>
                </html>
                """
                return Response(request, error_html, content_type="text/html")