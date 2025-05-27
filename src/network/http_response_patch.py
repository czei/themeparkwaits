"""
Patch for Adafruit HTTP Response to handle connection errors more gracefully.
Copyright 2024 3DUPFitters LLC
"""
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")

def apply_http_response_patch():
    """
    Apply patches to the adafruit_httpserver Response class to make it more
    robust against client disconnection errors.
    
    This should be called at the start of the app before using the web server.
    """
    try:
        from adafruit_httpserver.response import Response
        
        # Save original methods
        original_send_bytes = Response._send_bytes
        original_send_headers = Response._send_headers
        
        # Create enhanced version of _send_bytes with better error handling
        def enhanced_send_bytes(self, data):
            """Enhanced _send_bytes method with better error handling for disconnections"""
            try:
                return original_send_bytes(self, data)
            except (BrokenPipeError, OSError) as e:
                # These errors are common when client disconnects prematurely
                # Just log and return quietly instead of crashing
                if isinstance(e, BrokenPipeError) or (hasattr(e, 'args') and e.args and e.args[0] in (32, 104)):
                    logger.debug(f"Client disconnected during response: {type(e).__name__}")
                else:
                    logger.error(e, f"Error sending response: {type(e).__name__}")
                return 0  # Indicate no bytes sent
        
        # Create enhanced version of _send_headers that can handle argument mismatches
        def enhanced_send_headers(self, *args):
            """Enhanced _send_headers method with better argument handling"""
            try:
                # The original function might expect a different number of arguments
                # Check if it's being called with more arguments than it can handle
                if len(args) > 2:  # If we have more than expected args
                    logger.debug(f"Adjusting arguments for _send_headers call")
                    # Call with just the first 2 arguments (self is already bound)
                    return original_send_headers(self, args[0], args[1])
                else:
                    # Call normally if the argument count matches
                    return original_send_headers(self, *args)
            except TypeError as te:
                # If there's still a TypeError, log it and try a safer approach
                logger.error(te, f"TypeError in _send_headers, trying fallback approach")
                try:
                    # Try calling with just self (minimum required)
                    return original_send_headers(self)
                except Exception as e2:
                    logger.error(e2, "Fallback approach failed")
                    return 0
            except (BrokenPipeError, OSError) as e:
                # Handle connection errors gracefully
                if isinstance(e, BrokenPipeError) or (hasattr(e, 'args') and e.args and e.args[0] in (32, 104)):
                    logger.debug(f"Client disconnected during headers: {type(e).__name__}")
                else:
                    logger.error(e, f"Error sending headers: {type(e).__name__}")
                return 0
        
        # Replace the methods
        Response._send_bytes = enhanced_send_bytes
        Response._send_headers = enhanced_send_headers
        
        logger.info("HTTP response patch applied successfully")
        return True
    except Exception as e:
        # If patching fails, log error but continue
        logger.error(e, "Failed to apply HTTP response patch")
        return False