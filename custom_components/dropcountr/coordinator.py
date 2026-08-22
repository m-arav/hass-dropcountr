"""DataUpdateCoordinator for Dropcountr."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging

from dropcountr import DropcountrClient
from dropcountr.models import Leak, ServiceConnection
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
    service_type: str | None
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
) -> tuple[float, str | None]:
    """Return total gallons and the server-aligned during interval."""
    if not sc.usage_series:
        return 0.0, None
    series = client.usage(sc.usage_series.template, period=period, during=during)
    total = sum(point.total_gallons for point in series.members)
    return total, _server_during_from_members(list(series.members))


def _sum_cost(
    client: DropcountrClient, sc: ServiceConnection, period: str, during: str
) -> tuple[float | None, str | None]:
    if not sc.cost_series:
        return None, None
    series = client.cost(sc.cost_series.template, period=period, during=during)
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
    series = client.goal(sc.goal_series.template, period=period, during=during)
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
    """Fetch usage/cost/goal and open leak status for selected meters."""
    client = DropcountrClient(email=email, password=password)
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_during = _exclusive_day_during(today)
    yesterday_during = _exclusive_day_during(yesterday)
    week_during = _exclusive_week_during(today)
    month_during = _exclusive_month_during(today)
    leaks_during = _exclusive_last_7_days(today)
    include = set(selected_meter_ids or [])

    try:
        login = client.login()
        if login.status_code >= 400:
            raise ConfigEntryAuthFailed("Invalid Dropcountr credentials")

        user = client.me()
        snapshots: dict[str, MeterSnapshot] = {}

        for premise_ref in user.premises:
            premise = client.premise(premise_ref.id)
            premise_name = premise.name or premise.id

            for sc in premise.service_connections:
                meter_id = sc.meter_id or sc.id
                if include and meter_id not in include:
                    continue

                try:
                    snapshots[meter_id] = _fetch_meter_snapshot(
                        client,
                        sc,
                        premise_name=premise_name,
                        day_during=day_during,
                        yesterday_during=yesterday_during,
                        week_during=week_during,
                        month_during=month_during,
                        leaks_during=leaks_during,
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


def _fetch_meter_snapshot(
    client: DropcountrClient,
    sc: ServiceConnection,
    *,
    premise_name: str,
    day_during: str,
    yesterday_during: str,
    week_during: str,
    month_during: str,
    leaks_during: str,
) -> MeterSnapshot:
    """Fetch one meter snapshot."""
    meter_id = sc.meter_id or sc.id

    day_gallons, day_server_during = _fetch_usage(client, sc, "day", day_during)
    yesterday_gallons, yesterday_server_during = _fetch_usage(
        client, sc, "day", yesterday_during
    )
    week_gallons, week_server_during = _fetch_usage(client, sc, "week", week_during)
    month_gallons, month_server_during = _fetch_usage(
        client, sc, "month", month_during
    )

    day_cost, day_currency = _sum_cost(client, sc, "day", day_during)
    week_cost, week_currency = _sum_cost(client, sc, "week", week_during)
    month_cost, month_currency = _sum_cost(client, sc, "month", month_during)
    cost_currency = day_currency or week_currency or month_currency

    day_goal = _sum_goal_gallons(client, sc, "day", day_during)
    week_goal = _sum_goal_gallons(client, sc, "week", week_during)
    month_goal = _sum_goal_gallons(client, sc, "month", month_during)

    open_leak: Leak | None = None
    if sc.leaks:
        leak_series = client.leaks(sc.leaks.template, during=leaks_during)
        summary = _pick_open_leak(list(leak_series.members))
        if summary:
            try:
                open_leak = client.leak(summary.id)
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
        service_type=sc.service_type,
        day_gallons=day_gallons,
        yesterday_gallons=yesterday_gallons,
        week_gallons=week_gallons,
        month_gallons=month_gallons,
        day_during=day_server_during,
        yesterday_during=yesterday_server_during,
        week_during=week_server_during,
        month_during=month_server_during,
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
