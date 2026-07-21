"""
ThemeParkList model to manage a collection of theme parks.
Copyright (c) 2024-2026 Michael Czeiszperger
"""

from scrollkit.utils.error_handler import ErrorHandler
from src.models.theme_park import ThemePark

# Initialize logger
logger = ErrorHandler("error_log")


class ThemeParkList:
    """
    The ThemeParkList class is used to manage a list of ThemePark objects.
    It provides various utility methods to interact with, and retrieve data from the list.
    """

    def __init__(self, json_response):
        """
        Initialize a list of theme parks from a themeparks.wiki /destinations payload

        Args:
            json_response: parsed ``/v1/destinations`` response
                ``{"destinations": [{"name", "parks": [{"id", "name"}]}]}``
        """
        self.park_list = []
        self.current_park = ThemePark()  # Keep for backward compatibility
        self.selected_parks = []  # list of up to 4 selected parks
        self.skip_meet = False
        self.skip_closed = False

        # Handle empty or invalid JSON response
        if not json_response:
            logger.error(None, "Empty JSON response when initializing ThemeParkList")
            return

        try:
            destinations = json_response.get("destinations", []) if isinstance(json_response, dict) else []
            for dest in destinations:
                if not isinstance(dest, dict):
                    continue
                dest_name = ThemePark.remove_non_ascii(dest.get("name", ""))
                for item in dest.get("parks", []):
                    if not isinstance(item, dict):
                        continue
                    park_id = item.get("id")
                    name = item.get("name")
                    # Only add parks with valid names and IDs (UUID strings)
                    if name and park_id:
                        park = ThemePark("", ThemePark.remove_non_ascii(name), park_id)
                        # Carry the destination/resort name for disambiguating
                        # duplicate park names in the config UI (FR-005a).
                        park.destination_name = dest_name
                        self.park_list.append(park)

            # Sort park list alphabetically
            if self.park_list:
                self.park_list = sorted(self.park_list, key=lambda park: park.name)
                logger.debug(f"Initialized ThemeParkList with {len(self.park_list)} parks")
            else:
                logger.error(None, "No parks found in JSON response")
        except Exception as e:
            logger.error(e, "Error parsing JSON in ThemeParkList initialization")
            # Keep the empty park list

    @staticmethod
    def _is_legacy_id(pid):
        """True for a pre-UUID park id — a positive legacy integer or an
        all-digit/non-hyphenated string. themeparks.wiki ids are hyphenated UUID
        strings; the app's own ``-1`` sentinel and empty/blank values are NOT
        legacy (they just mean "no selection")."""
        if isinstance(pid, bool):
            return False
        if isinstance(pid, int):
            return pid > 0          # real legacy ids were positive; -1 is our sentinel
        if isinstance(pid, str):
            return bool(pid) and "-" not in pid   # e.g. "6"; "" / a UUID are not legacy
        return False

    def _migrate_legacy_selection(self, sm):
        """Clear-on-upgrade: pre-UUID integer park ids are not valid themeparks.wiki
        UUIDs, so on the first run after the update we drop any legacy selection and
        let the user re-select (FR-019, SC-006). Clears the relevant keys in place;
        ``load_settings`` then proceeds normally and finds nothing selected.
        """
        ids = sm.settings.get("selected_park_ids", []) or []
        legacy = any(self._is_legacy_id(pid) for pid in ids)
        # Also catch a legacy single-park id when there is no selected_park_ids list.
        if not ids and "current_park_id" in sm.settings:
            legacy = self._is_legacy_id(sm.settings.get("current_park_id"))
        if not legacy:
            return
        logger.info("Clearing legacy (pre-UUID) park selection on upgrade")
        for key in ("selected_park_ids", "selected_park_names",
                    "current_park_id", "current_park_name"):
            sm.settings.pop(key, None)
        try:
            sm.save_settings()
        except Exception as e:
            logger.error(e, "Failed to persist cleared legacy selection")

    def load_settings(self, sm):
        """
        Load settings from the settings manager

        Args:
            sm: The settings manager
        """
        # One-time upgrade migration: drop legacy (pre-UUID) integer ids (FR-019).
        # Clears in place, then loading proceeds normally (the cleared keys are gone,
        # so no park ends up selected, but skip_meet/skip_closed still load below).
        self._migrate_legacy_selection(sm)

        keys = sm.settings.keys()

        # Load multiple selected parks
        if "selected_park_ids" in keys:
            park_ids = sm.settings["selected_park_ids"]
            self.selected_parks = []
            for park_id in park_ids:
                park = self.get_park_by_id(park_id)
                if park:
                    self.selected_parks.append(park)
            # Set current_park to first selected park for backward compatibility
            if self.selected_parks:
                self.current_park = self.selected_parks[0]
        # Fallback to legacy single park setting
        elif "current_park_id" in keys:
            park_id = sm.settings["current_park_id"]
            park = self.get_park_by_id(park_id)
            if park:
                self.current_park = park
                self.selected_parks = [park]
                
        if "skip_meet" in keys:
            self.skip_meet = sm.settings["skip_meet"]
        if "skip_closed" in keys:
            self.skip_closed = sm.settings["skip_closed"]

    def get_park_by_id(self, park_id):
        """
        Find a park by its ID
        
        Args:
            park_id: The ID of the park
            
        Returns:
            The ThemePark with the given ID, or None if not found
        """
        for park in self.park_list:
            if park.id == park_id:
                return park
        return None

