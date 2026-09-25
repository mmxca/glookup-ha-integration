"""Constants for the Glooko integration."""

from __future__ import annotations

DOMAIN = "glooko"

CONF_REGION = "region"
CONF_DEVICE_ID = "device_id"
CONF_SERIAL = "serial_number"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_STALE_MINUTES = "stale_minutes"
CONF_SYNC_TRIGGER = "sync_trigger_minutes"

DEFAULT_REGION = "us"
DEFAULT_SCAN_INTERVAL = 10  # minutes
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 60
DEFAULT_STALE_MINUTES = 120
STATS_REFRESH_MINUTES = 60
# Web sign-in makes Glooko pull from the pump cloud (ON_DEMAND). 0 disables.
DEFAULT_SYNC_TRIGGER = 30
MIN_SYNC_TRIGGER = 15  # Glooko's post-sync cooldown measured at ~12 min
MAX_SYNC_TRIGGER = 240
SYNC_REFRESH_DELAY = 90  # seconds to wait before re-polling after a trigger

# Glooko API hosts per region (web dashboard uses the same backend).
REGIONS: dict[str, str] = {
    "us": "https://us.api.glooko.com",
    "eu": "https://eu.api.glooko.com",
    "ca": "https://ca.api.glooko.com",
    "de-fr": "https://de-fr.api.glooko.com",
}
WEB_ORIGINS: dict[str, str] = {
    "us": "https://us.my.glooko.com",
    "eu": "https://eu.my.glooko.com",
    "ca": "https://ca.my.glooko.com",
    "de-fr": "https://de-fr.my.glooko.com",
}

# Omnipod 5 pods are rated for 72 hours of use.
POD_LIFETIME_HOURS = 72

# v3 graph series requested each update (pump + meal data only; CGM left out on purpose).
GRAPH_SERIES: list[str] = [
    "automaticBolus",
    "basalBarAutomated",
    "basalBarAutomatedSuspend",
    "carbAll",
    "cgmSensorChange",
    "deliveredBolus",
    "interruptedBolus",
    "overrideAboveBolus",
    "overrideBelowBolus",
    "profileChange",
    "pumpAlarm",
    "pumpOp5AutomaticMode",
    "pumpOp5HypoprotectMode",
    "pumpOp5LimitedMode",
    "pumpOp5ManualMode",
    "pumpGenericAutomaticMode",
    "pumpGenericManualMode",
    "reservoirChange",
    "setSiteChange",
    "suspendBasal",
    "temporaryBasal",
]

MODE_SERIES: dict[str, str] = {
    "pumpOp5AutomaticMode": "automated",
    "pumpGenericAutomaticMode": "automated",
    "pumpOp5LimitedMode": "limited",
    "pumpOp5ManualMode": "manual",
    "pumpGenericManualMode": "manual",
    "pumpOp5HypoprotectMode": "hypoprotect",
}
PUMP_MODES: list[str] = ["automated", "limited", "manual", "hypoprotect", "unknown"]

INSULET_INTEGRATION = "INSULET_OMNIPOD_5_CLOUD"
