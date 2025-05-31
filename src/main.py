"""
ThemeParkAPI - Main entry point
Copyright 2024 3DUPFitters LLC
"""
import sys

# Check if running on CircuitPython
is_circuitpython = hasattr(sys, 'implementation') and sys.implementation.name == 'circuitpython'

# Add src/lib to Python path if running on CircuitPython
if is_circuitpython and '/src/lib' not in sys.path:
    sys.path.append('/src/lib')

import asyncio

# Platform module is not available in CircuitPython, check environment first
if not is_circuitpython:
    import platform
    import argparse  # argparse is not available in CircuitPython

from src.app import ThemeParkApp
from src.utils.error_handler import ErrorHandler
from src.ui.display_factory import create_display, is_circuitpython, is_dev_mode

# Initialize logger
logger = ErrorHandler("error_log")

# Parse command line arguments
def parse_args():
    """Parse command line arguments"""
    # On CircuitPython, argparse is not available, so provide default args
    if is_circuitpython:
        class DefaultArgs:
            dev = False
        return DefaultArgs()
    
    # Standard Python environment with argparse
    parser = argparse.ArgumentParser(description="Theme Park API")
    parser.add_argument('--dev', action='store_true', help='Run in development mode with display simulator')
    return parser.parse_args()

# Initialize ThemeParkApp and run it
async def main():
    # Parse command line arguments
    try:
        args = parse_args()
    except Exception as e:
        # If we can't parse arguments, assume defaults (may happen in CircuitPython)
        logger.warning(f"Unable to parse command line arguments: {e}")
        class DefaultArgs:
            dev = False
        args = DefaultArgs()
    
    try:
        # Create a settings manager
        from src.config.settings_manager import SettingsManager
        settings_manager = SettingsManager("settings.json")
        
        # Create display using the factory (will automatically choose simulator or hardware)
        if not is_circuitpython:
            logger.info(f"Creating display for platform: {platform.system()}")
        else:
            logger.info("Creating display for platform: CircuitPython")
        display = create_display({'settings_manager': settings_manager})
        
        # Initialize the display
        if not display.initialize():
            logger.error(None, "Failed to initialize display")
            return
        
        # Set up networking based on platform
        if is_circuitpython() and not is_dev_mode():
            # For CircuitPython hardware
            import wifi
            import mdns
            from src.network.http_client import HttpClient
            
            # Configure mDNS for hostname resolution
            # Use domain_name from settings (with fallback to "themeparkwaits" if not set)
            hostname = settings_manager.settings.get("domain_name", "themeparkwaits")
            
            try:
                mdns_server = mdns.Server(wifi.radio)
                mdns_server.hostname = hostname
                mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=80)
                logger.info(f"Advertising mDNS hostname: {hostname}.local")
            except Exception as e:
                logger.error(e, "Failed to set up mDNS")
            
            # Create HTTP client without initializing session yet
            http_client = HttpClient()
            
        else:
            # For non-hardware testing or dev mode
            from src.network.http_client import HttpClient
            
            # Create HTTP client
            http_client = HttpClient()
            
            # Set up special handling for simulator display
            if is_dev_mode():
                # Create a background task to update the simulator display
                asyncio.create_task(display.run_async())
                
        # Create app instance
        logger.debug(f"Display implementation type: {type(display)}")
        app = ThemeParkApp(display, http_client, settings_manager)
        
        # Run the app
        await app.run()
        
    except Exception as e:
        logger.error(e, "Error in main application")
        
# Run the main function
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, Exception) as e:
        logger.error(e, "Application terminated")