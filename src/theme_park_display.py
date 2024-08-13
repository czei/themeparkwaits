import asyncio
import time

import displayio
import terminalio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.label import Label

from src.color_utils import ColorUtils
from src.theme_park_api import logger


class Display:
    def __init__(self, sm):
        self.settings_manager = sm

    async def show_ride_closed(self, dummy):
        logger.info("Ride closed")

    async def show_ride_wait_time(self, ride_wait_time):
        logger.info(f"Ride wait time is {ride_wait_time}")

    async def show_configuration_message(self):
        logger.info(f"Showing configuration message")

    async def show_ride_name(self, ride_name):
        logger.info(f"Ride name is {ride_name}")

    async def show_scroll_message(self, message):
        logger.info(f"Scrolling message: {message}")

    def scroll_x(self, line):
        line.x = line.x - 1
        line_width = line.bounding_box[2]
        if line.x < -line_width:
            line.x = self.hardware.width
            return False
        return True

    def scroll_y(self, line, down=True):
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


class AsyncScrollingDisplay(Display):
    def __init__(self, display_hardware, sm):
        super().__init__(sm)
        self.font = terminalio.FONT
        self.hardware = display_hardware

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
        #Teeny-Tiny-Pixls-5.bdf
        self.centered_line1 = Label(terminalio.FONT, text="Test Line1")
            # bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
            # bitmap_font.load_font("src/fonts/Teeny-Tiny-Pixls-5.bdf"),
        #    text="Test Line1")
        self.centered_line2 = Label(terminalio.FONT, text="TEST LINE2")
            # bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
            # bitmap_font.load_font("src/fonts/Teeny-Tiny-Pixls-5.bdf"),
        self.centered_line1.x = 0
        self.centered_line1.y = 9
        self.centered_line2.x = 0
        self.centered_line2.y = 23
        self.centered_group = displayio.Group()
        self.centered_group.hidden = True
        self.centered_group.append(self.centered_line1)
        self.centered_group.append(self.centered_line2)
        scale = float(sm.settings["brightness_scale"])
        self.centered_line1.color = int(ColorUtils.scale_color(sm.settings["default_color"], scale))
        self.centered_line2.color = int(ColorUtils.scale_color(sm.settings["default_color"], scale))


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
        scale = float(settings.settings["brightness_scale"])
        logger.info(f"New brightness scale is: {scale}")
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
        self.scrolling_group.hidden = True
        self.wait_time_name_group.hidden = True
        self.wait_time_group.hidden = True
        self.closed_group.hidden = True
        self.splash_group.hidden = True
        self.update_group.hidden = True
        self.required_group.hidden = True
        self.centered_group.hidden = True

    async def show_ride_closed(self, dummy):
        await super().show_ride_closed(dummy)
        self.closed_group.hidden = False

    async def show_ride_wait_time(self, ride_wait_time):
        await super().show_ride_wait_time(ride_wait_time)
        self.wait_time.text = ride_wait_time
        self.center_time(self.wait_time)
        self.wait_time_group.hidden = False

    async def show_configuration_message(self):
        self.off()
        # self.wait_time_group.hidden = True
        # self.wait_time_name_group.hidden = True
        await super().show_configuration_message()

    async def show_splash(self, dummy):
        self.off()
        logger.debug("Showing the splash screen")
        self.splash_group.hidden = False
        await asyncio.sleep(4)
        self.splash_group.hidden = True

    async def show_centered(self,line1_text, line2_text, delay=0):
        """
        :param line1_text: The text for the first line of the centered screen
        :param line2_text: The text for the second line of the centered screen
        :param delay: The delay in seconds before hiding the centered screen
        :return: None

        The `show_centered` method displays a centered screen with two lines of text. It sets the text for the `line1_text` and `line2_text` parameters to the respective lines on the centered screen. It then centers the lines horizontally on the screen. The `delay` parameter determines how long the centered screen will be displayed before it is hidden.

        Example usage:

        show_centered("Hello", "Welcome!", 3)

        This will display a centered screen with the text "Hello" on the first line and "Welcome!" on the second line. The centered screen will remain visible for 3 seconds before it is hidden.
        """
        self.off()
        # logger.debug("Showing the centered screen")
        self.centered_line1.text = line1_text
        self.centered_line2.text = line2_text

        # Center lines
        self.centered_line1.x = self.center_line(self.centered_line1)
        self.centered_line2.x = self.center_line(self.centered_line2)
        self.centered_group.hidden = False

        # Give the user time to read the text before moving it
        time.sleep(1)

        scroll_amount1 = int((self.hardware.width - self.centered_line1.bounding_box[2]) / 2)
        scroll_amount2 = self.hardware.width - self.centered_line2.bounding_box[2]
        # logger.debug(f"Scroll amount 1: {scroll_amount1}")
        # logger.debug(f"Scroll amount 2: {scroll_amount2}")
        await self.scroll_line_to_end(self.centered_line1)
        await self.scroll_line_to_end(self.centered_line2)
        if delay is not 0:
            time.sleep(delay)
            self.centered_group.hidden = True

    async def scroll_line_to_end(self, line):
        scroll_amount = self.hardware.width - line.bounding_box[2]
        if scroll_amount < 0:
            for i in range(abs(scroll_amount)):
                await asyncio.sleep(.05)
                self.scroll_x(line)

    def center_line(self, line):
        line_width = line.bounding_box[2]
        padding = int((self.hardware.width - line_width) / 2)
        if padding < 0: padding = 0
        return padding

    async def show_update(self, on_flag):
        self.off()
        logger.debug("Showing the update screen")
        self.update_group.hidden = not on_flag

    async def show_required(self, on_flag):
        self.off()
        logger.debug("Showing the required screen")
        self.required_group.hidden = not on_flag

    async def show_ride_name(self, ride_name):
        await super().show_ride_name(ride_name)
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
        label_width = text_label.bounding_box[2]
        text_label.x = int(self.hardware.width / 2 - (label_width * len(text_label)))


class SimpleScrollingDisplay(Display):
    """
    This class uses the high level Adafruit text scrolling library that
    has very little functionality.  It is only used for pre-configuration
    help messages since later the more complex AsyncScrollingDisplay class
    will take over.
    """
    def __init__(self, mp, setting_manager, scrolldelay=0.03):
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
        logger.debug(f"Scrolling message: {message}")
        self.matrix_portal.set_text("", self.WAIT_TIME)
        self.matrix_portal.set_text(message, self.RIDE_NAME)
        self.matrix_portal.scroll_text(self.scroll_delay)
