"""Binary sensor platform for Dropcountr."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_DAY_COST,
    ATTR_DAY_GOAL,
    ATTR_LAST_ERROR,
    ATTR_LAST_SUCCESS,
    ATTR_LEAK_ARCHIVED,
    ATTR_LEAK_COST,
    ATTR_LEAK_CURRENCY,
    ATTR_LEAK_HOURLY_VOLUME,
    ATTR_LEAK_ID,
    ATTR_LEAK_IGNORED,
    ATTR_LEAK_STARTED_AT,
    ATTR_LEAK_VOLUME,
    ATTR_METER_COUNT,
    ATTR_METER_ID,
    ATTR_MONTH_COST,
    ATTR_MONTH_GOAL,
    ATTR_PREMISE_NAME,
    ATTR_PREMISE_TIMEZONE,
    ATTR_SCAN_INTERVAL,
    ATTR_SERVICE_TYPE,
    ATTR_WEEK_COST,
    ATTR_WEEK_GOAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import DropcountrDataUpdateCoordinator
from .sensor import _device_info


def _account_device_info(entry: ConfigEntry) -> dict:
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": entry.title or "Dropcountr",
        "manufacturer": "Dropcountr",
        "model": "Account",
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dropcountr binary sensors from a config entry."""
    coordinator: DropcountrDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        DropcountrApiHealthBinarySensor(coordinator, entry)
    ]
    entities.extend(
        DropcountrOpenLeakBinarySensor(coordinator, meter_id)
        for meter_id in coordinator.data
    )
    async_add_entities(entities)


class DropcountrApiHealthBinarySensor(
    CoordinatorEntity[DropcountrDataUpdateCoordinator], BinarySensorEntity
):
    """Diagnostic binary sensor for Dropcountr API health."""

    _attr_has_entity_name = True
    _attr_translation_key = "api_health"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-check"

    def __init__(
        self,
        coordinator: DropcountrDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_api_health"
        self._attr_device_info = _account_device_info(entry)

    @property
    def available(self) -> bool:
        """Always available so failures still show as Off."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True when the last API poll succeeded."""
        return self.coordinator.api_health.ok

    @property
    def icon(self) -> str:
        """Return icon based on API health."""
        return "mdi:cloud-check" if self.is_on else "mdi:cloud-off-outline"

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        """Return API health details."""
        health = self.coordinator.api_health
        last_success = health.last_success
        return {
            ATTR_LAST_SUCCESS: last_success.isoformat() if last_success else None,
            ATTR_LAST_ERROR: health.last_error,
            ATTR_METER_COUNT: health.meter_count,
            ATTR_SCAN_INTERVAL: int(
                self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        }


class DropcountrOpenLeakBinarySensor(
    CoordinatorEntity[DropcountrDataUpdateCoordinator], BinarySensorEntity
):
    """Open leak status from the service connection leaks API."""

    _attr_has_entity_name = True
    _attr_translation_key = "open_leak"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:pipe-leak"

    def __init__(
        self, coordinator: DropcountrDataUpdateCoordinator, meter_id: str
    ) -> None:
        super().__init__(coordinator)
        self._meter_id = meter_id
        snapshot = coordinator.data[meter_id]
        self._attr_unique_id = f"{meter_id}_open_leak"
        self._attr_device_info = _device_info(snapshot)

    @property
    def available(self) -> bool:
        """Available when the last poll succeeded and this meter is in the data."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._meter_id in self.coordinator.data
        )

    @property
    def is_on(self) -> bool:
        """Return True if an open-ended leak was found in the last 7 days."""
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return False
        return data.has_open_leak

    @property
    def icon(self) -> str:
        """Return icon based on leak state."""
        data = self.coordinator.data.get(self._meter_id)
        if data and data.has_open_leak:
            return "mdi:pipe-leak"
        return "mdi:pipe"

    @property
    def extra_state_attributes(self) -> dict[str, float | str | bool | None]:
        """Return leak and related cost/goal details when open."""
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return {}

        attrs: dict[str, float | str | bool | None] = {
            ATTR_PREMISE_NAME: data.premise_name,
            ATTR_PREMISE_TIMEZONE: data.premise_timezone,
            ATTR_METER_ID: data.meter_id,
            ATTR_SERVICE_TYPE: data.service_type,
        }
        if not data.has_open_leak:
            return attrs

        attrs.update(
            {
                ATTR_LEAK_ID: data.open_leak_id,
                ATTR_LEAK_STARTED_AT: data.open_leak_started_at,
                ATTR_LEAK_VOLUME: data.open_leak_volume,
                ATTR_LEAK_HOURLY_VOLUME: data.open_leak_hourly_volume,
                ATTR_LEAK_COST: data.open_leak_cost,
                ATTR_LEAK_CURRENCY: data.open_leak_currency,
                ATTR_LEAK_IGNORED: data.open_leak_ignored,
                ATTR_LEAK_ARCHIVED: data.open_leak_archived,
                ATTR_DAY_COST: data.day_cost,
                ATTR_WEEK_COST: data.week_cost,
                ATTR_MONTH_COST: data.month_cost,
                ATTR_DAY_GOAL: data.day_goal_gallons,
                ATTR_WEEK_GOAL: data.week_goal_gallons,
                ATTR_MONTH_GOAL: data.month_goal_gallons,
            }
        )
        return attrs
