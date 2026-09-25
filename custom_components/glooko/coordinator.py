"""Data update coordinator for Glooko."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GlookoAuthError, GlookoClient, GlookoError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SYNC_TRIGGER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SYNC_TRIGGER,
    DOMAIN,
    GRAPH_SERIES,
    INSULET_INTEGRATION,
    STATS_REFRESH_MINUTES,
    SYNC_REFRESH_DELAY,
)
from .parse import GlookoData, glooko_day_range, parse

_LOGGER = logging.getLogger(__name__)

type GlookoConfigEntry = ConfigEntry[GlookoCoordinator]


class GlookoCoordinator(DataUpdateCoordinator[GlookoData]):
    """Polls Glooko read-only on a fixed interval."""

    config_entry: GlookoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: GlookoConfigEntry, client: GlookoClient) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self._stats: dict[str, Any] | None = None
        self._stats_at = None
        self.raw: dict[str, Any] = {}
        self._last_trigger = None
        self._trigger_result: str | None = None
        self._cancel_refresh = None

    async def _async_update_data(self) -> GlookoData:
        tz = ZoneInfo(self.hass.config.time_zone)
        now = dt_util.now()
        today = now.astimezone(tz).date()
        try:
            code = self.client.glooko_code or await self.client.async_login()
            start, end = glooko_day_range(today - timedelta(days=1), today)
            graph = await self.client.async_get(
                "/api/v3/graph/data",
                [
                    ("patient", code),
                    ("startDate", start),
                    ("endDate", end),
                    ("locale", "en"),
                    ("insulinTooltips", "false"),
                    ("filterBgReadings", "false"),
                    ("splitByDay", "false"),
                    *(("series[]", s) for s in GRAPH_SERIES),
                ],
            )
            devices = await self.client.async_get("/api/v3/devices_and_settings", {"patient": code})
            connections = await self.client.async_get(
                "/api/v3/cloud_connections", {"clientType": "web", "patient": code}
            )
            if self._stats_at is None or now - self._stats_at > timedelta(minutes=STATS_REFRESH_MINUTES):
                s_start, s_end = glooko_day_range(today - timedelta(days=13), today)
                self._stats = await self.client.async_get(
                    "/api/v3/graph/statistics/overall",
                    {
                        "patient": code,
                        "startDate": s_start,
                        "endDate": s_end,
                        "egv": "true",
                        "normalized": "false",
                        "includeInsulin": "true",
                        "includeExercise": "false",
                        "excludeManual": "false",
                        "dow": "monday,tuesday,wednesday,thursday,friday,saturday,sunday",
                        "includePumpModes": "true",
                    },
                )
                self._stats_at = now
        except GlookoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GlookoError as err:
            raise UpdateFailed(str(err)) from err

        await self._maybe_trigger_sync(connections, now)

        self.raw = {"graph": graph, "devices": devices, "connections": connections, "stats": self._stats}
        data = parse(
            graph=graph,
            devices=devices,
            connections=connections if isinstance(connections, list) else None,
            stats=self._stats,
            tz=tz,
            now=now,
        )
        data.last_sync_trigger = self._last_trigger
        data.sync_trigger_result = self._trigger_result
        return data

    async def _maybe_trigger_sync(self, connections: Any, now) -> None:
        """Ask Glooko to pull fresh pump data via a web sign-in, at most every N minutes.

        Skipped while Glooko reports its cooldown (syncState ALREADY_SYNCED). Failures are
        logged and never fail the regular update.
        """
        minutes = int(self.config_entry.options.get(CONF_SYNC_TRIGGER, DEFAULT_SYNC_TRIGGER))
        if minutes <= 0:
            return
        if self._last_trigger and now - self._last_trigger < timedelta(minutes=minutes):
            return
        state = next(
            (c.get("syncState") for c in connections or [] if isinstance(c, dict) and c.get("integration") == INSULET_INTEGRATION),
            None,
        )
        if state == "ALREADY_SYNCED":
            return
        self._last_trigger = now
        try:
            await self.client.async_trigger_sync()
        except Exception as err:  # noqa: BLE001 - a trigger problem must never fail the regular update
            self._trigger_result = f"failed: {err}"
            _LOGGER.warning("Glooko sync trigger failed (data will still update): %s", err)
            return
        self._trigger_result = "ok"
        _LOGGER.debug("Triggered Glooko on-demand pump sync; re-polling in %ss", SYNC_REFRESH_DELAY)
        if self._cancel_refresh:
            self._cancel_refresh()
        self._cancel_refresh = async_call_later(self.hass, SYNC_REFRESH_DELAY, self._delayed_refresh)

    async def _delayed_refresh(self, _now) -> None:
        self._cancel_refresh = None
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        if self._cancel_refresh:
            self._cancel_refresh()
            self._cancel_refresh = None
        await super().async_shutdown()
