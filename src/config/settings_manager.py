"""
Settings manager for handling user configuration.
Copyright 2024 3DUPFitters LLC
"""
import json

from src.utils.error_handler import ErrorHandler
from src.utils.color_utils import ColorUtils

# Initialize logger
logger = ErrorHandler("error_log")


class SettingsManager:
    """
    Manages application settings with persistence to a JSON file
    """
    
    def __init__(self, filename):
        """
        Initialize the settings manager
        
        Args:
            filename: The name of the settings file
        """
        self.filename = filename
        self.settings = self.load_settings()
        self.scroll_speed = {"Slow": 0.06, "Medium": 0.04, "Fast": 0.02}

        # Set default settings if not present
        if self.settings.get("subscription_status") is None:
            self.settings["subscription_status"] = "Unknown"
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
        if self.settings.get("display_mode") is None:
            self.settings["display_mode"] = "all_rides"
        if self.settings.get("sort_mode") is None:
            self.settings["sort_mode"] = "alphabetical"
        if self.settings.get("group_by_park") is None:
            self.settings["group_by_park"] = False

    def get_scroll_speed(self):
        """
        Get the scroll speed based on the current setting
        
        Returns:
            The scroll speed in seconds per pixel
        """
        return self.scroll_speed[self.settings["scroll_speed"]]

    @staticmethod
    def get_pretty_name(settings_name):
        """
        Convert a settings key to a display-friendly name
        
        Args:
            settings_name: The settings key
            
        Returns:
            A display-friendly name
        """
        # Change underscore to spaces
        new_name = settings_name.replace("_", " ")
        return " ".join(word[0].upper() + word[1:] for word in new_name.split(' '))

    def load_settings(self):
        """
        Load settings from the settings file
        
        Returns:
            A dictionary of settings
        """
        logger.info(f"Loading settings {self.filename}")
        try:
            with open(self.filename, 'r') as f:
                return json.load(f)
        except OSError:
            return {}

    def save_settings(self):
        """Save settings to the settings file"""
        logger.info(f"Saving settings {self.filename}")
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.settings, f)
        except OSError as e:
            logger.error(e, f"Error saving settings to {self.filename}")
            
    def get(self, key, default=None):
        """
        Get a setting by key with a default value
        
        Args:
            key: The settings key
            default: The default value if the key is not found
            
        Returns:
            The setting value, or the default if not found
        """
        value = self.settings.get(key, default)
        
        # Special handling for boolean settings that might be stored as strings
        # This can happen with CircuitPython's JSON parser
        if key in ["group_by_park", "skip_closed", "skip_meet"] and isinstance(value, str):
            return value.lower() == "true"
            
        return value
        
    def set(self, key, value):
        """
        Set a setting by key
        
        Args:
            key: The settings key
            value: The value to set
        """
        self.settings[key] = value