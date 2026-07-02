"""
ThemePark model to represent a theme park with rides.
Copyright (c) 2024-2026 Michael Czeiszperger
"""

from src.models.theme_park_ride import ThemeParkRide
from scrollkit.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


class ThemePark:
    """Represents a theme park with rides and wait times"""
    
    def __init__(self, json_data=(), name="", id=-1):
        """
        Initialize a theme park

        Args:
            json_data: Parsed /entity/{id}/live response for a single park
            name: The name of the park
            id: The themeparks.wiki id (UUID string) of the park
        """
        self.is_open = False
        self.counter = 0
        self.name = name
        self.id = id
        self.destination_name = ""  # resort/destination, for FR-005a disambiguation
        self.rides = self.get_rides_from_json(json_data)

    @staticmethod
    def remove_non_ascii(orig_str):
        """
        Removes non-ascii characters from the data feed assigned
        park names that includes foreign languages.
        
        Args:
            orig_str: The original string that might contain non-ASCII characters
            
        Returns:
            A string with only ASCII characters
        """
        # Optimized: Use list comprehension with join for better performance
        # on both short and long strings
        chars = []
        for c in orig_str:
            if ord(c) < 128:
                chars.append(c)
        return ''.join(chars)

    @staticmethod
    def _standby_wait(item):
        """Standby wait minutes from a live entity, 0 if none.

        ``queue``/``STANDBY``/``waitTime`` may be absent OR present-but-null (the
        API marks several queue waits nullable), so this is a null-safe coercion,
        not a key-presence check.
        """
        queue = item.get("queue")
        standby = queue.get("STANDBY") if isinstance(queue, dict) else None
        w = standby.get("waitTime") if isinstance(standby, dict) else None
        try:
            return int(w) if w is not None else 0
        except (TypeError, ValueError):
            return 0

    def _process_ride(self, item):
        """
        Process a single live ATTRACTION entity into a ThemeParkRide object

        Args:
            item: A ``liveData`` entity dict from /entity/{id}/live

        Returns:
            ThemeParkRide object
        """
        name = self.remove_non_ascii(item.get("name", ""))
        open_flag = item.get("status") == "OPERATING"
        ride_obj = ThemeParkRide(name, item.get("id"), self._standby_wait(item), open_flag)
        if open_flag:
            self.is_open = True
        return ride_obj

    def get_rides_from_json(self, json_data):
        """
        Returns the list of attraction rides from a themeparks.wiki live payload.

        Reads ``liveData`` and keeps only ``entityType == "ATTRACTION"`` entities
        (shows, restaurants, hotels, and the PARK entity are skipped). Maps
        ``status == "OPERATING"`` to open and ``queue.STANDBY.waitTime`` to the wait.

        Args:
            json_data: Parsed /entity/{id}/live response for a single park

        Returns:
            List of ThemeParkRide objects
        """
        ride_list = []
        self.is_open = False

        # Early return for empty data
        if not json_data:
            return ride_list

        try:
            for item in json_data.get("liveData", []):
                if not isinstance(item, dict):
                    continue
                if item.get("entityType") != "ATTRACTION":
                    continue
                ride_list.append(self._process_ride(item))
        except (KeyError, TypeError, AttributeError) as e:
            # AttributeError guards against a malformed payload where liveData (or a
            # nested queue) is a non-dict — never crash on bad data (FR-016).
            logger.error(e, "Error parsing theme park data")

        return ride_list

    def is_valid(self):
        """
        Check if this is a valid theme park object

        Returns:
            True if the theme park has a (non-empty, non-sentinel) id
        """
        return bool(self.id) and self.id != -1

    def set_rides(self, ride_json):
        """
        Set the rides for this theme park from JSON data
        
        Args:
            ride_json: JSON data containing ride information
        """
        self.rides = self.get_rides_from_json(ride_json)
        self.counter = 0

    def get_wait_time(self, ride_name):
        """
        Get the wait time for a specific ride
        
        Args:
            ride_name: The name of the ride
            
        Returns:
            The wait time in minutes, or 0 if the ride is not found
        """
        for ride in self.rides:
            if ride.name == ride_name:
                return ride.wait_time
        return 0

    def is_ride_open(self, ride_name):
        """
        Check if a specific ride is open
        
        Args:
            ride_name: The name of the ride
            
        Returns:
            True if the ride is open, False otherwise or if not found
        """
        for ride in self.rides:
            if ride.name == ride_name:
                return ride.open_flag
        return False

    def increment(self):
        """Increment the ride counter, cycling back to 0 if at the end"""
        self.counter += 1
        if self.counter >= len(self.rides):
            self.counter = 0

    def update(self, json_data):
        """
        Update the rides from new JSON data
        
        Args:
            json_data: New JSON data for the park
        """
        self.rides = self.get_rides_from_json(json_data)

    def get_current_ride_name(self):
        """
        Get the name of the current ride
        
        Returns:
            The name of the current ride
        """
        if not self.rides:
            return ""
        return self.rides[self.counter].name

    def is_current_ride_open(self):
        """
        Check if the current ride is open
        
        Returns:
            True if the current ride is open, False otherwise
        """
        if not self.rides:
            return False
        return self.rides[self.counter].open_flag

    def get_current_ride_time(self):
        """
        Get the wait time for the current ride
        
        Returns:
            The wait time in minutes for the current ride
        """
        if not self.rides:
            return 0
        return self.rides[self.counter].wait_time

    def get_next_ride_name(self):
        """
        Get the name of the next ride
        
        Returns:
            The name of the next ride
        """
        self.increment()
        if not self.rides:
            return ""
        return self.rides[self.counter].name

    def get_num_rides(self):
        """
        Get the number of rides in this park
        
        Returns:
            The number of rides
        """
        return len(self.rides)

    def change_parks(self, new_name, new_id):
        """
        Change to a different park
        
        Args:
            new_name: The name of the new park
            new_id: The ID of the new park
        """
        self.name = new_name
        self.id = new_id
        self.counter = 0