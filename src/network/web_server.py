"""
Web server implementation for the ThemeParkAPI.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import time

from adafruit_datetime import datetime
from adafruit_httpserver import Server, Redirect
from adafruit_httpserver import Request
from adafruit_httpserver import Response
from adafruit_httpserver.methods import GET, POST

from src.models.vacation import Vacation
from src.utils.color_utils import ColorUtils
from src.utils.error_handler import ErrorHandler
from adafruit_httpserver import REQUEST_HANDLED_RESPONSE_SENT
from src.ui.display_factory import is_circuitpython

# Initialize logger
logger = ErrorHandler("error_log")

class ThemeParkWebServer:
    """Web server implementation for ThemeParkAPI"""
    COLOR_PARAMS = ["default_color", "ride_name_color", "ride_wait_time_color"]

    def __init__(self, socket_pool, app_instance):
        """
        Initialize the web server
        
        Args:
            socket_pool: The socket pool to use
            app_instance: The ThemeParkApp instance to interact with
        """
        self.app = app_instance
        # Use a more secure root path instead of "/" to prevent exposing sensitive files
        self.server = Server(socket_pool, "src/www", debug=True)
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

                # Redirect to base URL without query parameters
                # This ensures a clean URL and proper page state
                # response = Response(request, "", content_type="text/html", headers={"Location": "/"})
                # response.status_code = 302
                response = Redirect(request, "/")
                return response

            # Generate main page (no query params)
            page = self.generate_main_page()
            return Response(request, page, content_type="text/html")

        @self.server.route("/style.css", [GET])
        def style(request: Request):
            """Serve CSS styles"""
            try:
                # First try to read from www directory (preferred location)
                try:
                    with open("/src/www/style.css", "r") as f:
                        content = f.read()
                    logger.debug("Successfully served style.css from /www")
                    return Response(request, content, content_type="text/css")
                except OSError:
                    # Fallback to src directory for backward compatibility
                    with open("/www/style.css", "r") as f:
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
            update_checked = 'update_checked' in str(request.query_params) if request.query_params else False
            update_error = None
            
            if request.query_params and 'update_error' in str(request.query_params):
                import urllib.parse
                import re
                error_match = re.search(r'update_error=([^&]+)', str(request.query_params))
                if error_match:
                    update_error = urllib.parse.unquote(error_match.group(1))

            if query_params and not update_checked and not update_error:
                # Process settings form submission
                try:
                    self._process_query_params(query_params)
                    logger.info(f"Processed settings form params: {query_params}")
                    return Redirect(request, "/")
                except Exception as e:
                    logger.error(e, f"Error processing settings query params: {query_params}")

            # Generate settings page
            # Generate settings page with success message if query params were processed
            success = query_params and not update_checked and not update_error
            page = self.generate_settings_page(success=success, update_checked=update_checked, update_error=update_error)
            return Response(request, page, content_type="text/html")
        
        @self.server.route("/update", [POST])
        def handle_update(request: Request):
            """Handle OTA update request"""
            try:
                logger.info("OTA update requested via web interface")
                
                # Schedule update for next boot
                self.app.ota_updater.check_for_update_to_install_during_next_reboot()
                
                # Create a simple response page
                page = "<!DOCTYPE html><html><head>"
                page += "<title>Update Started - Theme Park Waits</title>"
                page += "<meta http-equiv='refresh' content='5;url=/'>'"
                page += "</head><body>"
                page += "<h2>Update Started</h2>"
                page += "<p>The update has been scheduled. The device will restart shortly.</p>"
                page += "<p>Please wait up to 10 minutes for the update to complete.</p>"
                page += "<p><strong>Do not unplug the device!</strong></p>"
                page += "</body></html>"
                
                # Send response before rebooting
                response = Response(request, page, content_type="text/html")
                
                # Schedule reboot after a short delay
                async def delayed_reboot():
                    await asyncio.sleep(2)
                    logger.info("Rebooting for OTA update...")
                    if is_circuitpython():
                        import supervisor
                        supervisor.reload()
                    else:
                        logger.info("Dev mode - would reboot here")
                
                # Create task for delayed reboot (won't block response)
                asyncio.create_task(delayed_reboot())
                
                return response
                
            except Exception as e:
                logger.error(e, "Error initiating OTA update")
                return Response(request, self.generate_settings_page(), content_type="text/html")

        @self.server.route("/check-update", [GET])
        def check_update(request: Request):
            """Handle check for updates request"""
            try:
                logger.info("Update check requested via web interface")
                
                # Get current and latest versions
                current_version = self.app.ota_updater.get_version("src")
                latest_version = self.app.ota_updater.get_latest_version()
                
                # Store the latest version info in settings manager temporarily
                self.app.settings_manager.latest_version_check = {
                    'current': current_version,
                    'latest': latest_version,
                    'checked_at': time.time()
                }
                
                # Redirect back to settings page with update info
                return Redirect(request, "/settings?update_checked=1")
                
            except Exception as e:
                logger.error(e, "Error checking for updates")
                # Redirect back to settings with error
                # URL encode the error message manually for CircuitPython
                error_msg = str(e).replace(' ', '%20').replace("'", '%27')
                return Redirect(request, f"/settings?update_error={error_msg}")

        @self.server.route("/api/park", [GET])
        def api_park(request: Request):
            """API endpoint to get data for a specific park"""
            import json
            
            try:
                # Extract park ID from query parameters
                park_id = None
                if request.query_params and "id" in request.query_params:
                    park_id = int(request.query_params["id"])
                
                # If no park ID provided, use current park
                if not park_id and hasattr(self.app, 'theme_park_service'):
                    if (hasattr(self.app.theme_park_service, 'park_list') and
                        hasattr(self.app.theme_park_service.park_list, 'current_park')):
                        park_id = self.app.theme_park_service.park_list.current_park.id
                
                if not park_id:
                    error_json = json.dumps({"error": "No park ID provided and no current park set"})
                    response = Response(request, error_json, content_type="application/json")
                    response.status_code = 400
                    return response
                
                # Get park data
                park_data = {}
                
                if hasattr(self.app, 'theme_park_service'):
                    # Get park from park list
                    park = None
                    if hasattr(self.app.theme_park_service, 'park_list'):
                        park = self.app.theme_park_service.park_list.get_park_by_id(park_id)
                    
                    if park:
                        # Build park data response
                        rides = []
                        # If park has no rides, try to fetch them from the API
                        if not park.rides:
                            logger.info(f"Park {park.name} has no rides, attempting to fetch from API")
                            # Use asyncio to run the async method
                            if hasattr(self.app.theme_park_service, 'get_rides_for_park_async'):
                                import asyncio
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    rides = loop.run_until_complete(self.app.theme_park_service.get_rides_for_park_async(park_id))
                                finally:
                                    loop.close()
                            else:
                                available_rides = self.app.theme_park_service.get_available_rides(park_id)
                                for ride_info in available_rides:
                                    rides.append(ride_info)
                        else:
                            for ride in park.rides:
                                rides.append({
                                    "name": ride.name,
                                    "wait_time": ride.wait_time,
                                    "is_open": ride.open_flag
                                })
                        
                        park_data = {
                            "id": park.id,
                            "name": park.name,
                            "is_open": park.is_open,
                            "rides": rides,
                            "latitude": park.latitude,
                            "longitude": park.longitude
                        }
                    else:
                        error_json = json.dumps({"error": f"Park with ID {park_id} not found"})
                        response = Response(request, error_json, content_type="application/json")
                        response.status_code = 404
                        return response
                else:
                    error_json = json.dumps({"error": "Theme park service not available"})
                    response = Response(request, error_json, content_type="application/json")
                    response.status_code = 500
                    return response
                
                # Return JSON response
                response_json = json.dumps(park_data)
                return Response(request, response_json, content_type="application/json")
                
            except Exception as e:
                logger.error(e, f"Error in park API endpoint")
                error_json = json.dumps({"error": "Failed to get park data"})
                response = Response(request, error_json, content_type="application/json")
                response.status_code = 500
                return response

    def start(self, ip_address):
        """
        Start the web server with improved reliability
        
        Args:
            ip_address: The IP address to bind to
        """
        try:
            # Make sure to convert IP to string and specify port 80
            logger.debug(f"Starting server on {ip_address}:80")

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
        """Stop the web server with improved error handling"""
        if not self.is_running:
            return
            
        try:
            # Mark as not running first to prevent further poll operations
            self.is_running = False
            
            # Add delay to allow any in-flight requests to complete
            import time
            time.sleep(0.5)
            
            try:
                # Check if server has a valid socket before stopping
                if hasattr(self.server, 'server_socket') and self.server.server_socket:
                    self.server.stop()
                    logger.debug("Web server stopped successfully")
                else:
                    logger.debug("Server already stopped or has invalid socket")
            except Exception as stop_error:
                logger.error(stop_error, "Error stopping web server")
                
            # Ensure we release resources associated with the server
            if hasattr(self.server, 'server_socket'):
                try:
                    if self.server.server_socket:
                        self.server.server_socket.close()
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(e, "Unexpected error in web server stop")
        finally:
            # Always mark as not running, regardless of exceptions
            self.is_running = False

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

        # Track if park was changed
        park_changed = False

        # Parse park-id-1 through park-id-4 parameters
        park_ids = []
        for i in range(1, 5):
            park_param = f"park-id-{i}="
            if park_param in query_params:
                try:
                    # Extract park ID value
                    import re
                    match = re.search(f'park-id-{i}=([^&]+)', query_params)
                    if match:
                        park_id = int(match.group(1))
                        if park_id > 0:  # Only add valid park IDs
                            park_ids.append(park_id)
                except (ValueError, TypeError):
                    pass
        
        # Check if parks changed
        if park_ids or "park-id-" in query_params:
            try:
                # Get current selected parks
                current_park_ids = []
                if (hasattr(self.app.theme_park_service, 'park_list') and
                        hasattr(self.app.theme_park_service.park_list, 'selected_parks')):
                    current_park_ids = [p.id for p in self.app.theme_park_service.park_list.selected_parks]
                
                # Update selected parks
                if hasattr(self.app.theme_park_service, 'park_list'):
                    # Clear existing selections
                    self.app.theme_park_service.park_list.selected_parks = []
                    
                    # Add new selections
                    for park_id in park_ids:
                        park = self.app.theme_park_service.park_list.get_park_by_id(park_id)
                        if park:
                            self.app.theme_park_service.park_list.selected_parks.append(park)
                    
                    # Check if parks changed
                    new_park_ids = [p.id for p in self.app.theme_park_service.park_list.selected_parks]
                    park_changed = (sorted(current_park_ids) != sorted(new_park_ids))
                    
                    if park_changed:
                        logger.info(f"Parks changed from {current_park_ids} to {new_park_ids}")
                        
                        # Store the selected parks to settings
                        self.app.theme_park_service.park_list.store_settings(self.app.settings_manager)
                        
                        # Set flag to trigger update in the main loop
                        if hasattr(self.app.theme_park_service, 'update_needed'):
                            self.app.theme_park_service.update_needed = True
                        else:
                            # Add the attribute if it doesn't exist
                            self.app.theme_park_service.update_needed = True
                        logger.info(f"Parks changed, triggering data update")
            except Exception as e:
                logger.error(e, "Error updating park selection")
        
        # Always use all_rides display mode (single ride functionality removed)
        settings_changed = False
        self.app.settings_manager.settings["display_mode"] = "all_rides"

        # Always set checkbox values (they'll be missing from query_params if unchecked)
        if hasattr(self.app.theme_park_service, 'park_list'):
            # Handle skip_closed checkbox
            skip_closed = "skip_closed=on" in query_params
            self.app.theme_park_service.park_list.skip_closed = skip_closed
            logger.debug(f"Set skip_closed to {skip_closed}")

            # Handle skip_meet checkbox
            skip_meet = "skip_meet=on" in query_params
            self.app.theme_park_service.park_list.skip_meet = skip_meet
            logger.debug(f"Set skip_meet to {skip_meet}")

        # Process vacation parameters if present
        vacation_updated = False
        if "Year=" in query_params and hasattr(self.app.theme_park_service, 'vacation'):
            try:
                # Always parse vacation data if any field is present
                self.app.theme_park_service.vacation.parse(query_params)
                vacation_updated = True
                logger.debug(f"Updated vacation settings from query params")
            except Exception as e:
                logger.error(e, "Error updating vacation settings")

        # Track display settings changes
        brightness_changed = False
        brightness_match = False
        scroll_changed = False
        import re
        # Process display settings
        if "domain_name=" in query_params:
            try:
                # Extract domain name value

                domain_match = re.search(r'domain_name=([^&]+)', query_params)
                if domain_match:
                    domain_name = domain_match.group(1)
                    self.app.settings_manager.settings["domain_name"] = domain_name
                    logger.debug(f"Updated domain name to {domain_name}")
            except Exception as e:
                logger.error(e, "Error updating display settings")

        # Extract brightness scale
        brightness_match = re.search(r'brightness_scale=([^&]+)', query_params)
        if brightness_match:
            brightness = brightness_match.group(1)
            self.app.settings_manager.settings["brightness_scale"] = brightness
            logger.debug(f"Updated brightness to {brightness}")
            brightness_changed = True

        self._process_color_params(query_params)

        # Extract scroll speed
        scroll_match = re.search(r'scroll_speed=([^&]+)', query_params)
        if scroll_match:
            scroll_speed = scroll_match.group(1)
            self.app.settings_manager.settings["scroll_speed"] = scroll_speed
            logger.debug(f"Updated scroll speed to {scroll_speed}")
            # No immediate action needed for scroll speed as it's read on demand when scrolling

        # Process sort mode
        sort_changed = False
        sort_match = re.search(r'sort_mode=([^&]+)', query_params)
        if sort_match:
            sort_mode = sort_match.group(1)
            old_sort_mode = self.app.settings_manager.settings.get("sort_mode", "alphabetical")
            if sort_mode != old_sort_mode:
                sort_changed = True
            self.app.settings_manager.settings["sort_mode"] = sort_mode
            logger.debug(f"Updated sort mode to {sort_mode}")
        
        # Process group by park
        old_group_by_park = self.app.settings_manager.settings.get("group_by_park", False)
        group_by_park = "group_by_park=on" in query_params
        logger.debug(f"Group by park processing: old={old_group_by_park}, new={group_by_park}, in query={('group_by_park=on' in query_params)}")
        if group_by_park != old_group_by_park:
            sort_changed = True
            logger.debug(f"Group by park changed from {old_group_by_park} to {group_by_park}, setting sort_changed=True")
        self.app.settings_manager.settings["group_by_park"] = group_by_park
        logger.debug(f"Updated group by park to {group_by_park}")

        # Save settings after changes
        try:
            self.app.settings_manager.save_settings()
            logger.debug("Settings saved successfully after processing query params")

            if (brightness_changed or scroll_changed) and hasattr(self.app, 'message_queue'):
                self.app.display.set_colors(self.app.settings_manager)
                logger.debug("Reset message queue after display settings change")
        except Exception as e:
            logger.error(e, "Error saving settings")

        # Handle use_prerelease checkbox
        if "use_prerelease=" in query_params:
            use_prerelease = "use_prerelease=on" in query_params
            self.app.settings_manager.set("use_prerelease", use_prerelease)
            # Update OTA updater with new setting
            self.app.ota_updater.use_prerelease = use_prerelease
            logger.debug(f"Updated use_prerelease to {use_prerelease}")
        
        # Save settings
        try:
            if hasattr(self.app.theme_park_service, 'save_settings'):
                self.app.theme_park_service.save_settings()
                self.last_settings_save = time.monotonic()
                logger.debug("Settings saved successfully")

                # Reset message queue if display settings changed
                if (brightness_changed or scroll_changed) and hasattr(self.app, 'message_queue'):
                    # Schedule message queue rebuild on next display refresh
                    self.app.display.set_colors(self.app.settings_manager)
                    logger.debug("Reset message queue after display settings change")
        except Exception as e:
            logger.error(e, "Error saving settings")

        # Check if only sort settings changed (no park change)
        sort_only_changed = sort_changed and not park_changed
        
        # Trigger park update if needed
        if park_changed:
            self._trigger_park_update()
            # When park changes, we need to ensure the new park's data is fetched
            # Set the update timer to expire immediately
            if hasattr(self.app, 'update_timer'):
                self.app.update_timer.reset(expired=True)
                logger.info("Forced immediate park data update after park change")
        elif sort_only_changed and hasattr(self.app, 'theme_park_service'):
            # Only sort settings changed - just rebuild the queue
            self.app.theme_park_service.queue_rebuild_needed = True
            logger.debug("Set queue_rebuild_needed flag after sort settings change")
            
            # Force immediate queue rebuild if possible
            if hasattr(self.app, 'message_queue') and hasattr(self.app, 'build_messages'):
                logger.info("Forcing immediate message queue rebuild after sort settings change")
                self.app.message_queue.init()
                # Note: We can't await here since we're not in an async context
                # The rebuild will happen on the next display loop iteration
                
        if settings_changed and hasattr(self.app, 'message_queue'):
            self.app.display.set_colors(self.app.settings_manager)
            logger.debug("Reset message queue after display mode/ride change")

        return park_changed

    def _trigger_park_update(self):
        """Trigger an update of the current park's ride times"""
        try:
            if not hasattr(self.app, 'theme_park_service'):
                return

            logger.info("Triggering park data update after park change")

            # Schedule the update task if the app has the update_data method
            # This needs to be handled carefully since we can't use await here
            if hasattr(self.app, 'update_timer'):
                # Force timer to expire to trigger update on next cycle
                self.app.update_timer.reset(expired=True)
                logger.debug("Reset update timer to trigger immediate update")

            # Alternative approach - create a flag to signal update needed
            if hasattr(self.app, 'theme_park_service'):
                self.app.theme_park_service.update_needed = True
                logger.debug("Set update_needed flag to trigger update")

        except Exception as e:
            logger.error(e, "Error triggering park update")

    async def poll(self):
        """
        Poll the server for incoming requests with improved error recovery
        
        Returns:
            True if a request was handled, False/None otherwise
        """
        if not self.is_running:
            return None

        try:
            # Poll the server for requests
            result = self.server.poll()

            # Short sleep to allow other tasks to run - essential for cooperative multitasking
            await asyncio.sleep(0.10)  # Slightly longer yield to reduce CPU usage

            # Only return a meaningful result for actual requests

            if result == REQUEST_HANDLED_RESPONSE_SENT:
                return True

            return False

        except BrokenPipeError as pipe_error:
            # BrokenPipeError is common when client disconnects prematurely
            # Log but no need to restart server as it's a client-side issue
            logger.debug(f"Client disconnected prematurely: {pipe_error}")
            await asyncio.sleep(0.1)  # Brief pause
            return False
            
        except OSError as os_error:
            # Handle specific OSError cases
            if os_error.args and os_error.args[0] == 32:  # Broken pipe
                logger.debug("OSError: Broken pipe - client disconnected")
                await asyncio.sleep(0.1)
                return False
            elif os_error.args and os_error.args[0] == 104:  # Connection reset
                logger.debug("OSError: Connection reset by client")
                await asyncio.sleep(0.1)
                return False
            else:
                # Other OS errors might require restart
                logger.error(os_error, f"OS Error in web server poll: {os_error}")
                await self._attempt_server_restart()
                return False
                
        except Exception as e:
            # Log the error but don't crash the server
            logger.error(e, f"Error in web server poll: {type(e).__name__}")

            # Brief pause to avoid error loops
            await asyncio.sleep(0.5)  # Longer pause for more serious errors

            # Check if server still needs to be restarted
            await self._attempt_server_restart()
            
            return False
    
    async def _attempt_server_restart(self):
        """Helper method to attempt server restart with proper error handling"""
        # First check if the server socket is still valid
        try:
            # Access a server property to check if it's functioning
            if hasattr(self.server, 'server_socket') and self.server.server_socket:
                addr = self.server.server_socket.getsockname()
                # If we get here, server socket is still valid
                return
        except Exception:
            # Server socket appears invalid, needs restart
            pass
            
        # If we get here, server needs restart
        logger.info("Restarting web server after error")
        
        # Implement a circuit breaker pattern to avoid restart loops
        import time
        # Track restart time in a module variable
        if not hasattr(self, '_last_restart_time'):
            self._last_restart_time = 0
            self._restart_attempts = 0
            
        current_time = time.monotonic()
        # Limit restarts to max once per 10 seconds to avoid rapid restarts
        if current_time - self._last_restart_time < 10:
            self._restart_attempts += 1
            # If we've had multiple rapid restart attempts, wait longer before trying again
            if self._restart_attempts > 3:
                logger.error(None, f"Multiple restart attempts ({self._restart_attempts}), waiting longer...")
                await asyncio.sleep(5)  # Longer cooldown period
                if self._restart_attempts > 10:
                    logger.error(None, "Too many restart attempts, server may be unstable")
                    self.is_running = False  # Mark as not running to prevent further attempts
                    return
            return
            
        # Try to restart the server
        try:
            # Record this attempt
            self._last_restart_time = current_time
            self._restart_attempts += 1
            
            # Stop all current connections
            self.is_running = False
            try:
                self.server.stop()
            except Exception as stop_error:
                logger.error(stop_error, "Error stopping server during restart")
            
            # Wait to ensure sockets are released
            await asyncio.sleep(2)
            
            # Create a fresh server instance to avoid any stale state
            import socketpool
            import wifi
            
            # In CircuitPython, we can't test if port is in use with socket module
            # Just wait to ensure previous connections are closed
            logger.debug("Waiting for port to be released before restart")
            await asyncio.sleep(2)  # Wait for connections to close
                
            # Start the server fresh
            try:
                self.server = Server(socketpool.SocketPool(wifi.radio), "src/www", debug=True)
                self.register_routes()  # Re-register the routes
                self.server.start("0.0.0.0", 80)
                self.is_running = True
                logger.info("Web server restarted successfully")
                
                # Reset restart counter on success
                self._restart_attempts = 0
            except Exception as start_error:
                logger.error(start_error, "Failed to restart web server")
                self.is_running = False
                
        except Exception as restart_error:
            logger.error(restart_error, "Unexpected error during server restart")
            self.is_running = False

    def generate_main_page(self):
        """
        Generate the main HTML page optimized for performance
        
        Returns:
            HTML content for the main page
        """
        # Use list for efficient string building
        page_parts = []
        
        # Pre-build static header
        page_parts.extend([
            "<!DOCTYPE html><html><head>",
            "<title>Theme Park Waits</title>",
            "<link rel=\"stylesheet\" href=\"/style.css\">",
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            "</head><body>",
            "<div class=\"navbar\">",
            "<a href=\"/\">Theme Park Wait Times</a>",
            "<div class=\"gear-icon\">",
            "<a href=\"/settings\"><img src=\"gear.png\" alt=\"Settings\"></a>",
            "</div></div>",
            "<div class=\"main-content\">",
            "<h2>Theme Park Selection</h2>"
        ])

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
            page_parts.append("<form action=\"/\" method=\"get\">")
            
            # Get currently selected parks
            selected_park_ids = []
            if hasattr(self.app.theme_park_service.park_list, 'selected_parks'):
                selected_park_ids = [p.id for p in self.app.theme_park_service.park_list.selected_parks]
            
            # Create 4 park dropdowns
            page_parts.append("<div class=\"park-selection\">")
            page_parts.append("<h3>Select Parks (up to 4)</h3>")
            
            parks = response_data.get("parks", [])
            
            for i in range(1, 5):  # 1 through 4
                page_parts.append(f"<div class=\"park-dropdown\">")
                page_parts.append(f"<label for=\"park-id-{i}\">Park {i}:</label>")
                page_parts.append(f"<select name=\"park-id-{i}\" id=\"park-select-{i}\">")
                
                # Default option
                page_parts.append(f"<option value=\"0\">Select Park {i}</option>")
                
                if not parks:
                    page_parts.append("<option value=\"0\">No parks available - check connection</option>")
                else:
                    # Get the park ID for this position
                    current_selection = selected_park_ids[i-1] if i <= len(selected_park_ids) else None
                    
                    for park in parks:
                        park_id = park.get("id", "")
                        park_name = park.get("name", "Unknown Park")
                        selected = "selected" if park_id == current_selection else ""
                        page_parts.append(f"<option value=\"{park_id}\" {selected}>{park_name}</option>")
                
                page_parts.append("</select>")
                page_parts.append("</div>")
            
            page_parts.append("</div>")
            # Safe access to settings
            settings = response_data.get("settings", {})
            if not isinstance(settings, dict):
                settings = {}

            # Create options div with better formatting
            page_parts.append("<div class=\"options\">")
            page_parts.append("<h3 style=\"margin-top: 0; margin-bottom: 10px; text-align: left; padding-left: 20px;\">Display Options</h3>")

            # Display Mode - Always show all rides (single ride functionality removed)
            page_parts.append("<div class=\"form-group\">")
            page_parts.append("<input type=\"hidden\" name=\"display_mode\" value=\"all_rides\">")
            
            
            
            page_parts.append("</div>")
            
            # Skip Rides Section
            page_parts.append("<div class=\"display-options\">")
            # page += "<h3 style=\"margin-top: 10px; margin-bottom: 10px; text-align: left; padding-left: 20px;\">Display Options</h3>"
            
            # Skip Closed Rides option - Fixed alignment with label
            page_parts.append("<div class=\"form-group checkbox-group\">")

            # Get skip_closed value from park_list with safe fallback
            skip_closed = False
            try:
                if hasattr(self.app.theme_park_service, 'park_list') and hasattr(self.app.theme_park_service.park_list, 'skip_closed'):
                    skip_closed = bool(self.app.theme_park_service.park_list.skip_closed)
                else:
                    skip_closed = bool(settings.get("skip_closed", False))
            except (TypeError, ValueError, AttributeError):
                skip_closed = False

            checked = "checked" if skip_closed else ""
            # Keep checkbox and label together in a tight layout
            page_parts.append(f"<input type=\"checkbox\" id=\"skip_closed\" name=\"skip_closed\" {checked}>")
            page_parts.append("<label for=\"skip_closed\">Skip Closed Rides</label>")
            page_parts.append("</div>")

            # Skip Meet & Greets option - Fixed alignment with label
            page_parts.append("<div class=\"form-group checkbox-group\">")

            # Get skip_meet value from park_list with safe fallback
            skip_meet = False
            try:
                if hasattr(self.app.theme_park_service, 'park_list') and hasattr(self.app.theme_park_service.park_list, 'skip_meet'):
                    skip_meet = bool(self.app.theme_park_service.park_list.skip_meet)
                else:
                    skip_meet = bool(settings.get("skip_meet", False))
            except (TypeError, ValueError, AttributeError):
                skip_meet = False

            checked = "checked" if skip_meet else ""
            # Keep checkbox and label together in a tight layout
            page_parts.append(f"<input type=\"checkbox\" id=\"skip_meet\" name=\"skip_meet\" {checked}>")
            page_parts.append("<label for=\"skip_meet\">Skip Meet & Greets</label>")
            page_parts.append("</div>")
            
            # Sort mode
            page_parts.append("<div class=\"form-group\">")
            page_parts.append("<label for=\"sort_mode\">Sort Rides By:</label>")
            sort_mode = settings.get("sort_mode", "alphabetical")
            page_parts.append("<select id=\"sort_mode\" name=\"sort_mode\">")
            sort_options = [
                ("alphabetical", "Alphabetical"),
                ("max_wait", "Longest Wait First"),
                ("min_wait", "Shortest Wait First")
            ]
            for value, label in sort_options:
                selected = "selected" if value == sort_mode else ""
                page_parts.append(f"<option value=\"{value}\" {selected}>{label}</option>")
            page_parts.append("</select>")
            page_parts.append("</div>")
            
            # Group by park
            page_parts.append("<div class=\"form-group checkbox-group\">")
            group_by_park = settings.get("group_by_park", False)
            checked = "checked" if group_by_park else ""
            page_parts.append(f"<input type=\"checkbox\" id=\"group_by_park\" name=\"group_by_park\" {checked}>")
            page_parts.append("<label for=\"group_by_park\">Group rides by park</label>")
            page_parts.append("</div>")

            page_parts.append("</div>")

        else:
            page_parts.append("<p>No theme parks available.</p>")


        vacation_date = Vacation()
        vacation_date.load_settings(self.app.settings_manager)
        page_parts.append("<h2>Configure Countdown</h2>")
        page_parts.append("<div class=\"countdown-section\">")
        page_parts.append("<p>")
        page_parts.append("<label for=\"Name\">Event:</label>")
        page_parts.append(f"<input type=\"text\" name=\"Name\" value=\"{vacation_date.name}\">")
        page_parts.append("</p>")

        page_parts.append("<p>")
        page_parts.append("<label for=\"Date\">Date:</label>")
        page_parts.append("<div class=\"date-selectors\">")
        
        # Year dropdown
        page_parts.append("<select id=\"Year\" name=\"Year\">")
        year_now = datetime.now().year
        for year_idx, year in enumerate(range(year_now, 2044)):
            # Yield control every 5 years to allow LED scrolling

            if vacation_date.is_set() is True and year == vacation_date.year:
                page_parts.append(f"<option value=\"{year}\" selected>{year}</option>\n")
            else:
                page_parts.append(f"<option value=\"{year}\">{year}</option>\n")
        page_parts.append("</select>")

        # Month dropdown with names
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        page_parts.append("<select id=\"Month\" name=\"Month\">")

        for month in range(1, 13):
            if vacation_date.is_set() is True and month == vacation_date.month:
                page_parts.append(f"<option value=\"{month}\" selected>{month_names[month-1]}</option>\n")
            else:
                page_parts.append(f"<option value=\"{month}\">{month_names[month-1]}</option>\n")
        page_parts.append("</select>")

        # Day dropdown
        page_parts.append("<select id=\"Day\" name=\"Day\">")
        # Yield control before processing days

        for day in range(1, 32):
            if vacation_date.is_set() is True and day == vacation_date.day:
                page_parts.append(f"<option value=\"{day}\" selected>{day}</option>\n")
            else:
                page_parts.append(f"<option value=\"{day}\">{day}</option>\n")
        page_parts.append("</select>")
        page_parts.append("</div>") # end date-selectors
        page_parts.append("</p>")

        # If vacation is set, show countdown
        if vacation_date.is_set():
            days_until = vacation_date.get_days_until()
            if days_until > 0:
                page_parts.append(f"<p style=\"text-align: center; font-weight: bold; margin-top: 10px;\">")
                page_parts.append(f"Days until {vacation_date.name}: {days_until}")
                page_parts.append("</p>")
        
        page_parts.append("</div>") # end countdown-section

        page_parts.append("<button type=\"submit\">Update</button>")
        page_parts.append("</form>")

        page_parts.append("</div></body></html>")
        return ''.join(page_parts)
    
    def _generate_main_page_sync(self):
        """
        Synchronous fallback for generate_main_page when async is not available
        
        Returns:
            HTML content for the main page
        """
        # This is a simplified synchronous version for fallback
        # Remove all async/await calls and yield points
        page = "<!DOCTYPE html><html><head>"
        page += "<title>Theme Park Waits</title>"
        page += "<link rel=\"stylesheet\" href=\"/style.css\">"
        page += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        page += "</head>"
        page += "<body>"
        
        page += "<div class=\"navbar\">"
        page += "<a href=\"/\">Theme Park Wait Times</a>"
        page += "<div class=\"gear-icon\">"
        page += "<a href=\"/settings\"><img src=\"gear.png\" alt=\"Settings\"></a>"
        page += "</div>"
        page += "</div>"
        
        page += "<div class=\"main-content\">"
        page += "<h2>Loading...</h2>"
        page += "<p>Page generation in progress. Please refresh in a moment.</p>"
        page += "</div></body></html>"
        
        return page

    def generate_settings_page(self, success=False, update_checked=False, update_error=None):
        """
        Generate the settings HTML page

        Args:
            success: Whether to show a success message
            update_checked: Whether we just checked for updates
            update_error: Error message if update check failed

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
        page += "<link rel=\"stylesheet\" href=\"/style.css\">"
        page += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        page += "</head>"
        page += "<body>"

        page += "<div class=\"navbar\">"
        page += "<a href=\"/\">Theme Park Wait Times</a>"
        # Add gear icon using image for consistent styling with main page
        page += "<div class=\"gear-icon\">"
        page += "<a href=\"/settings\"><img src=\"gear.png\" alt=\"Settings\"></a>"
        page += "</div>"
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
        page += "<label for=\"domain_name\">Hostname:</label>"
        domain_name = settings.get("domain_name", "themeparkwaits")
        page += f"<input type=\"text\" id=\"domain_name\" name=\"domain_name\" value=\"{domain_name}\">"
        page += "<label for=\"domain_name\">.local</label>"
        page += "<br><small>Hostname change requires a device restart</small>"
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
        
        # Add OTA update section
        page += self._generate_ota_section(update_checked, update_error)

        page += "</div></body></html>"
        return page
    
    def _generate_ota_section(self, update_checked=False, update_error=None):
        """Generate the OTA update section for settings page"""
        parts = []
        parts.append("<h2>Software Updates</h2>")
        parts.append("<div class=\"software-section\">")
        
        try:
            # Get current version
            current_version = self.app.ota_updater.get_version("src")
            parts.append(f"<p>Current version: <strong>{current_version}</strong></p>")
            
            # Check if we have recent version check results
            if update_error:
                parts.append(f"<p style='color: red;'>Error checking for updates: {update_error}</p>")
                parts.append("<p><a href='/check-update'>Try again</a></p>")
            elif update_checked and hasattr(self.app.settings_manager, 'latest_version_check'):
                version_info = self.app.settings_manager.latest_version_check
                latest = version_info.get('latest', 'Unknown')
                current = version_info.get('current', current_version)
                
                parts.append(f"<p>Latest version: <strong>{latest}</strong></p>")
                
                # Compare versions
                def version_to_tuple(v):
                    # Remove 'v' prefix if present
                    v = v.lstrip('v')
                    # Split by dots
                    parts_list = v.split('.')
                    
                    # Handle cases like "1.85" which should be "1.8.5"
                    if len(parts_list) == 2 and len(parts_list[1]) > 1:
                        # Split second part if it has multiple digits
                        major = parts_list[0]
                        minor_patch = parts_list[1]
                        if minor_patch.isdigit() and len(minor_patch) == 2:
                            # Convert "85" to "8.5"
                            parts_list = [major, minor_patch[0], minor_patch[1]]
                    
                    # Pad with zeros if needed
                    while len(parts_list) < 3:
                        parts_list.append('0')
                    return tuple(int(p) for p in parts_list[:3])
                
                try:
                    current_tuple = version_to_tuple(current)
                    latest_tuple = version_to_tuple(latest)
                    
                    if latest_tuple > current_tuple:
                        # Update available
                        parts.append("<div style='background-color: #f0f8ff; padding: 15px; margin: 15px 0; border-radius: 5px;'>")
                        parts.append("<h3 style='color: #0066cc; margin-top: 0;'>Update Available!</h3>")
                        parts.append(f"<p>A new version ({latest}) is available for installation.</p>")
                        parts.append("<p><strong>Important:</strong></p>")
                        parts.append("<ul>")
                        parts.append("<li>The update process takes up to 10 minutes</li>")
                        parts.append("<li>The display will be blank for minutes at a time</li>")
                        parts.append("<li><strong>DO NOT</strong> reset or unplug the device during the update</li>")
                        parts.append("</ul>")
                        parts.append("<form action='/update' method='post'>")
                        parts.append("<button type='submit' style='background-color: #0066cc; color: white; padding: 10px 20px; font-size: 16px; border: none; border-radius: 5px; cursor: pointer;'>Update Software</button>")
                        parts.append("</form>")
                        parts.append("</div>")
                    else:
                        # Already up to date
                        parts.append("<p style='color: #008000;'You have the latest version!</p>")
                except Exception as e:
                    logger.error(e, "Error comparing versions")
                    parts.append(f"<p>Latest version: <strong>{latest}</strong></p>")
                    parts.append("<p><a href='/check-update'>Check again</a></p>")
            else:
                # No check performed yet
                parts.append("<p>Latest version: <a href='/check-update'>Check for updates</a></p>")
                
            # Add pre-release toggle for testing
            # Always show developer options on the settings page
            parts.append("<hr>")
            parts.append("<h3>Developer Options</h3>")
            use_prerelease = self.app.settings_manager.get("use_prerelease", False)
            checked = "checked" if use_prerelease else ""
            parts.append("<form action='/settings' method='get'>")
            parts.append(f"<input type='checkbox' name='use_prerelease' id='use_prerelease' {checked}>")
            parts.append("<label for='use_prerelease'>Check for pre-release versions (testing only)</label>")
            parts.append("<button type='submit'>Update</button>")
            parts.append("</form>")
                
        except Exception as e:
            logger.error(e, "Error checking for updates")
            parts.append("<p>Unable to check for updates. Please verify internet connection.</p>")
            
        parts.append("</div>")
        return ''.join(parts)

    def _process_color_params(self, query_params: str) -> None:
        """
        Extract and update color-related settings from query parameters,
        decoding URL-encoded values without using urllib.parse.unquote.
        """
        import re

        for color_param in self.COLOR_PARAMS:
            try:
                color_pattern = f'{color_param}=([^&]+)'
                match = re.search(color_pattern, query_params)
                if match:
                    color_value = self._url_decode(match.group(1))
                    self.app.settings_manager.set(color_param, color_value)
                    logger.debug(f"Updated {color_param} to {color_value}")
            except Exception as e:
                logger.error(e, f"Error updating {color_param}")

    def _url_decode(self, encoded_str: str) -> str:
        """
        Decodes a percent-encoded string (e.g., 'Hello%20World') and plus signs ('+') to spaces,
        replicating urllib.parse.unquote's basic functionality compatible with CircuitPython.
        """
        res = []
        i = 0
        length = len(encoded_str)
        while i < length:
            char = encoded_str[i]
            if char == '+':
                res.append(' ')
                i += 1
            elif char == '%' and i + 2 < length:
                hex_value = encoded_str[i+1:i+3]
                try:
                    decoded_char = chr(int(hex_value, 16))
                    res.append(decoded_char)
                    i += 3
                except ValueError:
                    # Invalid percent-encoding, keep as is
                    res.append('%')
                    i += 1
            else:
                res.append(char)
                i += 1
        return ''.join(res)

