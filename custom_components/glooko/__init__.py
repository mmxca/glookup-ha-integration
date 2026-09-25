"""The Glooko integration (read-only Omnipod 5 data via Glooko)."""

from __future__ import annotations

import aiohttp

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import GlookoClient
from .const import CONF_DEVICE_ID, CONF_REGION, CONF_SERIAL, DEFAULT_REGION
from .coordinator import GlookoConfigEntry, GlookoCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


def build_client(hass: HomeAssistant, data: dict) -> GlookoClient:
    """Create a client with its own cookie-less session (cookies are handled explicitly)."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    return GlookoClient(
        session,
        data[CONF_EMAIL],
        data[CONF_PASSWORD],
        data.get(CONF_REGION, DEFAULT_REGION),
        data[CONF_DEVICE_ID],
        data[CONF_SERIAL],
    )


async def async_setup_entry(hass: HomeAssistant, entry: GlookoConfigEntry) -> bool:
    """Set up Glooko from a config entry."""
    coordinator = GlookoCoordinator(hass, entry, build_client(hass, dict(entry.data)))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: GlookoConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GlookoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
