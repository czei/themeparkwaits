"""
Concrete display implementations for Theme Park API.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import time

import displayio
import terminalio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.label import Label

from src.ui.display_base import Display
from src.utils.color_utils import ColorUtils
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


class AsyncScrollingDisplay(Display):
    """
    Display implementation using asyncio for smooth scrolling
    """
    
    def __init__(self, display_hardware, settings_manager):
        """
        Initialize the display
        
        Args:
            display_hardware: The display hardware to use
            settings_manager: The settings manager
        """
        super().__init__(settings_manager)
        self.font = terminalio.FONT
        self.hardware = display_hardware
        # Make settings available to be used by MessageQueue
        self.settings_manager = settings_manager

        self.main_group = displayio.Group()
        self.hardware.root_group = self.main_group
        self.main_group.hidden = False

        # Configure generic scrolling message
        self.scrolling_label = Label(terminalio.FONT)
        self.scrolling_label.x = 0
        self.scrolling_label.y = 15
        self.scrolling_group = displayio.Group()
        self.scrolling_group.append(self.scrolling_label)
        self.scrolling_group.hidden = True

        # Configure Ride Times
        self.wait_time_name = Label(terminalio.FONT)
        self.wait_time_name.x = 0
        self.wait_time_name.y = 7
        self.wait_time_name.scale = 1
        self.wait_time_name_group = displayio.Group()
        self.wait_time_name_group.append(self.wait_time_name)
        self.wait_time_name_group.hidden = True

        self.wait_time = Label(terminalio.FONT)
        self.wait_time.x = 0
        self.wait_time.y = 22
        self.wait_time.scale = (2)
        self.wait_time_group = displayio.Group()
        self.wait_time_group.append(self.wait_time)
        self.wait_time_group.hidden = True

        self.closed = Label(terminalio.FONT)
        self.closed.x = 14
        self.closed.y = 22
        self.closed.scale = (1)
        self.closed.text = "Closed"
        self.closed_group = displayio.Group()
        self.closed_group.hidden = True
        self.closed_group.append(self.closed)

        # Main Splash Screen
        self.splash_line1 = Label(
            terminalio.FONT,
            text="THEME PARK")
        self.splash_line1.x = self.hardware.width
        self.splash_line1.x = 2
        self.splash_line1.y = 7
        self.splash_line2 = Label(
            terminalio.FONT,
            text="WAITS",
            scale=2)
        self.splash_line2.x = 3
        self.splash_line2.y = 22
        self.splash_group = displayio.Group()
        self.splash_group.hidden = True
        self.splash_group.append(self.splash_line1)
        self.splash_group.append(self.splash_line2)
        self.splash_line1.color = int(ColorUtils.colors["Yellow"])
        self.splash_line2.color = int(ColorUtils.colors["Orange"])

        # Message to show when wait times are updating
        self.update_line1 = Label(
            terminalio.FONT,
            text="Wait Times")
        self.update_line1.x = 2
        self.update_line1.y = 10
        self.update_line2 = Label(
            terminalio.FONT,
            text="Powered By",
            scale=1)
        self.update_line2.x = 2
        self.update_line2.y = 22
        self.update_group = displayio.Group()
        self.update_group.hidden = True
        self.update_group.append(self.update_line1)
        self.update_group.append(self.update_line2)
        self.update_line1.color = int(ColorUtils.colors["Yellow"])
        self.update_line2.color = int(ColorUtils.colors["Yellow"])

        # Message to show when wait times are updating
        self.required_line1 = Label(
            bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
            text="QUEUE-TIMES.COM")
        self.required_line2 = Label(
            bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
            text="UPDATING NOW")
        self.required_line1.x = 3
        self.required_line1.y = 12
        self.required_line2.x = 8
        self.required_line2.y = 20
        self.required_group = displayio.Group()
        self.required_group.hidden = True
        self.required_group.append(self.required_line1)
        self.required_group.append(self.required_line2)
        self.required_line1.color = int(ColorUtils.colors["Yellow"])
        self.required_line2.color = int(ColorUtils.colors["Yellow"])

        # Centered generic messages
        self.centered_line1 = Label(terminalio.FONT, text="Test Line1")
        self.centered_line2 = Label(terminalio.FONT, text="TEST LINE2")
        self.centered_line1.x = 0
        self.centered_line1.y = 9
        self.centered_line2.x = 0
        self.centered_line2.y = 23
        self.centered_group = displayio.Group()
        self.centered_group.hidden = True
        self.centered_group.append(self.centered_line1)
        self.centered_group.append(self.centered_line2)
        
        # Set default colors if settings_manager exists
        if settings_manager:
            scale = float(settings_manager.settings["brightness_scale"])
            self.centered_line1.color = int(ColorUtils.scale_color(settings_manager.settings["default_color"], scale))
            self.centered_line2.color = int(ColorUtils.scale_color(settings_manager.settings["default_color"], scale))

        self.queue_line1 = Label(
            terminalio.FONT,
            text="Powered by")
        self.queue_line1.color = int(ColorUtils.colors["Yellow"])
        self.queue_line1.x = 0
        self.queue_line1.y = 10

        self.queue_line2 = Label(
            bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
            text="queue-times.com")
        self.queue_line2.color = int(ColorUtils.colors["Orange"])
        self.queue_line2.x = 1
        self.queue_line2.y = 25
        self.queue_group = displayio.Group()
        self.queue_group.hidden = True
        self.queue_group.append(self.queue_line1)
        self.queue_group.append(self.queue_line2)

        # Add all groups to the main group
        self.main_group.append(self.scrolling_group)
        self.main_group.append(self.wait_time_name_group)
        self.main_group.append(self.wait_time_group)
        self.main_group.append(self.closed_group)
        self.main_group.append(self.splash_group)
        self.main_group.append(self.update_group)
        self.main_group.append(self.required_group)
        self.main_group.append(self.centered_group)
        self.main_group.append(self.queue_group)

    def set_colors(self, settings):
        """
        Set colors from settings
        
        Args:
            settings: The settings manager
        """
        scale = float(settings.settings["brightness_scale"])
        logger.info(f"New brightness scale is{scale}")
        self.wait_time_name.color = int(ColorUtils.scale_color(settings.settings["ride_name_color"], scale))
        self.wait_time.color = int(ColorUtils.scale_color(settings.settings["ride_wait_time_color"], scale))
        self.closed.color = int(ColorUtils.scale_color(settings.settings["ride_wait_time_color"], scale))
        self.scrolling_label.color = int(ColorUtils.scale_color(settings.settings["default_color"], scale))
        self.splash_line1.color = int(ColorUtils.scale_color(ColorUtils.colors["Yellow"], scale))
        self.splash_line2.color = int(ColorUtils.scale_color(ColorUtils.colors["Orange"], scale))
        self.update_line1.color = int(ColorUtils.scale_color(settings.settings["default_color"], scale))
        self.update_line2.color = int(ColorUtils.scale_color(settings.settings["default_color"], scale))
        self.required_line1.color = int(ColorUtils.scale_color(settings.settings["default_color"], scale))
        self.required_line2.color = int(ColorUtils.scale_color(settings.settings["default_color"], scale))
        self.centered_line1.color = int(ColorUtils.scale_color(settings.settings["default_color"], scale))
        self.centered_line2.color = int(ColorUtils.scale_color(settings.settings["default_color"], scale))

    def off(self):
        """Turn off all display elements"""
        self.scrolling_group.hidden = True
        self.wait_time_name_group.hidden = True
        self.wait_time_group.hidden = True
        self.closed_group.hidden = True
        self.splash_group.hidden = True
        self.update_group.hidden = True
        self.required_group.hidden = True
        self.centered_group.hidden = True

    async def show_splash(self, duration=4):
        """
        Show the splash screen
        
        Args:
            duration: Duration to show splash screen in seconds (default: 4)
        """
        self.off()
        logger.debug(f"Showing the splash screen for {duration} seconds")
        self.splash_group.hidden = False
        await asyncio.sleep(duration)
        self.splash_group.hidden = True

    async def show_ride_closed(self, dummy):
        """
        Show that a ride is closed
        
        Args:
            dummy: Unused parameter for API consistency
        """
        await super().show_ride_closed(dummy)
        # Hide other displays but keep ride name visible if already shown
        self.scrolling_group.hidden = True
        self.wait_time_group.hidden = True
        self.splash_group.hidden = True
        self.update_group.hidden = True
        self.required_group.hidden = True
        self.centered_group.hidden = True
        
        self.closed_group.hidden = False

    async def show_ride_wait_time(self, ride_wait_time):
        """
        Show a ride's wait time
        
        Args:
            ride_wait_time: The wait time to display
        """
        await super().show_ride_wait_time(ride_wait_time)
        # Hide other displays but keep ride name visible if already shown
        self.scrolling_group.hidden = True
        self.closed_group.hidden = True
        self.splash_group.hidden = True
        self.update_group.hidden = True
        self.required_group.hidden = True
        self.centered_group.hidden = True
        
        self.wait_time.text = ride_wait_time
        self.center_time(self.wait_time)
        self.wait_time_group.hidden = False

    async def show_configuration_message(self):
        """Show a configuration message"""
        self.off()
        await super().show_configuration_message()

    async def show_centered(self, line1_text, line2_text, delay=0):
        """
        Show centered text
        
        Args:
            line1_text: Text for the first line
            line2_text: Text for the second line
            delay: Delay before hiding (0=don't hide)
        """
        self.off()
        # Convert inputs to strings to prevent AttributeError with find()
        self.centered_line1.text = str(line1_text) if line1_text is not None else ""
        self.centered_line2.text = str(line2_text) if line2_text is not None else ""

        # Center lines
        self.centered_line1.x = self.center_line(self.centered_line1)
        self.centered_line2.x = self.center_line(self.centered_line2)
        self.centered_group.hidden = False

        # Give the user time to read the text before moving it
        time.sleep(1)

        scroll_amount1 = int((self.hardware.width - self.centered_line1.bounding_box[2]) / 2)
        scroll_amount2 = self.hardware.width - self.centered_line2.bounding_box[2]
        
        await self.scroll_line_to_end(self.centered_line1)
        await self.scroll_line_to_end(self.centered_line2)
        
        if delay != 0:
            time.sleep(delay)
            self.centered_group.hidden = True

    async def scroll_line_to_end(self, line):
        """
        Scroll a line to the end of the display
        
        Args:
            line: The line to scroll
        """
        scroll_amount = self.hardware.width - line.bounding_box[2]
        if scroll_amount < 0:
            for i in range(abs(scroll_amount)):
                await asyncio.sleep(.05)
                self.scroll_x(line)

    def center_line(self, line):
        """
        Calculate the x position to center a line
        
        Args:
            line: The line to center
            
        Returns:
            The x position for centering
        """
        line_width = line.bounding_box[2]
        padding = int((self.hardware.width - line_width) / 2)
        if padding < 0: padding = 0
        return padding

    async def show_update(self, on_flag):
        """
        Show the update screen
        
        Args:
            on_flag: Whether to show or hide the screen
        """
        self.off()
        logger.debug("Showing the update screen")
        self.update_group.hidden = not on_flag

    async def show_required(self, on_flag):
        """
        Show the required attribution screen
        
        Args:
            on_flag: Whether to show or hide the screen
        """
        self.off()
        logger.debug("Showing the required screen")
        self.required_group.hidden = not on_flag

    async def show_ride_name(self, ride_name):
        """
        Show a ride's name
        
        Args:
            ride_name: The name of the ride to display
        """
        await super().show_ride_name(ride_name)
        # Hide other displays but keep wait time visible if already shown
        self.scrolling_group.hidden = True
        self.splash_group.hidden = True
        self.update_group.hidden = True
        self.required_group.hidden = True
        self.centered_group.hidden = True
        # Don't hide closed_group here since it might be showing "Closed" status
        
        await asyncio.sleep(.5)
        self.wait_time_name.text = ride_name
        self.wait_time_name_group.hidden = False
        while self.scroll_x(self.wait_time_name) is True:
            await asyncio.sleep(self.settings_manager.get_scroll_speed())
        await asyncio.sleep(1)
        self.wait_time.text = ""
        self.wait_time_name.text = ""
        self.wait_time_group.hidden = True
        self.wait_time_name_group.hidden = True
        self.closed_group.hidden = True

    async def show_scroll_message(self, message):
        """
        Show a scrolling message
        
        Args:
            message: The message to scroll
        """
        logger.debug(f"Scrolling message: {message}")
        self.splash_group.hidden = True
        self.wait_time_group.hidden = True
        self.wait_time_name_group.hidden = True
        self.scrolling_label.text = message
        self.scrolling_group.hidden = False
        await asyncio.sleep(.5)

        while self.scroll_x(self.scrolling_label) is True:
            await asyncio.sleep(self.settings_manager.get_scroll_speed())
            self.hardware.refresh(minimum_frames_per_second=0)

        self.scrolling_group.hidden = True

    def center_time(self, text_label):
        """
        Center a time display
        
        Args:
            text_label: The label to center
        """
        label_width = text_label.bounding_box[2]
        text_label.x = int(self.hardware.width / 2 - (label_width * len(text_label)))


class SimpleScrollingDisplay(Display):
    """
    This class uses the high level Adafruit text scrolling library that
    has very little functionality. It is only used for pre-configuration
    help messages since later the more complex AsyncScrollingDisplay class
    will take over.
    """
    def __init__(self, mp, setting_manager, scrolldelay=0.03):
        """
        Initialize the display
        
        Args:
            mp: The MatrixPortal instance
            setting_manager: The settings manager
            scrolldelay: The delay between scroll steps
        """
        super().__init__(setting_manager)

        self.matrix_portal = mp
        self.scroll_delay = scrolldelay

        self.WAIT_TIME = 0
        self.matrix_portal.add_text(
            text_font=terminalio.FONT,
            text_position=(
                23,
                int(self.matrix_portal.graphics.display.height * 0.75) - 2,
            ),
            text_color=ColorUtils.colors["Yellow"],
            scrolling=False,
            text_scale=2,
        )

        # Ride Name
        self.RIDE_NAME = 1
        self.matrix_portal.add_text(
            text_font=terminalio.FONT,
            text_position=(
                0,
                int(self.matrix_portal.graphics.display.height * 0.25) + 10,
            ),
            text_color=ColorUtils.colors["Yellow"],
            scrolling=True,
            text_scale=1,
        )

    def show_scroll_message(self, message):
        """
        Show a scrolling message
        
        Args:
            message: The message to scroll
        """
        logger.debug(f"Scrolling message{message}")
        self.matrix_portal.set_text("", self.WAIT_TIME)
        self.matrix_portal.set_text(message, self.RIDE_NAME)
        self.matrix_portal.scroll_text(self.scroll_delay)