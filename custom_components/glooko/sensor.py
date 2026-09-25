"""Sensors for Glooko."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import PUMP_MODES
from .coordinator import GlookoConfigEntry, GlookoCoordinator
from .entity import GlookoEntity
from .parse import GlookoData

UNIT_INSULIN = "U"
UNIT_CARBS = "g"
UNIT_MGDL = "mg/dL"


@dataclass(frozen=True, kw_only=True)
class GlookoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[GlookoData], Any]
    attrs_fn: Callable[[GlookoData], dict[str, Any] | None] = lambda d: None


def _bolus_attrs(d: GlookoData) -> dict[str, Any] | None:
    b = d.last_bolus
    if not b:
        return None
    return {
        "time": b.time.isoformat(),
        "programmed": b.programmed,
        "recommended": b.recommended,
        "meal_portion": b.meal_portion,
        "correction_portion": b.correction_portion,
        "carbs": b.carbs,
        "iob_at_bolus": b.iob,
        "bg_input": b.bg_input,
        "bg_source": b.bg_source,
        "override_above": b.override_above,
        "override_below": b.override_below,
        "interrupted": b.interrupted,
        "boluses_today": len(d.boluses_today),
    }


SENSORS: tuple[GlookoSensorDescription, ...] = (
    GlookoSensorDescription(
        key="last_bolus",
        translation_key="last_bolus",
        native_unit_of_measurement=UNIT_INSULIN,
        suggested_display_precision=2,
        value_fn=lambda d: d.last_bolus.delivered if d.last_bolus else None,
        attrs_fn=_bolus_attrs,
    ),
    GlookoSensorDescription(
        key="last_bolus_time",
        translation_key="last_bolus_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.last_bolus.time if d.last_bolus else None,
    ),
    GlookoSensorDescription(
        key="iob_at_last_bolus",
        translation_key="iob_at_last_bolus",
        native_unit_of_measurement=UNIT_INSULIN,
        suggested_display_precision=2,
        value_fn=lambda d: d.last_bolus.iob if d.last_bolus else None,
    ),
    GlookoSensorDescription(
        key="bolus_insulin_today",
        translation_key="bolus_insulin_today",
        native_unit_of_measurement=UNIT_INSULIN,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: d.bolus_insulin_today,
    ),
    GlookoSensorDescription(
        key="last_carbs",
        translation_key="last_carbs",
        native_unit_of_measurement=UNIT_CARBS,
        value_fn=lambda d: d.last_carbs,
        attrs_fn=lambda d: {"time": d.last_carbs_time.isoformat()} if d.last_carbs_time else None,
    ),
    GlookoSensorDescription(
        key="carbs_today",
        translation_key="carbs_today",
        native_unit_of_measurement=UNIT_CARBS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.carbs_today,
    ),
    GlookoSensorDescription(
        key="pump_mode",
        translation_key="pump_mode",
        device_class=SensorDeviceClass.ENUM,
        options=PUMP_MODES,
        value_fn=lambda d: d.pump_mode,
        attrs_fn=lambda d: {"since": d.pump_mode_since.isoformat()} if d.pump_mode_since else None,
    ),
    GlookoSensorDescription(
        key="pod_changed",
        translation_key="pod_changed",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.pod_changed,
    ),
    GlookoSensorDescription(
        key="pod_expires",
        translation_key="pod_expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.pod_expires,
    ),
    GlookoSensorDescription(
        key="pod_age",
        translation_key="pod_age",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        value_fn=lambda d: d.pod_age_hours(dt_util.now()),
    ),
    GlookoSensorDescription(
        key="cgm_sensor_changed",
        translation_key="cgm_sensor_changed",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.cgm_sensor_changed,
    ),
    GlookoSensorDescription(
        key="last_pump_alarm",
        translation_key="last_pump_alarm",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.last_pump_alarm,
    ),
    GlookoSensorDescription(
        key="last_sync",
        translation_key="last_sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.last_sync,
        attrs_fn=lambda d: {
            "transfer_type": d.last_sync_type,
            "connection_state": d.connection_state,
            "sync_state": d.sync_state,
            "last_sync_trigger": d.last_sync_trigger.isoformat() if d.last_sync_trigger else None,
            "sync_trigger_result": d.sync_trigger_result,
        },
    ),
    GlookoSensorDescription(
        key="data_through",
        translation_key="data_through",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.data_through,
    ),
    GlookoSensorDescription(
        key="data_age",
        translation_key="data_age",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda d: d.data_age_minutes(dt_util.now()),
    ),
    GlookoSensorDescription(
        key="time_in_range_14d",
        translation_key="time_in_range_14d",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.stats.get("inRangePercentage"),
        attrs_fn=lambda d: {
            "low_percentage": d.stats.get("lowPercentage"),
            "high_percentage": d.stats.get("highPercentage"),
            "cgm_active_percentage": d.stats.get("activeCgmTimePercentage"),
        },
    ),
    GlookoSensorDescription(
        key="gmi_14d",
        translation_key="gmi_14d",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.stats.get("gmi"),
    ),
    GlookoSensorDescription(
        key="average_glucose_14d",
        translation_key="average_glucose_14d",
        native_unit_of_measurement=UNIT_MGDL,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.stats.get("averageBg"),
        attrs_fn=lambda d: {"coefficient_of_variation": d.stats.get("coefficientOfVariation")},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GlookoConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(GlookoSensor(coordinator, desc) for desc in SENSORS)


class GlookoSensor(GlookoEntity, SensorEntity):
    """A Glooko sensor."""

    entity_description: GlookoSensorDescription

    def __init__(self, coordinator: GlookoCoordinator, description: GlookoSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.coordinator.data)
