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
from homeassistant.const import EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_COST_CURRENCY,
    ATTR_DAY_COST,
    ATTR_DAY_GOAL,
    ATTR_DURING,
    ATTR_DURING_END,
    ATTR_DURING_START,
    ATTR_METER_ID,
    ATTR_MONTH_COST,
    ATTR_MONTH_GOAL,
    ATTR_PREMISE_NAME,
    ATTR_SERVICE_TYPE,
    ATTR_WEEK_COST,
    ATTR_WEEK_GOAL,
    DOMAIN,
)
from .coordinator import DropcountrDataUpdateCoordinator, MeterSnapshot


def _during_bounds(during: str | None) -> tuple[str | None, str | None]:
    if not during or "/" not in during:
        return None, None
    start, end = during.split("/", 1)
    return start, end


@dataclass(frozen=True, kw_only=True)
class DropcountrSensorEntityDescription(SensorEntityDescription):
    """Describes a Dropcountr sensor."""

    value_fn: Callable[[MeterSnapshot], float | None]
    available_fn: Callable[[MeterSnapshot], bool] = lambda _data: True


SENSORS: tuple[DropcountrSensorEntityDescription, ...] = (
    DropcountrSensorEntityDescription(
        key="day_usage",
        translation_key="day_usage",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.day_gallons,
    ),
    DropcountrSensorEntityDescription(
        key="yesterday_usage",
        translation_key="yesterday_usage",
        icon="mdi:water-minus",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.yesterday_gallons,
    ),
    DropcountrSensorEntityDescription(
        key="week_usage",
        translation_key="week_usage",
        icon="mdi:water-outline",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.week_gallons,
    ),
    DropcountrSensorEntityDescription(
        key="month_usage",
        translation_key="month_usage",
        icon="mdi:cup-water",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.month_gallons,
    ),
    DropcountrSensorEntityDescription(
        key="day_cost",
        translation_key="day_cost",
        icon="mdi:currency-usd",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.day_cost,
        available_fn=lambda data: data.day_cost is not None,
    ),
    DropcountrSensorEntityDescription(
        key="week_cost",
        translation_key="week_cost",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.week_cost,
        available_fn=lambda data: data.week_cost is not None,
    ),
    DropcountrSensorEntityDescription(
        key="month_cost",
        translation_key="month_cost",
        icon="mdi:cash-multiple",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.month_cost,
        available_fn=lambda data: data.month_cost is not None,
    ),
    DropcountrSensorEntityDescription(
        key="day_goal",
        translation_key="day_goal",
        icon="mdi:bullseye-arrow",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.day_goal_gallons,
        available_fn=lambda data: data.day_goal_gallons is not None,
    ),
    DropcountrSensorEntityDescription(
        key="week_goal",
        translation_key="week_goal",
        icon="mdi:target",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.week_goal_gallons,
        available_fn=lambda data: data.week_goal_gallons is not None,
    ),
    DropcountrSensorEntityDescription(
        key="month_goal",
        translation_key="month_goal",
        icon="mdi:flag-checkered",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.month_goal_gallons,
        available_fn=lambda data: data.month_goal_gallons is not None,
    ),
    DropcountrSensorEntityDescription(
        key="leak_est_volume",
        translation_key="leak_est_volume",
        icon="mdi:pipe-leak",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.open_leak_volume,
        available_fn=lambda data: data.has_open_leak,
    ),
    DropcountrSensorEntityDescription(
        key="leak_est_hourly_volume",
        translation_key="leak_est_hourly_volume",
        icon="mdi:water-pump",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.open_leak_hourly_volume,
        available_fn=lambda data: data.has_open_leak,
    ),
    DropcountrSensorEntityDescription(
        key="leak_est_cost",
        translation_key="leak_est_cost",
        icon="mdi:cash-remove",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.open_leak_cost,
        available_fn=lambda data: data.has_open_leak and data.open_leak_cost is not None,
    ),
)


def _device_info(snapshot: MeterSnapshot) -> dict:
    """Build device info showing connection name and meter number."""
    connection_name = snapshot.name or "Meter"
    if snapshot.name and snapshot.meter_id:
        device_name = f"{snapshot.premise_name} — {snapshot.name} ({snapshot.meter_id})"
    elif snapshot.meter_id:
        device_name = f"{snapshot.premise_name} — {snapshot.meter_id}"
    else:
        device_name = f"{snapshot.premise_name} — {connection_name}"

    info: dict = {
        "identifiers": {(DOMAIN, snapshot.meter_id)},
        "name": device_name,
        "manufacturer": "Dropcountr",
        "model": snapshot.service_type or connection_name,
    }
    if snapshot.meter_id:
        info["serial_number"] = snapshot.meter_id
    return info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dropcountr sensors from a config entry."""
    coordinator: DropcountrDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[DropcountrSensor] = []
    for meter_id in coordinator.data:
        for description in SENSORS:
            entities.append(DropcountrSensor(coordinator, meter_id, description))
    async_add_entities(entities)


class DropcountrSensor(
    CoordinatorEntity[DropcountrDataUpdateCoordinator], SensorEntity
):
    """Sensor for a Dropcountr meter."""

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
        self._attr_device_info = _device_info(snapshot)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available:
            return False
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return False
        return self.entity_description.available_fn(data)

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit; monetary sensors use the account currency."""
        if self.entity_description.device_class == SensorDeviceClass.MONETARY:
            data = self.coordinator.data.get(self._meter_id)
            if data is None:
                return None
            if self.entity_description.key == "leak_est_cost":
                return data.open_leak_currency or data.cost_currency
            return data.cost_currency
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, float | str | None]:
        """Return extra attributes."""
        data = self.coordinator.data.get(self._meter_id)
        if data is None:
            return {}
        attrs: dict[str, float | str | None] = {
            ATTR_PREMISE_NAME: data.premise_name,
            ATTR_METER_ID: data.meter_id,
            ATTR_SERVICE_TYPE: data.service_type,
        }
        if self.entity_description.key.endswith("_usage"):
            attrs.update(
                {
                    ATTR_DAY_GOAL: data.day_goal_gallons,
                    ATTR_WEEK_GOAL: data.week_goal_gallons,
                    ATTR_MONTH_GOAL: data.month_goal_gallons,
                    ATTR_DAY_COST: data.day_cost,
                    ATTR_WEEK_COST: data.week_cost,
                    ATTR_MONTH_COST: data.month_cost,
                    ATTR_COST_CURRENCY: data.cost_currency,
                }
            )
            during_map = {
                "day_usage": data.day_during,
                "yesterday_usage": data.yesterday_during,
                "week_usage": data.week_during,
                "month_usage": data.month_during,
            }
            during = during_map.get(self.entity_description.key)
            start, end = _during_bounds(during)
            attrs[ATTR_DURING] = during
            attrs[ATTR_DURING_START] = start
            attrs[ATTR_DURING_END] = end
        return attrs
