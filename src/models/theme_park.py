"""
ThemePark model to represent a theme park with rides.
Copyright 2024 3DUPFitters LLC
"""

from src.models.theme_park_ride import ThemeParkRide
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


class ThemePark:
    """Represents a theme park with rides and wait times"""
    
    def __init__(self, json_data=(), name="", id=-1, latitude=0.0, longitude=0.0):
        """
        Initialize a theme park
        
        Args:
            json_data: Python JSON objects from a single park
            name: The name of the park
            id: The ID of the park
            latitude: The latitude coordinate of the park
            longitude: The longitude coordinate of the park
        """
        self.is_open = False
        self.counter = 0
        self.name = name
        self.id = id
        self.latitude = latitude
        self.longitude = longitude
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

    def get_url(self):
        """
        Get the URL for fetching this park's wait times
        
        Returns:
            URL string for the park's wait times data
        """
        url1 = "https://queue-times.com/parks/"
        url2 = "/queue_times.json"
        return url1 + str(self.id) + url2

    def _process_ride(self, ride_data):
        """
        Process a single ride's data into a ThemeParkRide object
        
        Args:
            ride_data: Dictionary containing ride information
            
        Returns:
            ThemeParkRide object
        """
        name = self.remove_non_ascii(ride_data["name"])
        ride_obj = ThemeParkRide(
            name,
            ride_data["id"],
            ride_data["wait_time"],
            ride_data["is_open"]
        )
        # Direct check instead of method call for performance
        if ride_data["is_open"]:
            self.is_open = True
        return ride_obj

    def get_rides_from_json(self, json_data):
        """
        Returns a list of rides at a particular park contained in the JSON
        
        Args:
            json_data: A JSON file containing data for a particular park
            
        Returns:
            List of ThemeParkRide objects
        """
        ride_list = []
        self.is_open = False

        # Early return for empty data
        if not json_data:
            return ride_list

        # Optimized: Process all rides regardless of structure
        try:
            # Process rides in lands (if they exist)
            lands = json_data.get("lands", [])
            for land in lands:
                land_rides = land.get("rides", [])
                for ride in land_rides:
                    ride_list.append(self._process_ride(ride))

            # Process rides not in lands (if they exist)
            # This handles parks without land structure
            direct_rides = json_data.get("rides", [])
            for ride in direct_rides:
                ride_list.append(self._process_ride(ride))
                
        except (KeyError, TypeError) as e:
            logger.error(e, "Error parsing theme park data")
            
        return ride_list

    def is_valid(self):
        """
        Check if this is a valid theme park object
        
        Returns:
            True if the theme park is valid, False otherwise
        """
        return self.id > 0

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