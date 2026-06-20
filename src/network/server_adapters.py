"""
Server adapters for different platforms (CircuitPython and Development).
Provides a common interface while handling platform-specific HTTP server implementations.
Copyright 2024 3DUPFitters LLC
"""
import sys
from abc import ABC, abstractmethod
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")

# Platform detection
IS_CIRCUITPYTHON = hasattr(sys, 'implementation') and sys.implementation.name == 'circuitpython'


class ServerAdapter(ABC):
    """Abstract base class for server adapters"""
    
    @abstractmethod
    def start_server(self, host, port):
        """Start the HTTP server"""
        pass
    
    @abstractmethod
    def stop_server(self):
        """Stop the HTTP server"""
        pass
    
    @abstractmethod
    def parse_query_params(self, query_string):
        """Parse query parameters from URL"""
        pass
    
    @abstractmethod
    def parse_form_data(self, request_body):
        """Parse form data from POST request"""
        pass


if IS_CIRCUITPYTHON:
    class CircuitPythonAdapter(ServerAdapter):
        """Server adapter for CircuitPython using adafruit_httpserver"""
        
        def __init__(self, core, wifi_manager):
            """
            Initialize CircuitPython adapter
            
            Args:
                core: WebServerCore instance
                wifi_manager: WiFi manager instance
            """
            self.core = core
            self.wifi_manager = wifi_manager
            self.server = None
            
        def start_server(self, host="0.0.0.0", port=80):
            """Start the CircuitPython HTTP server"""
            try:
                from adafruit_httpserver import HTTPServer, HTTPRoute, HTTPResponse
                import socketpool
                
                # Create socket pool
                pool = socketpool.SocketPool(self.wifi_manager.esp.wifi)
                
                # Create server
                self.server = HTTPServer(pool, "/src/www")
                
                # Set up routes
                self._setup_routes()
                
                # Start server
                self.server.start(str(self.wifi_manager.esp.pretty_ip))
                logger.info(f"CircuitPython web server started on {self.wifi_manager.esp.pretty_ip}:80")
                
                return True
                
            except Exception as e:
                logger.error(e, "Failed to start CircuitPython web server")
                return False
        
        def stop_server(self):
            """Stop the CircuitPython HTTP server"""
            if self.server:
                try:
                    self.server.stop()
                    logger.info("CircuitPython web server stopped")
                except Exception as e:
                    logger.error(e, "Error stopping CircuitPython web server")
        
        def _setup_routes(self):
            """Set up HTTP routes for CircuitPython"""
            from adafruit_httpserver import HTTPRoute, HTTPResponse
            
            @self.server.route("/", methods=["GET"])
            def serve_main_page(request):
                """Serve the main configuration page"""
                html = self.core.generate_main_page()
                return HTTPResponse(content_type="text/html", body=html)
            
            @self.server.route("/", methods=["POST"])
            def handle_main_form(request):
                """Handle main form submission"""
                form_data = self.parse_form_data(request.body)
                success, message = self.core.process_main_form(form_data)
                
                response_html = self.core.generate_redirect_response(
                    "success" if success else "error", message
                )
                return HTTPResponse(content_type="text/html", body=response_html)
            
            @self.server.route("/colors", methods=["POST"])
            def handle_color_form(request):
                """Handle color form submission"""
                form_data = self.parse_form_data(request.body)
                success, message = self.core.process_color_form(form_data)
                
                response_html = self.core.generate_redirect_response(
                    "success" if success else "error", message
                )
                return HTTPResponse(content_type="text/html", body=response_html)
            
            @self.server.route("/ota", methods=["POST"])
            def handle_ota_form(request):
                """Handle OTA form submission"""
                form_data = self.parse_form_data(request.body)
                success, message = self.core.process_ota_form(form_data)
                
                response_html = self.core.generate_redirect_response(
                    "success" if success else "error", message
                )
                return HTTPResponse(content_type="text/html", body=response_html)
            
            @self.server.route("/style.css")
            def serve_css(request):
                """Serve CSS file"""
                content, content_type = self.core.get_static_file_content("style.css")
                if content:
                    return HTTPResponse(content_type=content_type, body=content)
                else:
                    return HTTPResponse(status=404, body="Not Found")
        
        def parse_query_params(self, query_string):
            """Parse query parameters from URL"""
            params = {}
            if not query_string:
                return params
                
            try:
                for pair in query_string.split('&'):
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        # Simple URL decode
                        key = key.replace('%20', ' ').replace('+', ' ')
                        value = value.replace('%20', ' ').replace('+', ' ')
                        params[key] = value
            except Exception as e:
                logger.error(e, "Error parsing query parameters")
                
            return params
        
        def parse_form_data(self, request_body):
            """Parse form data from POST request"""
            if not request_body:
                return {}
                
            # Convert bytes to string if needed
            if isinstance(request_body, bytes):
                try:
                    request_body = request_body.decode('utf-8')
                except UnicodeDecodeError:
                    logger.error("Failed to decode form data")
                    return {}
            
            return self.parse_query_params(request_body)

else:
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import parse_qs, urlparse
    
    class DevelopmentAdapter(ServerAdapter):
        """Server adapter for development using Python's http.server"""
        
        def __init__(self, core):
            """
            Initialize development adapter
            
            Args:
                core: WebServerCore instance
            """
            self.core = core
            self.server = None
            self.server_thread = None
            
        def start_server(self, host="localhost", port=8080):
            """Start the development HTTP server"""
            try:
                # Create request handler class with access to core
                core = self.core
                
                class ThemeParkRequestHandler(BaseHTTPRequestHandler):
                    def log_message(self, format, *args):
                        """Override to use our logger"""
                        logger.debug(f"HTTP: {format % args}")
                    
                    def do_GET(self):
                        """Handle GET requests"""
                        try:
                            parsed_url = urlparse(self.path)
                            path = parsed_url.path
                            
                            if path == "/" or path == "/index.html":
                                # Serve main page
                                html = core.generate_main_page()
                                self._send_response(200, "text/html", html)
                            elif path == "/style.css":
                                # Serve CSS
                                content, content_type = core.get_static_file_content("style.css")
                                if content:
                                    self._send_response(200, content_type, content)
                                else:
                                    self._send_response(404, "text/plain", "Not Found")
                            elif path.startswith("/gear."):
                                # Serve gear images
                                filename = path[1:]  # Remove leading slash
                                content, content_type = core.get_static_file_content(filename)
                                if content:
                                    self._send_response(200, content_type, content, binary=True)
                                else:
                                    self._send_response(404, "text/plain", "Not Found")
                            else:
                                self._send_response(404, "text/plain", "Not Found")
                                
                        except Exception as e:
                            logger.error(e, "Error handling GET request")
                            self._send_response(500, "text/plain", "Internal Server Error")
                    
                    def do_POST(self):
                        """Handle POST requests"""
                        try:
                            parsed_url = urlparse(self.path)
                            path = parsed_url.path
                            
                            # Read form data
                            content_length = int(self.headers.get('Content-Length', 0))
                            post_data = self.rfile.read(content_length).decode('utf-8')
                            form_data = adapter.parse_form_data(post_data)
                            
                            if path == "/":
                                # Handle main form
                                success, message = core.process_main_form(form_data)
                            elif path == "/colors":
                                # Handle color form
                                success, message = core.process_color_form(form_data)
                            elif path == "/ota":
                                # Handle OTA form
                                success, message = core.process_ota_form(form_data)
                            else:
                                success, message = False, "Unknown endpoint"
                            
                            # Send redirect response
                            response_html = core.generate_redirect_response(
                                "success" if success else "error", message
                            )
                            self._send_response(200, "text/html", response_html)
                            
                        except Exception as e:
                            logger.error(e, "Error handling POST request")
                            self._send_response(500, "text/plain", "Internal Server Error")
                    
                    def _send_response(self, status, content_type, content, binary=False):
                        """Send HTTP response"""
                        self.send_response(status)
                        self.send_header('Content-type', content_type)
                        self.end_headers()
                        
                        if binary:
                            self.wfile.write(content)
                        else:
                            self.wfile.write(content.encode('utf-8'))
                
                # Store adapter reference for request handler
                adapter = self
                
                # Create and start server
                self.server = HTTPServer((host, port), ThemeParkRequestHandler)
                self.server_thread = threading.Thread(target=self.server.serve_forever)
                self.server_thread.daemon = True
                self.server_thread.start()
                
                logger.info(f"Development web server started on http://{host}:{port}")
                return True
                
            except Exception as e:
                logger.error(e, "Failed to start development web server")
                return False
        
        def stop_server(self):
            """Stop the development HTTP server"""
            if self.server:
                try:
                    self.server.shutdown()
                    self.server.server_close()
                    if self.server_thread:
                        self.server_thread.join(timeout=5)
                    logger.info("Development web server stopped")
                except Exception as e:
                    logger.error(e, "Error stopping development web server")
        
        def parse_query_params(self, query_string):
            """Parse query parameters from URL"""
            if not query_string:
                return {}
            
            try:
                parsed = parse_qs(query_string, keep_blank_values=True)
                # Convert lists to single values (take first value if multiple)
                params = {}
                for key, values in parsed.items():
                    params[key] = values[0] if values else ""
                return params
            except Exception as e:
                logger.error(e, "Error parsing query parameters")
                return {}
        
        def parse_form_data(self, request_body):
            """Parse form data from POST request"""
            return self.parse_query_params(request_body)


def create_server_adapter(core, wifi_manager=None):
    """
    Factory function to create the appropriate server adapter
    
    Args:
        core: WebServerCore instance
        wifi_manager: WiFi manager (CircuitPython only)
        
    Returns:
        ServerAdapter instance
    """
    if IS_CIRCUITPYTHON:
        if not wifi_manager:
            raise ValueError("WiFi manager required for CircuitPython adapter")
        return CircuitPythonAdapter(core, wifi_manager)
    else:
        return DevelopmentAdapter(core)