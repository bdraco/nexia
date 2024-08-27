"""Top-level package for Nexia."""
from __future__ import annotations

__version__ = "0.1.0"

BRAND_NEXIA = "nexia"
BRAND_ASAIR = "asair"
BRAND_TRANE = "trane"

NEXIA_ROOT_URL = "https://www.mynexia.com"
NEXIA_IDENTIFIER = "com.tranetechnologies.nexia"
ASAIR_ROOT_URL = "https://asairhome.com"
ASAIR_IDENTIFIER = "com.tranetechnologies.asair"
TRANE_ROOT_URL = "https://www.tranehome.com"
TRANE_IDENTIFIER = "com.tranetechnologies.trane"

MOBILE_URL_TEMPLATE = "{}/mobile"

DEFAULT_DEVICE_NAME = "Home Automation"

PUT_UPDATE_DELAY = 0.5

HOLD_PERMANENT = "permanent_hold"
HOLD_RESUME_SCHEDULE = "run_schedule"

OPERATION_MODE_AUTO = "AUTO"
OPERATION_MODE_COOL = "COOL"
OPERATION_MODE_HEAT = "HEAT"
OPERATION_MODE_OFF = "OFF"
OPERATION_MODES = [
    OPERATION_MODE_AUTO,
    OPERATION_MODE_COOL,
    OPERATION_MODE_HEAT,
    OPERATION_MODE_OFF,
]

# The order of these is important as it maps to preset#
PRESET_MODE_HOME = "Home"
PRESET_MODE_AWAY = "Away"
PRESET_MODE_SLEEP = "Sleep"
PRESET_MODE_NONE = "None"

SYSTEM_STATUS_COOL = "Cooling"
SYSTEM_STATUS_HEAT = "Heating"
SYSTEM_STATUS_WAIT = "Waiting..."
SYSTEM_STATUS_IDLE = "System Idle"
SYSTEM_STATUS_OFF = "System Off"

BLOWER_OFF_STATUSES = {SYSTEM_STATUS_WAIT, SYSTEM_STATUS_IDLE, SYSTEM_STATUS_OFF}

AIR_CLEANER_MODE_AUTO = "auto"
AIR_CLEANER_MODE_QUICK = "quick"
AIR_CLEANER_MODE_ALLERGY = "allergy"
AIR_CLEANER_MODES = [
    AIR_CLEANER_MODE_AUTO,
    AIR_CLEANER_MODE_QUICK,
    AIR_CLEANER_MODE_ALLERGY,
]

HUMIDITY_MIN = 0.35
HUMIDITY_MAX = 0.65

APP_VERSION = "6.0.0"

UNIT_CELSIUS = "C"
UNIT_FAHRENHEIT = "F"

DAMPER_CLOSED = "Damper Closed"
DAMPER_OPEN = "Damper Open"

ZONE_IDLE = "Idle"

ALL_IDS = "all"
