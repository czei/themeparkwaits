"""Application settings schema for ThemeParkWaits.

Centralizes the app's default settings + boolean keys, applied on top of the
library's ``scrollkit.config.SettingsManager`` (which already defaults
``brightness_scale`` and ``scroll_speed`` and provides ``get_scroll_speed()``).

``use_prerelease`` was removed with the move to the public-branch OTA model
(there is no prerelease channel under raw-content fetching — see
specs/001-this-project-is/contracts/ota-release.md).

Copyright 2024 3DUPFitters LLC
"""
from scrollkit.config.settings_manager import SettingsManager
from scrollkit.utils.color_utils import ColorUtils

# App-specific defaults (the library already supplies brightness_scale + scroll_speed).
DEFAULTS = {
    "subscription_status": "Unknown",
    "email": "",
    "domain_name": "themeparkwaits",
    "brightness_scale": "0.5",
    "skip_closed": False,
    "skip_meet": False,
    "default_color": ColorUtils.colors["Yellow"],
    "ride_name_color": ColorUtils.colors["Blue"],
    "ride_wait_time_color": ColorUtils.colors["Old Lace"],
    "scroll_speed": "Medium",
    "wait_time_effect": "Rain",
    "display_mode": "all_rides",
    "sort_mode": "alphabetical",
    "group_by_park": False,
    # themeparks.wiki park ids are UUID strings (e.g. "75ea578a-..."); legacy
    # integer ids from the old source are cleared on upgrade (see
    # ThemeParkList._migrate_legacy_selection).
    "selected_park_ids": [],
}

# Keys CircuitPython's JSON parser may store as strings; SettingsManager.get()
# coerces these back to bool.
BOOL_KEYS = ["skip_closed", "skip_meet", "group_by_park"]

DEFAULT_SETTINGS_FILE = "settings.json"


def make_settings(filename=DEFAULT_SETTINGS_FILE):
    """Build the app's SettingsManager with defaults + boolean keys applied."""
    return SettingsManager(filename, defaults=DEFAULTS, bool_keys=BOOL_KEYS)
