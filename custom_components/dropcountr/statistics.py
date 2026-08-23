"""Import Dropcountr hourly usage and cost into Recorder long-term statistics."""

from __future__ import annotations

from collections.abc import Callable
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
    TOTAL_COST_KEY,
    TOTAL_USAGE_KEY,
)
from .coordinator import (
    DropcountrDataUpdateCoordinator,
    MeterSnapshot,
    exclusive_last_days,
    fetch_hourly_backfill_for_meter,
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
    amounts: list[tuple[datetime, float]], base_sum: float
) -> list[tuple[datetime, float]]:
    running = base_sum
    rows: list[tuple[datetime, float]] = []
    for start, amount in amounts:
        running += amount
        rows.append((start, running))
    return rows


def _volume_metadata(entity_id: str, name: str | None) -> StatisticMetaData:
    return {
        "has_mean": False,
        "has_sum": True,
        "name": name,
        "source": "recorder",
        "statistic_id": entity_id,
        "unit_class": "volume",
        "unit_of_measurement": UnitOfVolume.GALLONS,
        "mean_type": StatisticMeanType.NONE,
    }


def _cost_metadata(
    entity_id: str, name: str | None, currency: str | None
) -> StatisticMetaData:
    return {
        "has_mean": False,
        "has_sum": True,
        "name": name,
        "source": "recorder",
        "statistic_id": entity_id,
        "unit_class": None,
        "unit_of_measurement": currency,
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


async def _import_amounts(
    hass: HomeAssistant,
    entity_id: str,
    metadata: StatisticMetaData,
    amounts: list[tuple[datetime, float]],
    base_sum: float,
) -> float | None:
    from homeassistant.components.recorder.statistics import async_import_statistics

    if not amounts:
        return None
    rows = _running_sums(amounts, base_sum)
    statistics: list[StatisticData] = [
        {
            "start": dt_util.as_utc(start),
            "state": total,
            "sum": total,
        }
        for start, total in rows
    ]
    async_import_statistics(hass, metadata, statistics)
    return rows[-1][1]


async def _import_series(
    hass: HomeAssistant,
    entity_id: str | None,
    name: str | None,
    last_sum: float | None,
    recent: list[tuple[datetime, float]],
    backfill: list[tuple[datetime, float]] | None,
    metadata_fn: Callable[[str, str | None], StatisticMetaData],
) -> float | None:
    if entity_id is None:
        return None
    metadata = metadata_fn(entity_id, name)
    if last_sum is None:
        first = backfill if backfill else recent
        return await _import_amounts(hass, entity_id, metadata, first, 0.0)
    if not recent:
        return last_sum
    base_sum = await _recorder_sum_before(hass, entity_id, recent[0][0])
    lifetime = await _import_amounts(hass, entity_id, metadata, recent, base_sum)
    return last_sum if lifetime is None else lifetime


async def async_import_hourly_statistics(
    hass: HomeAssistant,
    coordinator: DropcountrDataUpdateCoordinator,
    data: dict[str, MeterSnapshot] | None = None,
) -> dict[str, MeterSnapshot] | None:
    """Backfill or catch up hourly water and cost statistics.

    Returns a new snapshot dict when lifetime fields change, otherwise ``None``.
    Does not notify coordinator listeners.
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
        usage_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{meter_id}_{TOTAL_USAGE_KEY}"
        )
        cost_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{meter_id}_{TOTAL_COST_KEY}"
        )
        if usage_id is None and cost_id is None:
            continue

        usage_last = (
            await _recorder_last_sum(hass, usage_id) if usage_id is not None else None
        )
        cost_last = (
            await _recorder_last_sum(hass, cost_id) if cost_id is not None else None
        )

        usage_backfill: list[tuple[datetime, float]] | None = None
        cost_backfill: list[tuple[datetime, float]] | None = None
        if (usage_id is not None and usage_last is None) or (
            cost_id is not None and cost_last is None
        ):
            today = _local_today(snapshot.premise_timezone)
            during = exclusive_last_days(today, STATISTICS_BACKFILL_DAYS)
            try:
                usage_points, cost_points = await hass.async_add_executor_job(
                    fetch_hourly_backfill_for_meter,
                    coordinator.entry.data[CONF_EMAIL],
                    coordinator.entry.data[CONF_PASSWORD],
                    meter_id,
                    during,
                )
            except Exception:
                _LOGGER.exception(
                    "Dropcountr 30-day hourly backfill failed for %s", meter_id
                )
                usage_points, cost_points = [], []
            usage_backfill = [(point.start, point.gallons) for point in usage_points]
            cost_backfill = [(point.start, point.price) for point in cost_points]

        lifetime_gallons = await _import_series(
            hass,
            usage_id,
            snapshot.name,
            usage_last,
            [(point.start, point.gallons) for point in snapshot.hourly_points],
            usage_backfill,
            _volume_metadata,
        )
        lifetime_cost = await _import_series(
            hass,
            cost_id,
            snapshot.name,
            cost_last,
            [(point.start, point.price) for point in snapshot.hourly_cost_points],
            cost_backfill,
            lambda entity_id, name: _cost_metadata(
                entity_id, name, snapshot.cost_currency
            ),
        )

        new_snap = snapshot
        if (
            lifetime_gallons is not None
            and lifetime_gallons != snapshot.lifetime_gallons
        ):
            new_snap = replace(new_snap, lifetime_gallons=lifetime_gallons)
        if lifetime_cost is not None and lifetime_cost != snapshot.lifetime_cost:
            new_snap = replace(new_snap, lifetime_cost=lifetime_cost)
        if new_snap is not snapshot:
            new_data[meter_id] = new_snap
            updated = True

    return new_data if updated else None
