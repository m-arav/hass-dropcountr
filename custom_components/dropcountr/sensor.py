"""Sensor platform for Dropcountr."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_METER_ID,
    ATTR_PREMISE_NAME,
    ATTR_SERVICE_TYPE,
    DOMAIN,
)
from .coordinator import DropcountrDataUpdateCoordinator, MeterSnapshot


@dataclass(frozen=True, kw_only=True)
class DropcountrSensorEntityDescription(SensorEntityDescription):
    """Describes a Dropcountr sensor."""

    value_fn: Callable[[MeterSnapshot], float]


SENSORS: tuple[DropcountrSensorEntityDescription, ...] = (
    DropcountrSensorEntityDescription(
        key="week_usage",
        translation_key="week_usage",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.week_gallons,
    ),
    DropcountrSensorEntityDescription(
        key="month_usage",
        translation_key="month_usage",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.month_gallons,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dropcountr sensors from a config entry."""
    coordinator: DropcountrDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[DropcountrUsageSensor] = []
    for meter_id in coordinator.data:
        for description in SENSORS:
            entities.append(DropcountrUsageSensor(coordinator, meter_id, description))
    async_add_entities(entities)


class DropcountrUsageSensor(
    CoordinatorEntity[DropcountrDataUpdateCoordinator], SensorEntity
):
    """Usage sensor for a Dropcountr meter."""

    entity_description: DropcountrSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DropcountrDataUpdateCoordinator,
        meter_id: str,
        description: DropcountrSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._meter_id = meter_id
        snapshot = coordinator.data[meter_id]
        self._attr_unique_id = f"{meter_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, meter_id)},
            "name": f"{snapshot.premise_name} {snapshot.name}",
            "manufacturer": "Dropcountr",
            "model": snapshot.service_type or "meter",
        }

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return extra attributes."""
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return {}
        return {
            ATTR_PREMISE_NAME: data.premise_name,
            ATTR_METER_ID: data.meter_id,
            ATTR_SERVICE_TYPE: data.service_type,
        }
