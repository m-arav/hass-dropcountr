"""DataUpdateCoordinator for Dropcountr."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dropcountr import DropcountrClient
from dropcountr.models import BILLING_PERIOD_FEATURE, Leak, Premise, ServiceConnection, UsageStats
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_EMAIL,
    CONF_METER_IDS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ApiHealth:
    """Diagnostic status for the Dropcountr API connection."""

    ok: bool
    last_success: datetime | None = None
    last_error: str | None = None
    meter_count: int = 0


@dataclass(frozen=True)
class MeterSnapshot:
    """Polled state for one service connection (meter)."""

    meter_id: str
    service_connection_id: str
    name: str
    premise_name: str
    premise_timezone: str | None
    service_type: str | None
    read_frequency: str | None
    lag: str | None
    completeness_7d: float | None
    completeness_30d: float | None
    completeness_90d: float | None
    day_gallons: float
    yesterday_gallons: float
    week_gallons: float
    month_gallons: float
    day_during: str | None
    yesterday_during: str | None
    week_during: str | None
    month_during: str | None
    day_cost: float | None
    week_cost: float | None
    month_cost: float | None
    cost_currency: str | None
    day_goal_gallons: float | None
    week_goal_gallons: float | None
    month_goal_gallons: float | None
    has_open_leak: bool
    open_leak_id: str | None = None
    open_leak_started_at: str | None = None
    open_leak_volume: float | None = None
    open_leak_hourly_volume: float | None = None
    open_leak_cost: float | None = None
    open_leak_currency: str | None = None
    open_leak_ignored: bool | None = None
    open_leak_archived: bool | None = None
    hour_gallons: float | None = None
    hour_irrigation_gallons: float | None = None
    hour_during: str | None = None
    day_irrigation_gallons: float = 0.0
    day_irrigation_events: float = 0.0
    week_irrigation_gallons: float = 0.0
    month_irrigation_gallons: float = 0.0
    billing_gallons: float | None = None
    billing_irrigation_gallons: float | None = None
    billing_irrigation_events: float | None = None
    billing_during: str | None = None
    billing_cost: float | None = None
    billing_goal_gallons: float | None = None


def _local_today(tz_name: str | None) -> date:
    """Calendar date at the premise, not the Home Assistant host."""
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except (ZoneInfoNotFoundError, ValueError):
            _LOGGER.debug("Unknown premise timezone %s", tz_name)
    return date.today()


def _monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _exclusive_day_during(day: date) -> str:
    return f"{day.isoformat()}/{(day + timedelta(days=1)).isoformat()}"


def _exclusive_week_during(today: date) -> str:
    start = _monday_of(today)
    end = start + timedelta(days=7)
    return f"{start.isoformat()}/{end.isoformat()}"


def _exclusive_month_during(today: date) -> str:
    start = today.replace(day=1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1)
    else:
        end = date(today.year, today.month + 1, 1)
    return f"{start.isoformat()}/{end.isoformat()}"


def _exclusive_last_7_days(today: date) -> str:
    start = today - timedelta(days=7)
    end = today + timedelta(days=1)
    return f"{start.isoformat()}/{end.isoformat()}"


def _exclusive_billing_query(today: date) -> str:
    """Current calendar month; the API returns the billing bucket that overlaps."""
    start = today.replace(day=1)
    return f"{start.isoformat()}/{(today + timedelta(days=1)).isoformat()}"


def _parse_instant(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _interval_start(during: str | None) -> datetime | None:
    if not during:
        return None
    if "/" in during:
        during = during.split("/", 1)[0]
    return _parse_instant(during)


def _interval_start_date(during: str | None) -> date | None:
    start = _interval_start(during)
    return start.date() if start else None


def _interval_end_date(during: str | None) -> date | None:
    if not during or "/" not in during:
        return None
    end = _parse_instant(during.split("/", 1)[1])
    return end.date() if end else None


@dataclass(frozen=True)
class UsageTotals:
    gallons: float = 0.0
    irrigation_gallons: float = 0.0
    irrigation_events: float = 0.0
    during: str | None = None


def _totals_from_members(members: list) -> UsageTotals:
    reported = [point for point in members if point.total_gallons is not None]
    return UsageTotals(
        gallons=sum(point.total_gallons or 0.0 for point in reported),
        irrigation_gallons=sum(point.irrigation_gallons or 0.0 for point in reported),
        irrigation_events=sum(point.irrigation_events or 0.0 for point in reported),
        during=_server_during_from_members(reported or members),
    )


def _totals_from_point(point) -> UsageTotals:
    return UsageTotals(
        gallons=point.total_gallons,
        irrigation_gallons=point.irrigation_gallons,
        irrigation_events=point.irrigation_events,
        during=point.during,
    )


_ISO_DURATION = re.compile(
    r"^P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def _iso_duration_hours(value: str | None) -> float | None:
    """Parse an ISO-8601 duration (``lag``) into hours."""
    if not value:
        return None
    match = _ISO_DURATION.fullmatch(value)
    if not match:
        return None
    years = float(match.group("years") or 0)
    months = float(match.group("months") or 0)
    days = float(match.group("days") or 0)
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return (
        years * 365.25 * 24
        + months * 30.4375 * 24
        + days * 24
        + hours
        + minutes / 60
        + seconds / 3600
    )


def _latest_reported_hour(members: list):
    """Latest hourly bucket whose gallons are not null (vendor has reported)."""
    dated: list[tuple[datetime, object]] = []
    for point in members:
        if point.total_gallons is None:
            continue
        start = _interval_start(point.during)
        if start is None:
            continue
        dated.append((start, point))
    if not dated:
        return None
    dated.sort(key=lambda item: item[0])
    return dated[-1][1]


def _current_billing_member(members: list, today: date):
    for point in members:
        start = _interval_start_date(point.during)
        end = _interval_end_date(point.during)
        if start and end and start <= today < end:
            return point
    return members[-1] if members else None


def _server_during_from_members(members: list) -> str | None:
    """Use the API's aligned interval(s), not the client request window."""
    if not members:
        return None
    if len(members) == 1:
        return members[0].during
    first = members[0].during.split("/", 1)
    last = members[-1].during.split("/", 1)
    if len(first) == 2 and len(last) == 2:
        return f"{first[0]}/{last[1]}"
    return members[0].during


def _fetch_usage(
    client: DropcountrClient, sc: ServiceConnection, period: str, during: str
) -> UsageTotals:
    """Return usage totals and the server-aligned during interval."""
    if not sc.usage_series:
        return UsageTotals()
    series = client.usage(sc, period=period, during=during)
    return _totals_from_members(list(series.members))


def _fetch_hour_usage(
    client: DropcountrClient, sc: ServiceConnection, during: str
) -> UsageTotals | None:
    if not sc.usage_series:
        return None
    series = client.usage(sc, period="hour", during=during)
    point = _latest_reported_hour(list(series.members))
    if point is None:
        return None
    return _totals_from_point(point)


def _supports_billing(sc: ServiceConnection) -> bool:
    return BILLING_PERIOD_FEATURE in (sc.features or [])


def _fetch_billing_usage(
    client: DropcountrClient, sc: ServiceConnection, during: str, today: date
) -> UsageTotals | None:
    if not sc.usage_series or not _supports_billing(sc):
        return None
    try:
        series = client.usage(sc, period="billing", during=during)
    except Exception:
        _LOGGER.debug(
            "Dropcountr billing usage failed for %s",
            sc.meter_id or sc.id,
            exc_info=True,
        )
        return None
    point = _current_billing_member(list(series.members), today)
    if point is None:
        return None
    return _totals_from_point(point)


def _fetch_billing_cost(
    client: DropcountrClient, sc: ServiceConnection, during: str, today: date
) -> tuple[float | None, str | None]:
    if not sc.cost_series or not _supports_billing(sc):
        return None, None
    try:
        series = client.cost(sc, period="billing", during=during)
    except Exception:
        _LOGGER.debug(
            "Dropcountr billing cost failed for %s",
            sc.meter_id or sc.id,
            exc_info=True,
        )
        return None, None
    point = _current_billing_member(list(series.members), today)
    if point is None:
        return None, None
    return point.price, point.price_currency


def _fetch_billing_goal(
    client: DropcountrClient, sc: ServiceConnection, during: str, today: date
) -> float | None:
    if not sc.goal_series or not _supports_billing(sc):
        return None
    try:
        series = client.goal(sc, period="billing", during=during)
    except Exception:
        _LOGGER.debug(
            "Dropcountr billing goal failed for %s",
            sc.meter_id or sc.id,
            exc_info=True,
        )
        return None
    point = _current_billing_member(list(series.members), today)
    if point is None:
        return None
    return point.gallons


def _sum_cost(
    client: DropcountrClient, sc: ServiceConnection, period: str, during: str
) -> tuple[float | None, str | None]:
    if not sc.cost_series:
        return None, None
    series = client.cost(sc, period=period, during=during)
    if not series.members:
        return 0.0, None
    total = sum(point.price for point in series.members)
    currency = series.members[0].price_currency
    return total, currency


def _sum_goal_gallons(
    client: DropcountrClient, sc: ServiceConnection, period: str, during: str
) -> float | None:
    if not sc.goal_series:
        return None
    series = client.goal(sc, period=period, during=during)
    if not series.members:
        return 0.0
    return sum(point.gallons for point in series.members)


def _pick_open_leak(leaks: list[Leak]) -> Leak | None:
    open_leaks = [leak for leak in leaks if leak.resolved_at is None]
    if not open_leaks:
        return None
    return max(open_leaks, key=lambda leak: leak.started_at or "")


def _fetch_all(
    email: str, password: str, selected_meter_ids: list[str] | None
) -> dict[str, MeterSnapshot]:
    """Fetch usage/cost/goal, stats, and open leak status for selected meters."""
    client = DropcountrClient(email=email, password=password)
    include = set(selected_meter_ids or [])

    try:
        login = client.login()
        if login.status_code >= 400:
            raise ConfigEntryAuthFailed("Invalid Dropcountr credentials")

        user = client.me()
        snapshots: dict[str, MeterSnapshot] = {}

        for premise_ref in user.premises:
            premise = client.premise(premise_ref.id)

            for sc in premise.service_connections:
                meter_id = sc.meter_id or sc.id
                if include and meter_id not in include:
                    continue

                try:
                    snapshots[meter_id] = _fetch_meter_snapshot(
                        client,
                        sc,
                        premise=premise,
                    )
                except Exception:
                    _LOGGER.exception(
                        "Dropcountr update failed for meter %s; skipping", meter_id
                    )

        if not snapshots:
            raise UpdateFailed("No Dropcountr meters could be updated")

        return snapshots
    finally:
        try:
            client.logout()
        except Exception:
            _LOGGER.debug("Dropcountr logout failed", exc_info=True)
        client.close()


def _fetch_usage_stats(client: DropcountrClient, sc: ServiceConnection) -> UsageStats | None:
    if not sc.usage_stats:
        return None
    try:
        return client.usage_stats(sc)
    except Exception:
        _LOGGER.debug(
            "Dropcountr usage_stats failed for %s",
            sc.meter_id or sc.id,
            exc_info=True,
        )
        return None


def _fetch_meter_snapshot(
    client: DropcountrClient,
    sc: ServiceConnection,
    *,
    premise: Premise,
) -> MeterSnapshot:
    """Fetch one meter snapshot."""
    meter_id = sc.meter_id or sc.id
    premise_name = premise.name or premise.id
    today = _local_today(sc.timezone)
    yesterday = today - timedelta(days=1)
    day_during = _exclusive_day_during(today)
    yesterday_during = _exclusive_day_during(yesterday)
    week_during = _exclusive_week_during(today)
    month_during = _exclusive_month_during(today)
    leaks_during = _exclusive_last_7_days(today)
    billing_during = _exclusive_billing_query(today)

    stats = _fetch_usage_stats(client, sc)

    day = _fetch_usage(client, sc, "day", day_during)
    yesterday_usage = _fetch_usage(client, sc, "day", yesterday_during)
    week = _fetch_usage(client, sc, "week", week_during)
    month = _fetch_usage(client, sc, "month", month_during)
    hour = _fetch_hour_usage(client, sc, day_during)
    billing = _fetch_billing_usage(client, sc, billing_during, today)

    day_cost, day_currency = _sum_cost(client, sc, "day", day_during)
    week_cost, week_currency = _sum_cost(client, sc, "week", week_during)
    month_cost, month_currency = _sum_cost(client, sc, "month", month_during)
    billing_cost, billing_currency = _fetch_billing_cost(
        client, sc, billing_during, today
    )
    cost_currency = (
        day_currency or week_currency or month_currency or billing_currency
    )

    day_goal = _sum_goal_gallons(client, sc, "day", day_during)
    week_goal = _sum_goal_gallons(client, sc, "week", week_during)
    month_goal = _sum_goal_gallons(client, sc, "month", month_during)
    billing_goal = _fetch_billing_goal(client, sc, billing_during, today)

    open_leak: Leak | None = None
    if sc.leaks:
        leak_series = client.leaks(sc, during=leaks_during)
        summary = _pick_open_leak(list(leak_series.members))
        if summary:
            try:
                open_leak = client.leak(summary.id, timezone=sc.timezone)
            except Exception:
                _LOGGER.debug(
                    "Failed to refresh leak detail %s",
                    summary.id,
                    exc_info=True,
                )
                open_leak = summary

    volume = None
    hourly = None
    cost = None
    currency = None
    ignored = None
    archived = None
    if open_leak:
        ignored = open_leak.is_ignored
        archived = open_leak.is_archived
        if open_leak.est_total_volume:
            volume = open_leak.est_total_volume.value
        if open_leak.est_hourly_volume:
            hourly = open_leak.est_hourly_volume.value
        if open_leak.est_total_cost:
            cost = open_leak.est_total_cost.price
            currency = open_leak.est_total_cost.price_currency

    return MeterSnapshot(
        meter_id=meter_id,
        service_connection_id=sc.id,
        name=sc.name or meter_id,
        premise_name=premise_name,
        premise_timezone=sc.timezone,
        service_type=sc.service_type,
        read_frequency=stats.read_frequency if stats else None,
        lag=stats.lag if stats else None,
        completeness_7d=stats.completeness_7d if stats else None,
        completeness_30d=stats.completeness_30d if stats else None,
        completeness_90d=stats.completeness_90d if stats else None,
        day_gallons=day.gallons,
        yesterday_gallons=yesterday_usage.gallons,
        week_gallons=week.gallons,
        month_gallons=month.gallons,
        day_during=day.during,
        yesterday_during=yesterday_usage.during,
        week_during=week.during,
        month_during=month.during,
        day_cost=day_cost,
        week_cost=week_cost,
        month_cost=month_cost,
        cost_currency=cost_currency,
        day_goal_gallons=day_goal,
        week_goal_gallons=week_goal,
        month_goal_gallons=month_goal,
        has_open_leak=open_leak is not None,
        open_leak_id=open_leak.id if open_leak else None,
        open_leak_started_at=open_leak.started_at if open_leak else None,
        open_leak_volume=volume,
        open_leak_hourly_volume=hourly,
        open_leak_cost=cost,
        open_leak_currency=currency,
        open_leak_ignored=ignored,
        open_leak_archived=archived,
        hour_gallons=hour.gallons if hour else None,
        hour_irrigation_gallons=hour.irrigation_gallons if hour else None,
        hour_during=hour.during if hour else None,
        day_irrigation_gallons=day.irrigation_gallons,
        day_irrigation_events=day.irrigation_events,
        week_irrigation_gallons=week.irrigation_gallons,
        month_irrigation_gallons=month.irrigation_gallons,
        billing_gallons=billing.gallons if billing else None,
        billing_irrigation_gallons=billing.irrigation_gallons if billing else None,
        billing_irrigation_events=billing.irrigation_events if billing else None,
        billing_during=billing.during if billing else None,
        billing_cost=billing_cost,
        billing_goal_gallons=billing_goal,
    )


def _scan_interval(entry: ConfigEntry) -> timedelta:
    minutes = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    return timedelta(minutes=max(minutes, 1))


class DropcountrDataUpdateCoordinator(DataUpdateCoordinator[dict[str, MeterSnapshot]]):
    """Coordinator that polls Dropcountr for meter snapshots."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=_scan_interval(entry),
        )
        self.entry = entry
        self.api_health = ApiHealth(ok=False)

    async def _async_update_data(self) -> dict[str, MeterSnapshot]:
        selected = self.entry.options.get(CONF_METER_IDS) or []
        try:
            data = await self.hass.async_add_executor_job(
                _fetch_all,
                self.entry.data[CONF_EMAIL],
                self.entry.data[CONF_PASSWORD],
                list(selected),
            )
        except ConfigEntryAuthFailed as err:
            self.api_health = ApiHealth(
                ok=False,
                last_success=self.api_health.last_success,
                last_error="Authentication failed",
                meter_count=0,
            )
            raise
        except Exception as err:
            self.api_health = ApiHealth(
                ok=False,
                last_success=self.api_health.last_success,
                last_error=str(err),
                meter_count=len(self.data) if self.data else 0,
            )
            raise UpdateFailed(f"Error communicating with Dropcountr: {err}") from err

        self.api_health = ApiHealth(
            ok=True,
            last_success=datetime.now(timezone.utc),
            last_error=None,
            meter_count=len(data),
        )
        return data
