"""
Unified web server that works on both CircuitPython and development environments.
Eliminates the duplication between web_server.py and dev_web_server.py.
Copyright 2024 3DUPFitters LLC
"""
import sys
from src.network.web_server_core import WebServerCore
from src.network.server_adapters import create_server_adapter
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")

# Platform detection
IS_CIRCUITPYTHON = hasattr(sys, 'implementation') and sys.implementation.name == 'circuitpython'


class UnifiedWebServer:
    """Unified web server that works on both CircuitPython and development platforms"""
    
    def __init__(self, settings_manager, wifi_manager=None, ota_updater=None):
        """
        Initialize the unified web server
        
        Args:
            settings_manager: Settings manager instance
            wifi_manager: WiFi manager (required for CircuitPython)
            ota_updater: OTA updater instance (optional)
        """
        self.settings_manager = settings_manager
        self.wifi_manager = wifi_manager
        self.ota_updater = ota_updater
        
        # Create core business logic
        self.core = WebServerCore(settings_manager, ota_updater)
        
        # Create platform-specific adapter
        self.adapter = create_server_adapter(self.core, wifi_manager)
        
        self.running = False
        
    def start(self, host=None, port=None):
        """
        Start the web server
        
        Args:
            host: Host to bind to (optional, platform-specific defaults)
            port: Port to bind to (optional, platform-specific defaults)
            
        Returns:
            True if server started successfully, False otherwise
        """
        try:
            # Set platform-appropriate defaults
            if IS_CIRCUITPYTHON:
                host = host or "0.0.0.0"
                port = port or 80
            else:
                host = host or "localhost"
                port = port or 8080
            
            logger.info(f"Starting unified web server on {host}:{port}")
            
            success = self.adapter.start_server(host, port)
            if success:
                self.running = True
                logger.info("Unified web server started successfully")
            else:
                logger.error("Failed to start unified web server")
                
            return success
            
        except Exception as e:
            logger.error(e, "Error starting unified web server")
            return False
    
    def stop(self):
        """Stop the web server"""
        try:
            if self.running:
                logger.info("Stopping unified web server")
                self.adapter.stop_server()
                self.running = False
                logger.info("Unified web server stopped")
        except Exception as e:
            logger.error(e, "Error stopping unified web server")
    
    def is_running(self):
        """
        Check if the web server is running
        
        Returns:
            True if running, False otherwise
        """
        return self.running
    
    def handle_requests(self):
        """
        Handle incoming requests (CircuitPython only)
        
        For CircuitPython, this method should be called regularly in the main loop
        to handle incoming HTTP requests. For development servers, this is handled
        automatically in a separate thread.
        """
        if IS_CIRCUITPYTHON and self.running and hasattr(self.adapter, 'server'):
            try:
                self.adapter.server.poll()
            except Exception as e:
                logger.error(e, "Error handling web server requests")
    
    def get_server_url(self):
        """
        Get the server URL
        
        Returns:
            Server URL string
        """
        if IS_CIRCUITPYTHON and self.wifi_manager:
            return f"http://{self.wifi_manager.esp.pretty_ip}"
        else:
            return "http://localhost:8080"
    
    def update_settings(self, new_settings):
        """
        Update settings and notify the core
        
        Args:
            new_settings: Dictionary of new settings
        """
        try:
            self.settings_manager.settings.update(new_settings)
            self.settings_manager.save_settings()
            logger.info("Settings updated via web server")
        except Exception as e:
            logger.error(e, "Error updating settings via web server")


# Compatibility functions for legacy code
def create_web_server(settings_manager, wifi_manager=None, ota_updater=None):
    """
    Create a web server instance (legacy compatibility function)
    
    Args:
        settings_manager: Settings manager instance
        wifi_manager: WiFi manager (required for CircuitPython)
        ota_updater: OTA updater instance (optional)
        
    Returns:
        UnifiedWebServer instance
    """
    return UnifiedWebServer(settings_manager, wifi_manager, ota_updater)


def start_web_server(settings_manager, wifi_manager=None, ota_updater=None, host=None, port=None):
    """
    Start a web server (legacy compatibility function)
    
    Args:
        settings_manager: Settings manager instance
        wifi_manager: WiFi manager (required for CircuitPython)
        ota_updater: OTA updater instance (optional)
        host: Host to bind to (optional)
        port: Port to bind to (optional)
        
    Returns:
        UnifiedWebServer instance if successful, None otherwise
    """
    server = create_web_server(settings_manager, wifi_manager, ota_updater)
    if server.start(host, port):
        return server
    else:
        return None