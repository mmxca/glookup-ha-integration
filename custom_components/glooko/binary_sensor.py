"""Binary sensors for Glooko."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES
from .coordinator import GlookoConfigEntry, GlookoCoordinator
from .entity import GlookoEntity
from .parse import GlookoData


@dataclass(frozen=True, kw_only=True)
class GlookoBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[GlookoData, int], bool | None]


def _stale(d: GlookoData, limit: int) -> bool | None:
    age = d.data_age_minutes(dt_util.now())
    return None if age is None else age > limit


BINARY_SENSORS: tuple[GlookoBinaryDescription, ...] = (
    GlookoBinaryDescription(
        key="automated_mode",
        translation_key="automated_mode",
        value_fn=lambda d, _: None if d.pump_mode == "unknown" else d.pump_mode == "automated",
    ),
    GlookoBinaryDescription(
        key="data_stale",
        translation_key="data_stale",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_stale,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GlookoConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(GlookoBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class GlookoBinarySensor(GlookoEntity, BinarySensorEntity):
    """A Glooko binary sensor."""

    entity_description: GlookoBinaryDescription

    def __init__(self, coordinator: GlookoCoordinator, description: GlookoBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        limit = self.coordinator.config_entry.options.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)
        return self.entity_description.value_fn(self.coordinator.data, limit)
