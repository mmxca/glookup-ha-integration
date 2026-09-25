"""Diagnostics for Glooko (secrets and identifiers redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_ID, CONF_SERIAL
from .coordinator import GlookoConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    CONF_SERIAL,
    "glookoCode",
    "glookoCodes",
    "integrationUserId",
    "serialNumber",
    "guid",
    "pumpGuid",
    "blobFileName",
    "unique_id",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: GlookoConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data({**entry.as_dict(), "data": dict(entry.data)}, TO_REDACT),
        "parsed": async_redact_data(asdict(coordinator.data), TO_REDACT) if coordinator.data else None,
        "raw_devices": async_redact_data(coordinator.raw.get("devices") or {}, TO_REDACT),
        "raw_connections": async_redact_data(coordinator.raw.get("connections") or [], TO_REDACT),
    }
