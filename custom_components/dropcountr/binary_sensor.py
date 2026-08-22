"""Binary sensor platform for Dropcountr."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_LEAK_COST,
    ATTR_LEAK_CURRENCY,
    ATTR_LEAK_ID,
    ATTR_LEAK_STARTED_AT,
    ATTR_LEAK_VOLUME,
    ATTR_METER_ID,
    ATTR_PREMISE_NAME,
    ATTR_SERVICE_TYPE,
    DOMAIN,
)
from .coordinator import DropcountrDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dropcountr binary sensors from a config entry."""
    coordinator: DropcountrDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DropcountrOpenLeakBinarySensor(coordinator, meter_id)
        for meter_id in coordinator.data
    )


class DropcountrOpenLeakBinarySensor(
    CoordinatorEntity[DropcountrDataUpdateCoordinator], BinarySensorEntity
):
    """Open leak status from the service connection leaks API."""

    _attr_has_entity_name = True
    _attr_translation_key = "open_leak"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self, coordinator: DropcountrDataUpdateCoordinator, meter_id: str
    ) -> None:
        super().__init__(coordinator)
        self._meter_id = meter_id
        snapshot = coordinator.data[meter_id]
        self._attr_unique_id = f"{meter_id}_open_leak"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, meter_id)},
            "name": f"{snapshot.premise_name} {snapshot.name}",
            "manufacturer": "Dropcountr",
            "model": snapshot.service_type or "meter",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if an open-ended leak was found in the last 7 days."""
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return None
        return data.has_open_leak

    @property
    def extra_state_attributes(self) -> dict[str, float | str | None]:
        """Return leak details when open."""
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return {}
        return {
            ATTR_PREMISE_NAME: data.premise_name,
            ATTR_METER_ID: data.meter_id,
            ATTR_SERVICE_TYPE: data.service_type,
            ATTR_LEAK_ID: data.open_leak_id,
            ATTR_LEAK_STARTED_AT: data.open_leak_started_at,
            ATTR_LEAK_VOLUME: data.open_leak_volume,
            ATTR_LEAK_COST: data.open_leak_cost,
            ATTR_LEAK_CURRENCY: data.open_leak_currency,
        }
