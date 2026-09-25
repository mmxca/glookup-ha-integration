"""Base entity for Glooko."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GlookoCoordinator


class GlookoEntity(CoordinatorEntity[GlookoCoordinator]):
    """Common device info / naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GlookoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        uid = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{uid}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name="Glooko",
            manufacturer="Glooko",
            model=(coordinator.data.pump_name if coordinator.data else None) or "Insulin pump",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://my.glooko.com",
        )
