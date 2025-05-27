"""
Vacation model to represent a vacation plan.
Copyright 2024 3DUPFitters LLC
"""
from adafruit_datetime import datetime

from src.utils.error_handler import ErrorHandler
from src.config.settings_manager import SettingsManager
from src.utils.url_utils import url_decode

# Initialize logger
logger = ErrorHandler("error_log")


class Vacation:
    """Represents a vacation plan with date information"""
    
    def __init__(self, park_name= "", year= 0, month= 0, day= 0):
        """
        Initialize a vacation plan
        
        Args:
            park_name: The name of the park to visit
            year: The year of the vacation
            month: The month of the vacation
            day: The day of the vacation
        """
        self.name = park_name
        self.year = year
        self.month = month
        self.day = day

    def print(self):
        """Print the vacation details to the console"""
        print(f"Vacation{self.name}, {self.year}, {self.month}, {self.day}, isset={self.is_set()}")

    def parse(self, str_params):
        """
        Parse vacation parameters from a URL query string
        
        Args:
            str_params: The URL query string
        """
        params = str_params.split("&")
        for param in params:
            name_value = param.split("=")
            if name_value[0] == "Name":
                self.name = url_decode(name_value[1])
            if name_value[0] == "Year":
                self.year = int(name_value[1])
            if name_value[0] == "Month":
                self.month = int(name_value[1])
            if name_value[0] == "Day":
                self.day = int(name_value[1])

    def get_days_until(self):
        """
        Calculate the number of days until the vacation
        
        Returns:
            The number of days until the vacation
        """
        today = datetime.now()
        logger.info(f"The current year is {today.year}")
        future = datetime(self.year, self.month, self.day)
        diff = future - today
        return diff.days + 1

    def is_set(self):
        """
        Check if the vacation is properly set
        
        Returns:
            True if the vacation is set, False otherwise
        """
        if len(self.name) > 0 and self.year > 1999 and self.month > 0 and self.day > 0:
            return True
        return False

    def store_settings(self, sm):
        """
        Store vacation settings in the settings manager
        
        Args:
            sm: The settings manager
        """
        sm.settings["next_visit"] = self.name
        sm.settings["next_visit_year"] = self.year
        sm.settings["next_visit_month"] = self.month
        sm.settings["next_visit_day"] = self.day

    def load_settings(self, sm):
        """
        Load vacation settings from the settings manager
        
        Args:
            sm: The settings manager
        """
        if "next_visit" in sm.settings.keys():
            self.name = sm.settings.get("next_visit")
        if "next_visit_year" in sm.settings.keys():
            self.year = sm.settings.get("next_visit_year")
        if "next_visit_month" in sm.settings.keys():
            self.month = sm.settings.get("next_visit_month")
        if "next_visit_day" in sm.settings.keys():
            self.day = sm.settings.get("next_visit_day")