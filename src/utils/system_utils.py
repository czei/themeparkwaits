"""
System utilities for hardware and system operations.
Copyright 2024 3DUPFitters LLC
"""
import sys
import time
import asyncio

# Import hardware-specific modules or mock them
try:
    import rtc
    import microcontroller
    HAS_HARDWARE = True
except ModuleNotFoundError:
    # Mocking the unavailable modules in non-embedded environments
    from adafruit_datetime import datetime
    
    class rtc:
        class RTC:
            def __init__(self):
                self.datetime = datetime()
    
    HAS_HARDWARE = False

# Try to import adafruit_ntp, with fallback if not available
try:
    import adafruit_ntp
    HAS_NTP = True
except Exception:
    HAS_NTP = False


async def set_system_clock_ntp(socket_pool, tz_offset=None):
    """
    Set device time using NTP (Network Time Protocol)
    
    Args:
        socket_pool: SocketPool instance to use for NTP requests (must be actual socket pool, not HTTP client)
        tz_offset: Optional timezone offset in hours (defaults to US Eastern Time)
        
    Returns:
        True if successful, False otherwise
    """
    from src.utils.error_handler import ErrorHandler
    logger = ErrorHandler("error_log")

    if not HAS_NTP or not HAS_HARDWARE:
        logger.info("NTP module not available or hardware not supported")
        return False
        
    # Validate socket_pool is a proper socket pool object
    if socket_pool is None or not hasattr(socket_pool, 'getaddrinfo'):
        logger.error(None, "Invalid socket pool provided for NTP, socket pool must have getaddrinfo")
        return False
        
    try:
        # Timezone offset: default to EST (-5 hours)
        if tz_offset is None:
            tz_offset = -5
            
        # Create NTP client
        logger.info(f"Creating NTP client with server pool.ntp.org and tz_offset {tz_offset}")
        ntp = adafruit_ntp.NTP(socket_pool, server="pool.ntp.org", tz_offset=tz_offset)
        
        # Get the time
        logger.info("Getting time from NTP server")
        current_time = ntp.datetime
        
        # Convert to a tuple for the RTC module
        datetime_tuple = (
            current_time.tm_year,    # Year
            current_time.tm_mon,     # Month
            current_time.tm_mday,    # Day
            current_time.tm_hour,    # Hour
            current_time.tm_min,     # Minute
            current_time.tm_sec,     # Second
            current_time.tm_wday,    # Day of week (0-6)
            -1,                      # Day of year (not necessary)
            -1                       # DST flag (not necessary)
        )
        
        # Update the RTC
        rtc.RTC().datetime = datetime_tuple
        logger.info(f"System clock set to {datetime_tuple} via NTP")
        return True
        
    except Exception as e:
        logger.error(e, "Error setting time via NTP")
        return False
    
async def set_system_clock(http_client, socket_pool=None):
    """
    Set device time from the internet with multiple fallback options
    
    Args:
        http_client: The HTTP client to use for HTTP requests
        socket_pool: Optional socket pool for NTP (if available)
        
    Returns:
        A tuple representing the datetime that was set, or None if all attempts failed
    """
    from src.utils.error_handler import ErrorHandler
    logger = ErrorHandler("error_log")
    
    # First try NTP if available (more accurate)
    if HAS_NTP and socket_pool is not None:
        logger.info("Attempting to set time using NTP...")
        try:
            ntp_success = await set_system_clock_ntp(socket_pool)
            if ntp_success:
                logger.info("Successfully set system clock using NTP")
                return rtc.RTC().datetime
        except Exception as e:
            logger.error(e, "Failed to set time using NTP, falling back to HTTP methods")
    
    # Fall back to HTTP-based time APIs
    logger.info("Setting time using HTTP time APIs...")
    
    # Try multiple time API endpoints with fallbacks
    time_apis = [
        'http://worldtimeapi.org/api/timezone/America/New_York',
        'http://worldtimeapi.org/api/ip'  # Fallback to IP-based timezone
    ]
    
    datetime_object = None
    
    for api_url in time_apis:
        try:
            response = await http_client.get(api_url)
            
            # Skip failed requests
            if not hasattr(response, 'status_code') or response.status_code != 200:
                continue
                
            # Handle different API response formats
            if 'worldtimeapi.org' in api_url:
                try:
                    time_data = response.json()
                    
                    # Some responses might not have datetime field
                    if "datetime" not in time_data:
                        if "utc_datetime" in time_data:
                            date_string = time_data["utc_datetime"]
                        else:
                            continue
                    else:
                        date_string = time_data["datetime"]
                        
                    date_elements = date_string.split("T")
                    date = date_elements[0].split("-")
                    the_time = date_elements[1].split(".")
                    the_time = the_time[0].split(":")

                    # Pass elements to datetime constructor
                    datetime_object = (
                        int(date[0]),
                        int(date[1]),
                        int(date[2]),
                        int(the_time[0]),
                        int(the_time[1]),
                        int(the_time[2]),
                        -1,
                        -1,
                        -1
                    )
                    
                    # Success! Break out of retry loop
                    break
                    
                except (ValueError, KeyError, IndexError) as e:
                    # Continue to next API if JSON parsing fails
                    logger.error(e, f"Error parsing time API response")
                    continue
                    
        except Exception as e:
            # Continue to next API on any error
            logger.error(e, f"Error fetching time from {api_url}")
            continue
    
    # Set the clock if we got a valid time
    if datetime_object and HAS_HARDWARE:
        try:
            rtc.RTC().datetime = datetime_object
            logger.info(f"System clock set to {datetime_object}")
        except Exception as e:
            logger.error(e, "Error setting system clock")
    elif not datetime_object:
        logger.error(None, "Failed to set system clock - could not get time from any source")
        
    return datetime_object