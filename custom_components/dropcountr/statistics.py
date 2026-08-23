"""Import Dropcountr hourly usage into Recorder long-term statistics."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    STATISTICS_BACKFILL_DAYS,
    TOTAL_USAGE_KEY,
)
from .coordinator import (
    DropcountrDataUpdateCoordinator,
    HourlyPoint,
    MeterSnapshot,
    exclusive_last_days,
    fetch_hourly_points_for_meter,
    _local_today,
)

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.components.recorder.models import (
        StatisticData,
        StatisticMeanType,
        StatisticMetaData,
    )
except ImportError:  # pragma: no cover - older HA layout
    from homeassistant.components.recorder.models.statistics import (  # type: ignore[no-redef]
        StatisticData,
        StatisticMeanType,
        StatisticMetaData,
    )


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


def _running_sums(
    points: list[HourlyPoint], base_sum: float
) -> list[tuple[datetime, float]]:
    running = base_sum
    rows: list[tuple[datetime, float]] = []
    for point in points:
        running += point.gallons
        rows.append((point.start, running))
    return rows


def _statistic_metadata(entity_id: str, name: str | None) -> StatisticMetaData:
    return {
        "has_mean": False,
        "has_sum": True,
        "name": name,
        "source": "sensor",
        "statistic_id": entity_id,
        "unit_class": "volume",
        "unit_of_measurement": UnitOfVolume.GALLONS,
        "mean_type": StatisticMeanType.NONE,
    }


async def _recorder_last_sum(hass: HomeAssistant, statistic_id: str) -> float | None:
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import get_last_statistics

    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        statistic_id,
        True,
        {"sum"},
    )
    rows = last.get(statistic_id) or []
    if not rows:
        return None
    sum_value = rows[-1].get("sum")
    return float(sum_value) if sum_value is not None else None


async def _recorder_sum_before(
    hass: HomeAssistant, statistic_id: str, before: datetime
) -> float:
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import statistics_during_period

    start = before - timedelta(hours=36)
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        before,
        {statistic_id},
        "hour",
        None,
        {"sum"},
    )
    best_sum = 0.0
    best_start: datetime | None = None
    for row in rows.get(statistic_id) or []:
        row_start = _as_datetime(row.get("start"))
        sum_value = row.get("sum")
        if row_start is None or sum_value is None or row_start >= before:
            continue
        if best_start is None or row_start > best_start:
            best_start = row_start
            best_sum = float(sum_value)
    return best_sum


async def _import_points(
    hass: HomeAssistant,
    entity_id: str,
    name: str | None,
    points: list[HourlyPoint],
    base_sum: float,
) -> float | None:
    from homeassistant.components.recorder.statistics import async_import_statistics

    if not points:
        return None
    rows = _running_sums(points, base_sum)
    statistics: list[StatisticData] = [
        {
            "start": dt_util.as_utc(start),
            "state": total,
            "sum": total,
        }
        for start, total in rows
    ]
    async_import_statistics(hass, _statistic_metadata(entity_id, name), statistics)
    return rows[-1][1]


async def async_import_hourly_statistics(
    hass: HomeAssistant,
    coordinator: DropcountrDataUpdateCoordinator,
    data: dict[str, MeterSnapshot] | None = None,
) -> dict[str, MeterSnapshot] | None:
    """Backfill or catch up hourly water statistics.

    Returns a new snapshot dict when ``lifetime_gallons`` changes, otherwise
    ``None``. Does not notify coordinator listeners.
    """
    if "recorder" not in hass.config.components:
        _LOGGER.debug("Recorder is not enabled; skipping Dropcountr statistics import")
        return None
    snapshots = data if data is not None else coordinator.data
    if not snapshots:
        return None

    registry = er.async_get(hass)
    updated = False
    new_data = dict(snapshots)

    for meter_id, snapshot in snapshots.items():
        unique_id = f"{meter_id}_{TOTAL_USAGE_KEY}"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id is None:
            continue

        last_sum = await _recorder_last_sum(hass, entity_id)
        if last_sum is None:
            today = _local_today(snapshot.premise_timezone)
            during = exclusive_last_days(today, STATISTICS_BACKFILL_DAYS)
            try:
                points = await hass.async_add_executor_job(
                    fetch_hourly_points_for_meter,
                    coordinator.entry.data[CONF_EMAIL],
                    coordinator.entry.data[CONF_PASSWORD],
                    meter_id,
                    during,
                )
            except Exception:
                _LOGGER.exception(
                    "Dropcountr 30-day hourly backfill failed for %s", meter_id
                )
                continue
            lifetime = await _import_points(hass, entity_id, snapshot.name, points, 0.0)
        else:
            points = list(snapshot.hourly_points)
            if not points:
                lifetime = last_sum
            else:
                base_sum = await _recorder_sum_before(hass, entity_id, points[0].start)
                lifetime = await _import_points(
                    hass, entity_id, snapshot.name, points, base_sum
                )
                if lifetime is None:
                    lifetime = last_sum

        if lifetime is not None and lifetime != snapshot.lifetime_gallons:
            new_data[meter_id] = replace(snapshot, lifetime_gallons=lifetime)
            updated = True

    return new_data if updated else None
