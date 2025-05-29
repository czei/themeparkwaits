"""
Base display classes for theme park wait time display.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import time

from src.config.settings_manager import SettingsManager
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


class Display:
    """Base display class for all display implementations"""
    
    def __init__(self, settings_manager):
        """
        Initialize the display
        
        Args:
            settings_manager: The settings manager
        """
        self.settings_manager = settings_manager
        
        # Create a default settings object if none is provided
        if self.settings_manager is None:
            self.settings_manager = SettingsManager("settings.json")
        
    def initialize(self):
        """
        Initialize the display - base implementation just returns True
        
        Returns:
            True if initialization was successful, False otherwise
        """
        logger.info("Base display initialize method called")
        return True
        
    def set_colors(self, settings):
        """
        Set colors from settings (base implementation does nothing)
        
        Args:
            settings: The settings manager
        """
        pass

    async def show_splash(self, duration=8, reveal_style=False):
        """
        Show the splash screen
        
        Args:
            duration: Duration to show splash screen in seconds (default: 4)
            reveal_style: If True, use reveal animation (ignored in base implementation)
        """
        logger.info(f"Showing splash screen for {duration} seconds")
        await asyncio.sleep(duration)
        
    async def show_ride_closed(self, dummy):
        """
        Show that a ride is closed
        
        Args:
            dummy: Unused parameter for API consistency
        """
        logger.info("Ride closed")

    async def show_ride_wait_time(self, ride_wait_time):
        """
        Show a ride's wait time
        
        Args:
            ride_wait_time: The wait time to display
        """
        logger.info(f"Ride wait time is {ride_wait_time}")

    async def show_configuration_message(self):
        """Show a configuration message"""
        logger.info(f"Showing configuration message")

    async def show_ride_name(self, ride_name):
        """
        Show a ride's name
        
        Args:
            ride_name: The name of the ride to display
        """
        logger.info(f"Ride name is {ride_name}")

    async def show_scroll_message(self, message):
        """
        Show a scrolling message
        
        Args:
            message: The message to scroll
        """
        logger.info(f"Scrolling message: {message}")

    def scroll_x(self, line):
        """
        Scroll a line horizontally
        
        Args:
            line: The line to scroll
            
        Returns:
            True if still scrolling, False if done
        """
        line.x = line.x - 1
        line_width = line.bounding_box[2]
        if line.x < -line_width:
            line.x = self.hardware.width
            return False
        return True

    def scroll_y(self, line, down= True):
        """
        Scroll a line vertically
        
        Args:
            line: The line to scroll
            down: True to scroll down, False to scroll up
            
        Returns:
            True if still scrolling, False if done
        """
        orig_y = line.y
        if down is True:
            line.y = line.y - line.bounding_box[1]
        else:
            line.y = line.y + line.bounding_box[1]
        while line.y != orig_y:
            if down is True:
                line.y = line.y - 1
            else:
                line.y = line.y + 1

        line_height = line.bounding_box[1]
        if line.y < -line_height:
            line.y = self.hardware.height
            return False
        return True


class DisplayStyle:
    """
    Defines display style constants
    Mostly static or scrolling, but could expand in the future
    """

    SCROLLING = 0
    STATIC = 1