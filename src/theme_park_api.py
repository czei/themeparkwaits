#
# Theme Park Waits
# View information about ride wait times at any theme park
# Copyright 2024 3DUPFitters LLC
#
import sys

# from production.ThemeParkAPI.src.themeparkwaits import settings

sys.path.append('/src/lib')

import asyncio
from adafruit_datetime import datetime
from src.color_utils import ColorUtils

import json
import time
from src.ErrorHandler import ErrorHandler
logger = ErrorHandler("error_log")

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
        # logger.debug(f"Params = {params}")
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

        # Some parks consist of Lands, some don't have lands at all,
        # and some have both.  We'll # try to parse all 3 kinds.
        lands_list = json_data["lands"]
        for land in lands_list:
            # logger.debug(f"Land = {land}")
            rides = land["rides"]
            for ride in rides:
                name = ride["name"]
                logger.debug(f"Ride = {name}")
                ride_id = ride["id"]
                wait_time = ride["wait_time"]
                open_flag = ride["is_open"]
                this_ride_object = ThemeParkRide(name, ride_id, wait_time, open_flag)
                if this_ride_object.is_open() is True:
                    self.is_open = True
                ride_list.append(this_ride_object)

        # Some parks dont' have lands, but we also want to avoid
        # double-counting
        # if len(lands_list) == 0:
        rides_not_in_a_land = json_data["rides"]
        for ride in rides_not_in_a_land:
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
                vac_message = f"Your vacation to {vac.name} is tomorrow!!!"
                self.add_scroll_message(vac_message, 0)
            elif days_until == 0:
                vac_message = f"Your vacation to {vac.name} is TODAY!!!!!!!!!!!!!"
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

        # Start with the park name
        self.func_queue.append(self.display.show_scroll_message)
        self.delay_queue.append(self.delay)
        self.param_queue.append(park.name + " wait times...")

        for ride in park.rides:
            await asyncio.sleep(0)
            if "Meet" in ride.name and park_list.skip_meet == True:
                logger.debug(f"Skipping character meet: {ride.name}")
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

        if self.settings.get("subscription_status") is None:
            self.settings[""] = "Unknown"
        if self.settings.get("email") is None:
            self.settings["email"] = ""
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
