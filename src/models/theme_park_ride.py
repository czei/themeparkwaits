"""
ThemeParkRide model to represent a ride at a theme park.
Copyright (c) 2024-2026 Michael Czeiszperger
"""


class ThemeParkRide:
    """Represents a ride at a theme park with wait time information"""
    
    def __init__(self, name, new_id, wait_time, open_flag):
        """
        Initialize a new theme park ride
        
        Args:
            name: The name of the ride
            new_id: The ID of the ride (a themeparks.wiki UUID string)
            wait_time: The current standby wait time in minutes
            open_flag: Whether the ride is currently operating
        """
        self.name = name
        self.id = new_id
        self.wait_time = wait_time
        self.open_flag = open_flag

    def is_open(self):
        """
        The listings will often mark a ride as "open" when its obvious
        after hours and the park is closed, but the wait time will be zero.
        Because of this discrepancy we have to check both.
        
        Returns:
            True if the ride is open, False otherwise
        """
        return self.open_flag is True and self.wait_time > 0