"""
Timer utility for tracking elapsed time.
Copyright 2024 3DUPFitters LLC
"""
import time


class Timer:
    """Simple timer class for tracking elapsed time"""
    
    def __init__(self, time_to_wait):
        """
        Initialize a timer
        
        Args:
            time_to_wait: The amount of time to wait in seconds
        """
        self.target_length = time_to_wait
        self.start_time = time.monotonic()
        self.forced_expiry = False

    def finished(self):
        """
        Check if the timer has finished
        
        Returns:
            True if the time has elapsed or was forced to expire, False otherwise
        """
        if self.forced_expiry:
            return True
            
        return (time.monotonic() - self.start_time) > self.target_length

    def reset(self, expired=False):
        """
        Reset the timer to start counting from now
        
        Args:
            expired: If True, force the timer to report as expired
        """
        self.start_time = time.monotonic()
        self.forced_expiry = expired
        
    def remaining(self):
        """
        Get the remaining time in seconds
        
        Returns:
            The remaining time in seconds, or 0 if the timer has finished
        """
        if self.forced_expiry:
            return 0
            
        remaining = self.target_length - (time.monotonic() - self.start_time)
        return max(0, remaining)