#
# Theme Park Waits
# View information about ride wait times at any theme park
# Copyright 2024 3DUPFitters LLC
#
import sys

sys.path.append('/src/lib')

import asyncio
import displayio
import terminalio
from adafruit_datetime import datetime
from adafruit_display_text.label import Label
from src.color_utils import ColorUtils
import json
import time
from adafruit_bitmap_font import bitmap_font

import adafruit_logging as logging

logger = logging.getLogger('Test')
# logger.setLevel(logging.ERROR)  # Use DEBUG for testing
logger.setLevel(logging.DEBUG)  # Use DEBUG for testing

try:
    logger.addHandler(logging.FileHandler("error_log"))
except OSError:
    print("Read-only file system")

try:
    import rtc
    import microcontroller
except ModuleNotFoundError:
    # Mocking the unavailable modules in non-embedded environments
    # You can add more according to your needs, these are just placeholders
    class rtc:
        class RTC:
            def __init__(self):
                self.datetime = datetime()


#'Red': '0xcc3333',

def set_system_clock(http_requests):
    # Set device time from the internet
    response = http_requests.get(
        'http://worldtimeapi.org/api/timezone/America/New_York')
    time_data = response.json()
    date_string = time_data["datetime"]
    date_elements = date_string.split("T")
    date = date_elements[0].split("-")
    the_time = date_elements[1].split(".")
    the_time = the_time[0].split(":")

    # Pass elements to datetime constructor
    #            int(float(offset)*1000000)
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

    logger.info(f"Setting the time to {datetime_object}")
    rtc.RTC().datetime = datetime_object
    return datetime_object


class ThemeParkList:
    '''
    The ThemeParkList class is used to manage a list of ThemePark objects.
    It provides various utility methods to interact with, and retrieve data from the list.
    '''

    def __init__(self, json_response):
        self.park_list = []
        self.current_park = ThemePark()
        self.skip_meet = False
        self.skip_closed = False

        for company in json_response:
            for parks in company:
                if parks == "parks":
                    park = company[parks]
                    name = ""
                    park_id = 0
                    latitude = 0
                    longitude = 0
                    for item in park:
                        # logger.debug(f"park = {item}")
                        for element in item:
                            if element == "name":
                                name = item[element]
                            if element == "id":
                                park_id = item[element]
                            if element == "latitude":
                                latitude = item[element]
                            if element == "longitude":
                                longitude = item[element]
                        park = ThemePark("", ThemePark.remove_non_ascii(name), park_id, latitude, longitude)
                        self.park_list.append(park)

        sorted_park_list = sorted(self.park_list, key=lambda park: park.name)
        self.park_list = sorted_park_list

    @staticmethod
    def get_park_url_from_id(self, park_id):
        url1 = "https://queue-times.com/parks/"
        url2 = "/queue_times.json"
        return url1 + str(park_id) + url2

    def load_settings(self, sm):

        keys = sm.settings.keys()

        if "current_park_id" in keys:
            id = sm.settings["current_park_id"]
            park = self.get_park_by_id(id)
            self.current_park = park
        if "skip_meet" in keys:
            self.skip_meet = sm.settings["skip_meet"]
        if "skip_closed" in keys:
            self.skip_closed = sm.settings["skip_closed"]

    def get_park_url_from_name(self, park_name):
        """
        Takes the output from get_theme_parks_from_json and assembles
        the URL to get individual ride data.
        :param park_list: A list of tuples of park names and ids
        :param park_name: The string describing the Theme Park
        :return: JSON url for a particular theme park
        """
        # Magic Kingdom URL example: https://queue-times.com/parks/6/queue_times.json
        url1 = "https://queue-times.com/parks/"
        url2 = "/queue_times.json"
        for park in self.park_list:
            if park.name == park_name:
                park_id = park.id
                url = url1 + str(park_id) + url2
                return url

    def get_park_by_id(self, id):
        for park in self.park_list:
            if park.id == id:
                return park

    def get_park_location_from_id(self, park_id):
        """
        Takes the output from get_theme_parks_from_json and assembles
        the URL to get individual ride data.
        :param park_id: The id from QueueTimes.com
        :return: JSON url for a particular theme park
        """
        # Magic Kingdom URL example: https://queue-times.com/parks/6/queue_times.json
        for park in self.park_list:
            if park.id == park_id:
                return park.latitude, park.longitude

    def get_park_name_from_id(self, park_id):
        park_name = ""
        for park in self.park_list:
            if park.id == park_id:
                park_name = park.name
                return park_name

    def parse(self, str_params):
        params = str_params.split("&")
        logger.debug(f"Params = {params}")
        self.skip_meet = False
        self.skip_closed = False
        for param in params:
            name_value = param.split("=")
            if name_value[0] == "park-id":
                self.current_park = self.get_park_by_id(int(name_value[1]))
                logger.debug(f"New park name = {self.current_park.name}")
                logger.debug(f"New park id = {self.current_park.id}")
                logger.debug(f"New park latitude = {self.current_park.latitude}")
                logger.debug(f"New park longitude = {self.current_park.longitude}")
            if name_value[0] == "skip_closed":
                logger.debug("Skip closed is True")
                self.skip_closed = True
            if name_value[0] == "skip_meet":
                logger.debug("Skip meet is True")
                self.skip_meet = True

    def store_settings(self, sm):
        sm.settings["current_park_name"] = self.current_park.name
        sm.settings["current_park_id"] = self.current_park.id
        sm.settings["skip_meet"] = self.skip_meet
        sm.settings["skip_closed"] = self.skip_closed


class ThemeParkRide:
    def __init__(self, name, new_id, wait_time, open_flag):
        self.name = name
        self.id = new_id
        self.wait_time = wait_time
        self.open_flag = open_flag

    def is_open(self):
        """
        The listings will often mark a ride as "open" when its obvious
        after hours and the park is closed, but the wait time will be zero.
        Because of this discrepancy we have to check both.
        :return:
        """
        return self.open_flag is True and self.wait_time > 0
        # return self.open_flag


class ThemePark:
    def __init__(self, json_data=(), name="", id=-1, latitude=0.0, longitude=0.0):
        """
        :param self:
        :param json_data: Python JSON objects from a single park
        :return:
        """
        self.is_open = False
        self.counter = 0
        self.name = name
        self.id = id
        self.latitude = latitude
        self.longitude = longitude
        self.rides = self.get_rides_from_json(json_data)
        #self.skip_meet = False
        #self.skip_closed = False

    @staticmethod
    def remove_non_ascii(orig_str):
        """
        Removes non-ascii characters from the data feed assigned
        park names that includes foreign languages.
        """
        new_str = ""
        for c in orig_str:
            if ord(c) < 128:
                new_str += c
        return new_str

    def get_url(self):
        url1 = "https://queue-times.com/parks/"
        url2 = "/queue_times.json"
        return url1 + str(self.id) + url2

    def get_rides_from_json(self, json_data):
        """
        Returns a list of the names of rides at a particular park contained in the JSON
        :param json_data: A JSON file containing data for a particular park
        :return: name, id, wait_time, open_flag
        """
        ride_list = []
        self.is_open = False

        # logger.debug(f"Json_data is: {json_data}")
        if len(json_data) <= 0:
            return ride_list

        # Some parks consist of Lands, and some don't.  We'll
        # try to parse both.
        lands_list = json_data["lands"]
        for land in lands_list:
            rides = land["rides"]
            for ride in rides:
                name = ride["name"]
                # logger.debug(f"Ride = {name}")
                ride_id = ride["id"]
                wait_time = ride["wait_time"]
                open_flag = ride["is_open"]
                this_ride_object = ThemeParkRide(name, ride_id, wait_time, open_flag)
                if this_ride_object.is_open() is True:
                    self.is_open = True
                ride_list.append(this_ride_object)

        # Some parks dont' have lands, but we also want to avoid
        # double-counting
        if len(lands_list) == 0:
            rides_list = json_data["rides"]
            for ride in rides_list:
                name = ride["name"]
                ride_id = ride["id"]
                wait_time = ride["wait_time"]
                open_flag = ride["is_open"]
                this_ride_object = ThemeParkRide(name, ride_id, wait_time, open_flag)
                if this_ride_object.is_open() is True:
                    self.is_open = True
                ride_list.append(this_ride_object)

        return ride_list

    def is_valid(self):
        return self.id > 0

    def set_rides(self, ride_json):
        self.rides = self.get_rides_from_json(ride_json)
        self.counter = 0

    def get_wait_time(self, ride_name):
        for ride in self.rides:
            if ride.name == ride_name:
                return ride.wait_time

    def is_ride_open(self, ride_name):
        for ride in self.rides:
            if ride.name == ride_name:
                return ride.open_flag

    def increment(self):
        self.counter += 1
        if self.counter >= len(self.rides):
            self.counter = 0

    def update(self, json_data):
        self.rides = self.get_rides_from_json(json_data)

    def get_current_ride_name(self):
        return self.rides[self.counter].name

    def is_current_ride_open(self):
        if self.rides[self.counter].open_flag is False:
            return False
        else:
            return True

    def get_current_ride_time(self):
        return self.rides[self.counter].wait_time

    def get_next_ride_name(self):
        self.increment()
        return self.rides[self.counter].name

    def get_num_rides(self):
        return len(self.rides)

    def change_parks(self, new_name, new_id):
        self.name = new_name
        self.id = new_id
        self.counter = 0


class ThemeParkIterator:
    def __init__(self, park):
        """
        :param self:
        :return:
        """
        self.park = park


class DisplayStyle:
    """
    Mostly static or scrolling, but could expand in the future
    """

    def __init__(self):
        self.SCROLLING = 0
        self.STATIC = 1


class Vacation:
    def __init__(self, park_name="", year=0, month=0, day=0):
        self.name = park_name
        self.year = year
        self.month = month
        self.day = day

    def print(self):
        print(f"Vacation: {self.name}, {self.year}, {self.month}, {self.day}, isset={self.is_set()}")

    def parse(self, str_params):
        params = str_params.split("&")
        for param in params:
            name_value = param.split("=")
            if name_value[0] == "Name":
                #self.name = str(name_value[1]).replace("+", " ")
                self.name = url_decode(name_value[1])
            if name_value[0] == "Year":
                self.year = int(name_value[1])
            if name_value[0] == "Month":
                self.month = int(name_value[1])
            if name_value[0] == "Day":
                self.day = int(name_value[1])

    def get_days_until(self):
        today = datetime.now()
        logger.info(f"The current year is {today.year}")
        future = datetime(self.year, self.month, self.day)
        diff = future - today
        return diff.days + 1

    def is_set(self):
        if len(self.name) > 0 and self.year > 1999 and self.month > 0 and self.day > 0:
            return True

        return False

    def store_settings(self, sm):
        sm.settings["next_visit"] = self.name
        sm.settings["next_visit_year"] = self.year
        sm.settings["next_visit_month"] = self.month
        sm.settings["next_visit_day"] = self.day

    def load_settings(self, sm):
        if "next_visit" in sm.settings.keys():
            self.name = sm.settings.get("next_visit")
        if "next_visit_year" in sm.settings.keys():
            self.year = sm.settings.get("next_visit_year")
        if "next_visit_month" in sm.settings.keys():
            self.month = sm.settings.get("next_visit_month")
        if "next_visit_day" in sm.settings.keys():
            self.day = sm.settings.get("next_visit_day")


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


class AsyncScrollingDisplay(Display):
    def __init__(self, display_hardware, sm):
        super().__init__(sm)
        self.font = terminalio.FONT
        self.hardware = display_hardware

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
            text="queue-times.com")
        self.required_line2 = Label(
            bitmap_font.load_font("src/fonts/tom-thumb.bdf"),
            text="Updating Now")
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

        self.main_group = displayio.Group()
        self.main_group.hidden = False
        self.main_group.append(self.scrolling_group)
        self.main_group.append(self.wait_time_name_group)
        self.main_group.append(self.wait_time_group)
        self.main_group.append(self.closed_group)
        self.main_group.append(self.splash_group)
        self.main_group.append(self.update_group)
        self.main_group.append(self.required_group)
        self.main_group.append(self.queue_group)
        self.hardware.root_group = self.main_group

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

    async def off(self):
        self.scrolling_group.hidden = True
        self.wait_time_name_group.hidden = True
        self.wait_time_group.hidden = True
        self.closed_group.hidden = True
        self.splash_group.hidden = True
        self.update_group.hidden = True
        self.required_group.hidden = True

    async def show_ride_closed(self, dummy):
        await super().show_ride_closed(dummy)
        self.closed_group.hidden = False

    async def show_ride_wait_time(self, ride_wait_time):
        await super().show_ride_wait_time(ride_wait_time)
        self.wait_time.text = ride_wait_time
        self.center_time(self.wait_time)
        self.wait_time_group.hidden = False

    async def show_configuration_message(self):
        await self.off()
        # self.wait_time_group.hidden = True
        # self.wait_time_name_group.hidden = True
        await super().show_configuration_message()

    async def show_splash(self, dummy):
        await self.off()
        logger.debug("Showing the splash screen")
        self.splash_group.hidden = False
        await asyncio.sleep(4)
        self.splash_group.hidden = True

    async def show_update(self, on_flag):
        await self.off()
        logger.debug("Showing the update screen")
        self.update_group.hidden = not on_flag

    async def show_required(self, on_flag):
        await self.off()
        logger.debug("Showing the update screen")
        self.required_group.hidden = not on_flag

    async def show_ride_name(self, ride_name):
        # await self.off()
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

    def center_time(self, text_label):
        label_width = text_label.bounding_box[2]
        text_label.x = int(self.hardware.width / 2 - (label_width * len(text_label)))


class MatrixPortalDisplay(Display):
    def __init__(self, mp, setting_manager, scrolldelay=0.03):
        super().__init__(setting_manager)
        # super().__init__(scrolldelay)

        self.matrix_portal = mp
        self.scroll_delay = scrolldelay

        self.WAIT_TIME = 0
        self.matrix_portal.add_text(
            text_font=terminalio.FONT,
            text_position=(
                23,
                int(self.matrix_portal.graphics.display.height * 0.75) - 2,
            ),
            text_color=ColorUtils.colors["Blue"],
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
            text_color=ColorUtils.colors["Red"],
            scrolling=True,
            text_scale=1,
        )

        # Standby
        self.STANDBY = 2
        self.matrix_portal.add_text(
            text_font=terminalio.FONT,
            text_position=(
                (int((self.matrix_portal.graphics.display.width - 7 * 6) / 2)),
                6,
            ),
            text_color=ColorUtils.colors["Blue"]
        )

    async def show_ride_closed(self, dummy):
        self.matrix_portal.set_text("Closed", self.STANDBY)

    async def show_ride_wait_time(self, ride_wait_time):
        self.matrix_portal.set_text("", self.RIDE_NAME)
        self.matrix_portal.set_text(ride_wait_time, self.WAIT_TIME)
        self.matrix_portal.set_text("Standby", self.STANDBY)

    async def show_configuration_message(self):
        self.matrix_portal.set_text("", self.STANDBY)
        self.matrix_portal.set_text("", self.WAIT_TIME)
        self.matrix_portal.set_text(f"Configure at http://{self.settings_manager.settings["domain_name"]}.local",
                                    self.RIDE_NAME)
        self.matrix_portal.scroll_text(self.scroll_delay)
        self.matrix_portal.set_text(f"http://", self.RIDE_NAME)
        self.matrix_portal.scroll_text(self.scroll_delay)

    async def show_ride_name(self, ride_name):
        self.matrix_portal.set_text("", self.STANDBY)
        self.matrix_portal.set_text("", self.WAIT_TIME)
        self.matrix_portal.set_text(ride_name, self.RIDE_NAME)
        self.matrix_portal.scroll_text(self.scroll_delay)

    async def show_scroll_message(self, message):
        logger.debug(f"Scrolling message: {message}")
        self.matrix_portal.set_text("", self.STANDBY)
        self.matrix_portal.set_text("", self.WAIT_TIME)
        self.matrix_portal.set_text(message, self.RIDE_NAME)
        self.matrix_portal.scroll_text(self.scroll_delay)

    def sync_show_scroll_message(self, message):
        logger.debug(f"Scrolling message: {message}")
        self.matrix_portal.set_text("", self.STANDBY)
        self.matrix_portal.set_text("", self.WAIT_TIME)
        self.matrix_portal.set_text(message, self.RIDE_NAME)
        self.matrix_portal.scroll_text(self.scroll_delay)


REQUIRED_MESSAGE = "queue-times.com"


#  The things to display on the screen
class MessageQueue:
    def __init__(self, d, delay_param=4, regen_flag=False):
        self.display = d
        self.delay = delay_param
        self.regenerate_flag = regen_flag
        self.init()

    def add_scroll_message(self, the_message, delay=2):
        self.func_queue.append(self.display.show_scroll_message)
        self.param_queue.append(the_message)
        self.delay_queue.append(delay)

    async def add_splash(self, delay):
        logger.debug("Adding splash message to queue")
        self.func_queue.append(self.display.show_splash)
        self.param_queue.append("")
        self.delay_queue.append(delay)

    def init(self):
        self.func_queue = []
        self.param_queue = []
        self.delay_queue = []
        self.index = 0

    async def add_vacation(self, vac):
        if vac.is_set() is True:
            days_until = vac.get_days_until()
            if days_until > 1:
                vac_message = f"Vacation to {vac.name} in: {days_until} days"
                self.add_scroll_message(vac_message, 0)
            elif days_until == 1:
                vac_message = f"Your vacation to {vac.name} is tomorrow!!!!!!!!!!!!!"
                self.add_scroll_message(vac_message, 0)

    async def add_required_message(self, parkName):
        self.func_queue.append(self.display.show_scroll_message)
        required_message = f"Wait times for {parkName} provided by {REQUIRED_MESSAGE}"
        self.param_queue.append(required_message)
        self.delay_queue.append(self.delay)

    async def add_rides(self, park_list):
        park = park_list.current_park
        logger.debug(f"MessageQueue.add_rides() called for: {park.name}:{park.id}")

        if park.is_open is False:
            self.func_queue.append(self.display.show_scroll_message)
            self.delay_queue.append(self.delay)
            self.param_queue.append(park.name + " is closed")
            return

        for ride in park.rides:
            await asyncio.sleep(0)
            if "Meet" in ride.name and park_list.skip_meet == True:
                logger.info(f"Skipping character meet: {ride.name}")
                continue

            if ride.is_open() is False and park_list.skip_closed == True:
                continue

            if ride.open_flag is True:
                self.func_queue.append(self.display.show_ride_wait_time)
                self.param_queue.append(str(ride.wait_time))
                self.delay_queue.append(0)
            else:
                self.func_queue.append(self.display.show_ride_closed)
                self.param_queue.append("Closed")
                self.delay_queue.append(0)

            self.func_queue.append(self.display.show_ride_name)
            self.param_queue.append(ride.name)
            self.delay_queue.append(self.delay)

            self.regenerate_flag = False

    async def show(self):
        await asyncio.create_task(
            self.func_queue[self.index](self.param_queue[self.index]))
        await asyncio.sleep(self.delay_queue[self.index])
        self.index += 1
        if self.index >= len(self.func_queue):
            self.index = 0


# Can't get dataclasses to work on MatrixPortal S3.
# Saving to JSON by hand.
# @dataclasses.dataclass
class SettingsManager:
    def __init__(self, filename):
        self.filename = filename
        self.settings = self.load_settings()
        self.scroll_speed = {"Slow": 0.06, "Medium": 0.04, "Fast": 0.02}

        if self.settings.get("domain_name") is None:
            self.settings["domain_name"] = "themeparkwaits"
        if self.settings.get("brightness_scale") is None:
            self.settings["brightness_scale"] = "0.5"
        if self.settings.get("skip_closed") is None:
            self.settings["skip_closed"] = False
        if self.settings.get("skip_meet") is None:
            self.settings["skip_meet"] = False
        if self.settings.get("default_color") is None:
            self.settings["default_color"] = ColorUtils.colors["Yellow"]
        if self.settings.get("ride_name_color") is None:
            self.settings["ride_name_color"] = ColorUtils.colors["Blue"]
        if self.settings.get("ride_wait_time_color") is None:
            self.settings["ride_wait_time_color"] = ColorUtils.colors["Old Lace"]
        if self.settings.get("scroll_speed") is None:
            self.settings["scroll_speed"] = "Medium"

        # Features not implemented yet
        # if self.settings.get("park_name_color") is None:
        #    self.settings["park_name_color"] = ColorUtils.colors["Blue"]
        # if self.settings.get("vacation_color") is None:
        #    self.settings["vacation_color"] = ColorUtils.colors["Red"]

    def get_scroll_speed(self):
        return self.scroll_speed[self.settings["scroll_speed"]]

    @staticmethod
    def get_pretty_name(settings_name):
        # Change underscore to spaces
        new_name = settings_name.replace("_", " ")
        return " ".join(word[0].upper() + word[1:] for word in new_name.split(' '))

    def load_settings(self):
        logger.info(f"Loading settings {self.filename}")
        try:
            with open(self.filename, 'r') as f:
                return json.load(f)
        except OSError:
            return {}

    def save_settings(self):
        logger.info(f"Saving settings {self.filename}")
        with open(self.filename, 'w') as f:
            json.dump(self.settings, f)


def load_credentials():
    try:
        from secrets import secrets
        return secrets['ssid'], secrets['password']
    except ImportError:
        return "", ""


def url_decode(input_string):
    input_string = input_string.replace('+', ' ')
    hex_chars = "0123456789abcdef"
    result = ""
    i = 0
    while i < len(input_string):
        if input_string[i] == "%" and i < len(input_string) - 2:
            hex_value = input_string[i + 1:i + 3].lower()
            if all(c in hex_chars for c in hex_value):
                result += chr(int(hex_value, 16))
                i += 3
                continue
        result += input_string[i]
        i += 1
    return result


class Timer:
    def __init__(self, time_to_wait):
        self.target_length = time_to_wait
        self.start_time = time.monotonic()

    def finished(self):
        return (time.monotonic() - self.start_time) > self.target_length

    def reset(self):
        self.start_time = time.monotonic()
