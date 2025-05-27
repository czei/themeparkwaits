"""
Web server implementation for the ThemeParkAPI.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import time
import re

from adafruit_datetime import datetime
from adafruit_httpserver import Server
from adafruit_httpserver import Request
from adafruit_httpserver import Response
from adafruit_httpserver import Headers
from adafruit_httpserver import Status
from adafruit_httpserver.methods import GET, POST

from src.models.vacation import Vacation
from src.utils.color_utils import ColorUtils
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")

class ThemeParkWebServer:
    """Web server implementation for ThemeParkAPI"""

    def __init__(self, socket_pool, app_instance):
        """
        Initialize the web server
        
        Args:
            socket_pool: The socket pool to use
            app_instance: The ThemeParkApp instance to interact with
        """
        self.app = app_instance
        # Use a more secure root path instead of "/" to prevent exposing sensitive files
        self.server = Server(socket_pool, "/www", debug=True)
        self.is_running = False
        self.last_settings_save = 0  # Track when settings were last saved

        # Register routes
        self.register_routes()

    def register_routes(self):
        """Register HTTP routes with the server"""

        @self.server.route("/", [GET])
        def base(request: Request):
            """Handle root endpoint"""
            query_params = str(request.query_params) if request.query_params else None

            if query_params:
                # Process parameters and update settings synchronously
                try:
                    # Process parameters directly with a non-async approach
                    self._process_query_params(query_params)
                    logger.info(f"Processed main page form params: {query_params}")
                except Exception as e:
                    logger.error(e, f"Error processing query params: {query_params}")

                # Generate response page with updated settings
                # No redirect - return the updated page directly
                page = self.generate_main_page()
                return Response(request, page, content_type="text/html")

            # Generate main page (no query params)
            page = self.generate_main_page()
            return Response(request, page, content_type="text/html")

        @self.server.route("/style.css", [GET])
        def style(request: Request):
            """Serve CSS styles"""
            try:
                # First try to read from www directory (preferred location)
                try:
                    with open("/www/style.css", "r") as f:
                        content = f.read()
                    logger.debug("Successfully served style.css from /www")
                    return Response(request, content, content_type="text/css")
                except OSError:
                    # Fallback to src directory for backward compatibility
                    with open("/src/style.css", "r") as f:
                        content = f.read()
                    logger.debug("Successfully served style.css from /src")
                    return Response(request, content, content_type="text/css")
            except OSError as e:
                logger.error(e, "Error serving style.css from all locations")
                # Create a minimal fallback CSS if the file can't be read
                fallback_css = """
                body { font-family: Arial, sans-serif; margin: 0; padding: 0; }
                .navbar { background-color: #faa538; color: white; padding: 1rem; display: flex; justify-content: space-between; }
                .navbar a { color: white; text-decoration: none; }
                .main-content { padding: 1rem; }
                button { background-color: #faa538; border: none; padding: 8px 16px; color: white; cursor: pointer; }
                input, select { margin: 5px 0; padding: 5px; }
                .form-group { margin-bottom: 1rem; }
                """
                return Response(request, fallback_css, content_type="text/css")

        @self.server.route("/settings", [GET])
        def settings(request: Request):
            """Handle settings endpoint"""
            query_params = str(request.query_params) if request.query_params else None

            if query_params:
                # Process settings form submission
                try:
                    self._process_query_params(query_params)
                    logger.info(f"Processed settings form params: {query_params}")
                except Exception as e:
                    logger.error(e, f"Error processing settings query params: {query_params}")

            # Generate settings page
            # Generate settings page with success message if query params were processed
            if query_params:
                page = self.generate_settings_page(success=True)
            else:
                page = self.generate_settings_page()
            return Response(request, page, content_type="text/html")

    def start(self, ip_address):
        """
        Start the web server
        
        Args:
            ip_address: The IP address to bind to
        """
        try:
            # Make sure to convert IP to string and specify port 80
            logger.debug(f"Starting server on {ip_address}:80")

            # Try to stop any existing server first
            try:
                self.server.stop()
            except:
                pass

            # Start the server with "0.0.0.0" to listen on all interfaces
            # This is important for ensuring the server responds to all incoming connections
            self.server.start("0.0.0.0", 80)

            # Verify server started
            logger.info(f"Web server started on all interfaces, access at http://{ip_address}")
            self.is_running = True

        except Exception as e:
            logger.error(e, f"Failed to start web server on {ip_address}:80")
            self.is_running = False

    def stop(self):
        """Stop the web server"""
        if self.is_running:
            self.server.stop()
            self.is_running = False

import urllib.parse
import re

def _process_query_params(self, query_params):
    """
    Process query parameters synchronously without using async/await

    Args:
        query_params: Query parameters from the request as a string

    Returns:
        True if a park change was detected, False otherwise
    """
    if not query_params or not self.app or not hasattr(self.app, 'theme_park_service'):
        return False

    park_changed = False

    # Handle park-id parameter (existing code)
    if "park-id=" in query_params:
        try:
            current_park_id = None
            if (hasattr(self.app.theme_park_service, 'park_list') and
                    hasattr(self.app.theme_park_service.park_list, 'current_park')):
                current_park_id = self.app.theme_park_service.park_list.current_park.id

            if hasattr(self.app.theme_park_service, 'park_list'):
                self.app.theme_park_service.park_list.parse(query_params)
                logger.debug(f"Updated park selection from query params")

                new_park_id = self.app.theme_park_service.park_list.current_park.id
                park_changed = (current_park_id != new_park_id)
                if park_changed:
                    logger.info(f"Park changed from ID {current_park_id} to {new_park_id}")
        except Exception as e:
            logger.error(e, "Error updating park selection")

    # Handle checkbox parameters (existing code)
    if hasattr(self.app.theme_park_service, 'park_list'):
        skip_closed = "skip_closed=on" in query_params
        self.app.theme_park_service.park_list.skip_closed = skip_closed
        logger.debug(f"Set skip_closed to {skip_closed}")

        skip_meet = "skip_meet=on" in query_params
        self.app.theme_park_service.park_list.skip_meet = skip_meet
        logger.debug(f"Set skip_meet to {skip_meet}")

    # Process vacation (existing code)
    vacation_updated = False
    if "Year=" in query_params and hasattr(self.app.theme_park_service, 'vacation'):
        try:
            self.app.theme_park_service.vacation.parse(query_params)
            vacation_updated = True
            logger.debug(f"Updated vacation settings from query params")
        except Exception as e:
            logger.error(e, "Error updating vacation settings")

    # Process display settings (existing code)
    brightness_changed = False
    scroll_changed = False

    if "domain_name=" in query_params:
        try:
            domain_match = re.search(r'domain_name=([^&]+)', query_params)
            if domain_match:
                domain_name = domain_match.group(1)
                self.app.settings_manager.set("domain_name", domain_name)
                logger.debug(f"Updated domain name to {domain_name}")
        except Exception as e:
            logger.error(e, "Error updating display settings")

    brightness_match = re.search(r'brightness_scale=([^&]+)', query_params)
    if brightness_match:
        brightness = brightness_match.group(1)
        self.app.settings_manager.set("brightness_scale", brightness)
        logger.debug(f"Updated brightness to {brightness}")
        brightness_changed = True

    self.app.display.set_colors(self.app.settings_manager)
    logger.debug("Applied new brightness setting to display")

    scroll_match = re.search(r'scroll_speed=([^&]+)', query_params)
    if scroll_match:
        scroll_speed = scroll_match.group(1)
        self.app.settings_manager.set("scroll_speed", scroll_speed)
        logger.debug(f"Updated scroll speed to {scroll_speed}")

    # --- NEW: process color parameters ---
    color_params = ["default_color", "ride_name_color", "ride_wait_time_color"]
    for color_param in color_params:
        if f"{color_param}=" in query_params:
            try:
                # Use plain f-string without raw
                pattern = f'{color_param}=([^&]+)'
                match = re.search(pattern, query_params)
                if match:
                    color_value = urllib.parse.unquote(match.group(1))
                    self.app.settings_manager.set(color_param, color_value)
                    logger.debug(f"Updated {color_param} to {color_value}")
            except Exception as e:
                logger.error(e, f"Error updating {color_param}")

    # Save settings after changes
    try:
        self.app.settings_manager.save_settings()
        logger.debug("Settings saved successfully after processing query params")

        if (brightness_changed or scroll_changed) and hasattr(self.app, 'message_queue'):
            self.app.display.set_colors(self.app.settings_manager)
            logger.debug("Reset message queue after display settings change")
    except Exception as e:
        logger.error(e, "Error saving settings")

    if park_changed:
        self._trigger_park_update()

    return park_changed

    async def poll(self):
        """
        Poll the server for incoming requests with error recovery
        
        Returns:
            True if a request was handled, False/None otherwise
        """
        if not self.is_running:
            return None

        try:
            # Poll the server for requests
            result = self.server.poll()

            # Short sleep to allow other tasks to run
            await asyncio.sleep(0)

            # Only return a meaningful result for actual requests
            # The adafruit_httpserver.REQUEST_HANDLED_RESPONSE_SENT constant
            # is used to indicate a request was actually processed
            from adafruit_httpserver import REQUEST_HANDLED_RESPONSE_SENT
            if result == REQUEST_HANDLED_RESPONSE_SENT:
                return True

            return False

        except Exception as e:
            # Log the error but don't crash the server
            logger.error(e, "Error in web server poll")

            # Brief pause to avoid error loops
            await asyncio.sleep(0.1)

            # Check if server is still in a valid state
            try:
                # Access a server property to check if it's functioning
                addr = self.server.server_socket.getsockname()
                # If we get here, server socket is still valid
            except Exception:
                # Server socket appears invalid, restart server
                logger.info("Restarting web server after error")
                try:
                    self.is_running = False
                    self.server.stop()
                    await asyncio.sleep(1)  # Brief delay before restart
                    self.server.start("0.0.0.0", 80)
                    self.is_running = True
                    logger.info("Web server restarted successfully")
                except Exception as restart_error:
                    logger.error(restart_error, "Failed to restart web server")

            return False

    def generate_main_page(self):
        """
        Generate the main HTML page
        
        Returns:
            HTML content for the main page
            
        Note:
            This method uses direct access to app data to avoid asyncio conflicts
        """
        page = "<!DOCTYPE html><html><head>"
        page += "<title>Theme Park Waits</title>"
        page += "<link rel=\"stylesheet\" href=\"style.css\">"
        page += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        page += "</head>"
        page += "<body>"

        page += "<div class=\"navbar\">"
        page += "<a href=\"/\">Theme Park Wait Times</a>"
        page += "<div class=\"settings\">"
        page += "<a href=\"/settings\" class=\"settings-icon\">&#x2699;</a>"
        page += "</div></div>"

        # Main content
        page += "<div class=\"main-content\">"
        page += "<h2>Theme Park Selection</h2>"

        # Get parks from app - without using asyncio.run()
        try:
            # Create basic response data first
            response_data = {
                "parks": [],
                "settings": self.app.settings_manager.settings,  # Include settings directly
                "success": True
            }

            # Use direct data access - no event loop
            parks = []

            # Safely access theme park data directly with full error handling
            try:
                # Check theme park service exists
                if (hasattr(self.app, 'theme_park_service') and
                        self.app.theme_park_service and
                        hasattr(self.app.theme_park_service, 'park_list') and
                        self.app.theme_park_service.park_list):

                    # Get parks list
                    if hasattr(self.app.theme_park_service.park_list, 'park_list'):
                        for park in self.app.theme_park_service.park_list.park_list:
                            if hasattr(park, 'id') and hasattr(park, 'name'):
                                parks.append({"id": park.id, "name": park.name})

                    # Get current park
                    if (hasattr(self.app.theme_park_service.park_list, 'current_park') and
                            self.app.theme_park_service.park_list.current_park and
                            hasattr(self.app.theme_park_service.park_list.current_park, 'is_valid')):

                        try:
                            if self.app.theme_park_service.park_list.current_park.is_valid():
                                current_park = self.app.theme_park_service.park_list.current_park
                                ride_count = 0
                                if hasattr(current_park, 'rides'):
                                    ride_count = len(current_park.rides)

                                response_data["current_park"] = {
                                    "id": current_park.id,
                                    "name": current_park.name,
                                    "ride_count": ride_count
                                }
                        except Exception as park_error:
                            logger.error(park_error, "Error getting current park data")

                # Update response data with parks
                response_data["parks"] = parks
                logger.debug(f"Using direct access for parks data - found {len(parks)} parks")

            except Exception as data_error:
                logger.error(data_error, "Error accessing theme park data")
                # Keep empty parks list
                response_data["parks"] = []

        except Exception as e:
            logger.error(e, "Error getting app data for main page")
            # Ensure response data exists with settings
            response_data = {"parks": [], "settings": {}, "success": False}

            # Try to get settings directly if available
            if hasattr(self.app, 'settings_manager') and hasattr(self.app.settings_manager, 'settings'):
                response_data["settings"] = self.app.settings_manager.settings

        if "parks" in response_data:
            page += "<form action=\"/\" method=\"get\">"
            page += "<select name=\"park-id\" id=\"park-select\">"

            # Check if we have parks and provide a message if empty
            parks = response_data.get("parks", [])
            if not parks:
                page += "<option value=\"\">No parks available - check connection</option>"
                logger.error(None, "No parks available for dropdown - empty park list")
            else:
                logger.debug(f"Generating dropdown with {len(parks)} parks")

                current_park_id = None
                if "current_park" in response_data:
                    current_park_id = response_data["current_park"]["id"]

                for park in parks:
                    selected = "selected" if park["id"] == current_park_id else ""
                    park_name = park.get("name", "Unknown Park")
                    park_id = park.get("id", "")
                    page += f"<option value=\"{park_id}\" {selected}>{park_name}</option>"

            page += "</select>"
            # Safe access to settings
            settings = response_data.get("settings", {})
            if not isinstance(settings, dict):
                settings = {}

            # Create options div with better formatting
            page += "<div class=\"options\">"
            page += "<h3 style=\"margin-top: 0; margin-bottom: 10px; text-align: left; padding-left: 20px;\">Display Options</h3>"

            # Skip Closed Rides option - Fixed alignment with label
            page += "<div class=\"form-group checkbox-group\">"

            # Get skip_closed value with safe fallback
            skip_closed = False
            try:
                skip_closed = bool(settings.get("skip_closed", False))
            except (TypeError, ValueError):
                skip_closed = False

            checked = "checked" if skip_closed else ""
            # Keep checkbox and label together in a tight layout
            page += f"<input type=\"checkbox\" id=\"skip_closed\" name=\"skip_closed\" {checked}>"
            page += "<label for=\"skip_closed\">Skip Closed Rides</label>"
            page += "</div>"

            # Skip Meet & Greets option - Fixed alignment with label
            page += "<div class=\"form-group checkbox-group\">"

            # Get skip_meet value with safe fallback
            skip_meet = False
            try:
                skip_meet = bool(settings.get("skip_meet", False))
            except (TypeError, ValueError):
                skip_meet = False

            checked = "checked" if skip_meet else ""
            # Keep checkbox and label together in a tight layout
            page += f"<input type=\"checkbox\" id=\"skip_meet\" name=\"skip_meet\" {checked}>"
            page += "<label for=\"skip_meet\">Skip Meet & Greets</label>"
            page += "</div>"

            page += "</div>"

        else:
            page += "<p>No theme parks available.</p>"


        vacation_date = Vacation()
        vacation_date.load_settings(self.app.settings_manager)
        page += "<h2>Configure Countdown</h2>"
        page += "<div class=\"countdown-section\">"
        page += "<p>"
        page += "<label for=\"Name\">Event:</label>"
        page += f"<input type=\"text\" name=\"Name\" value=\"{vacation_date.name}\">"
        page += "</p>"

        page += "<p>"
        page += "<label for=\"Date\">Date:</label>"
        page += "<div class=\"date-selectors\">"
        
        # Year dropdown
        page += "<select id=\"Year\" name=\"Year\">"
        year_now = datetime.now().year
        for year in range(year_now, 2044):
            if vacation_date.is_set() is True and year == vacation_date.year:
                page += f"<option value=\"{year}\" selected>{year}</option>\n"
            else:
                page += f"<option value=\"{year}\">{year}</option>\n"
        page += "</select>"

        # Month dropdown with names
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        page += "<select id=\"Month\" name=\"Month\">"
        for month in range(1, 13):
            if vacation_date.is_set() is True and month == vacation_date.month:
                page += f"<option value=\"{month}\" selected>{month_names[month-1]}</option>\n"
            else:
                page += f"<option value=\"{month}\">{month_names[month-1]}</option>\n"
        page += "</select>"

        # Day dropdown
        page += "<select id=\"Day\" name=\"Day\">"
        for day in range(1, 32):
            if vacation_date.is_set() is True and day == vacation_date.day:
                page += f"<option value=\"{day}\" selected>{day}</option>\n"
            else:
                page += f"<option value=\"{day}\">{day}</option>\n"
        page += "</select>"
        page += "</div>" # end date-selectors
        page += "</p>"

        # If vacation is set, show countdown
        if vacation_date.is_set():
            days_until = vacation_date.get_days_until()
            if days_until > 0:
                page += f"<p style=\"text-align: center; font-weight: bold; margin-top: 10px;\">"
                page += f"Days until {vacation_date.name}: {days_until}"
                page += "</p>"
        
        page += "</div>" # end countdown-section

        page += "<button type=\"submit\">Update</button>"
        page += "</form>"

        page += "</div></body></html>"
        return page

    def generate_settings_page(self, success=False):
        """
        Generate the settings HTML page

        Args:
            success: Whether to show a success message

        Returns:
            HTML content for the settings page
        """
        # Get current settings - without using asyncio.run()
        response_data = {"settings": {}}

        try:
            # Always use direct access for settings - no event loop needed
            # This is more reliable in CircuitPython environment
            if hasattr(self.app, 'settings_manager') and hasattr(self.app.settings_manager, 'settings'):
                response_data = {"settings": self.app.settings_manager.settings}
                logger.debug("Using direct settings access - skipping event loop")
            else:
                logger.error(None, "Settings manager not available")
                response_data = {"settings": {}}
        except Exception as e:
            # Fallback if any error occurs
            logger.error(e, "Error getting settings data")
            response_data = {"settings": {}}

        settings = response_data.get("settings", {})

        page = "<!DOCTYPE html><html><head>"
        page += "<title>Settings - Theme Park Waits</title>"
        page += "<link rel=\"stylesheet\" href=\"style.css\">"
        page += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        page += "</head>"
        page += "<body>"

        page += "<div class=\"navbar\">"
        page += "<a href=\"/\">Theme Park Wait Times</a>"
        page += "</div>"

        page += "<div class=\"main-content\">"
        page += "<h2>Settings</h2>"

        # Show success message if settings were saved
        if success:
            page += "<div class=\"success-message\" style=\"background-color: #4CAF50; color: white; padding: 10px; margin-bottom: 15px; border-radius: 4px;\">"
            page += "Settings saved successfully!"
            page += "</div>"

        page += "<form action=\"/settings\" method=\"get\">"

        # Display settings
        page += "<div class=\"settings-section\">"
        page += "<h3>Display Settings</h3>"

        # Hostname/domain name
        page += "<div class=\"form-group\">"
        page += "<label for=\"domain_name\">Hostname (.local):</label>"
        domain_name = settings.get("domain_name", "themeparkwaits")
        page += f"<input type=\"text\" id=\"domain_name\" name=\"domain_name\" value=\"{domain_name}\">"
        page += "<small>Changes require a device restart</small>"
        page += "</div>"

        # Brightness
        page += "<div class=\"form-group\">"
        page += "<label for=\"brightness_scale\">Brightness:</label>"
        brightness = settings.get("brightness_scale", "0.5")
        page += f"<input type=\"range\" id=\"brightness_scale\" name=\"brightness_scale\" min=\"0.3\" max=\"1.0\" step=\"0.1\" value=\"{brightness}\">"
        page += "</div>"

        # Scroll speed
        page += "<div class=\"form-group\">"
        page += "<label for=\"scroll_speed\">Scroll Speed:</label>"
        scroll_speed = settings.get("scroll_speed", "Medium")
        page += "<select id=\"scroll_speed\" name=\"scroll_speed\">"
        for speed in ["Slow", "Medium", "Fast"]:
            selected = "selected" if speed == scroll_speed else ""
            page += f"<option value=\"{speed}\" {selected}>{speed}</option>"
        page += "</select>"
        page += "</div>"
        page += "</div>"

        # Color settings
        page += "<div class=\"settings-section\">"
        page += "<h3>Color Settings</h3>"
        for color_setting_name, color_value in settings.items():
            if "color" in color_setting_name:
                page += "<p>"
                page += f"<label for=\"Name\">{self.app.settings_manager.get_pretty_name(color_setting_name)}</label>"
                page += ColorUtils.html_color_chooser(color_setting_name, hex_num_str=color_value)
                page += "</p>"
        page += "</div>"

        page += "<button type=\"submit\">Save Settings</button>"
        page += "</form>"

        page += "</div></body></html>"
        return page