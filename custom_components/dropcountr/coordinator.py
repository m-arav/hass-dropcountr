"""DataUpdateCoordinator for Dropcountr."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import logging

from dropcountr import DropcountrClient
from dropcountr.models import Leak, ServiceConnection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeterSnapshot:
    """Polled state for one service connection (meter)."""

    meter_id: str
    service_connection_id: str
    name: str
    premise_name: str
    service_type: str | None
    week_gallons: float
    month_gallons: float
    has_open_leak: bool
    open_leak_id: str | None = None
    open_leak_started_at: str | None = None
    open_leak_volume: float | None = None
    open_leak_cost: float | None = None
    open_leak_currency: str | None = None


def _monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


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


def _sum_usage_gallons(client: DropcountrClient, sc: ServiceConnection, period: str, during: str) -> float:
    if not sc.usage_series:
        return 0.0
    series = client.usage(sc.usage_series.template, period=period, during=during)
    return sum(point.total_gallons for point in series.members)


def _pick_open_leak(leaks: list[Leak]) -> Leak | None:
    open_leaks = [leak for leak in leaks if leak.resolved_at is None]
    if not open_leaks:
        return None
    return max(open_leaks, key=lambda leak: leak.started_at or "")


def _fetch_all(email: str, password: str) -> dict[str, MeterSnapshot]:
    """Fetch week/month usage and open leak status for every meter."""
    client = DropcountrClient(email=email, password=password)
    today = date.today()
    week_during = _exclusive_week_during(today)
    month_during = _exclusive_month_during(today)
    leaks_during = _exclusive_last_7_days(today)

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
                week_gallons = _sum_usage_gallons(client, sc, "week", week_during)
                month_gallons = _sum_usage_gallons(client, sc, "month", month_during)

                open_leak: Leak | None = None
                if sc.leaks:
                    leak_series = client.leaks(sc.leaks.template, during=leaks_during)
                    open_leak = _pick_open_leak(list(leak_series.members))

                volume = None
                cost = None
                currency = None
                if open_leak and open_leak.est_total_volume:
                    volume = open_leak.est_total_volume.value
                if open_leak and open_leak.est_total_cost:
                    cost = open_leak.est_total_cost.price
                    currency = open_leak.est_total_cost.price_currency

                snapshots[meter_id] = MeterSnapshot(
                    meter_id=meter_id,
                    service_connection_id=sc.id,
                    name=sc.name or meter_id,
                    premise_name=premise_name,
                    service_type=sc.service_type,
                    week_gallons=week_gallons,
                    month_gallons=month_gallons,
                    has_open_leak=open_leak is not None,
                    open_leak_id=open_leak.id if open_leak else None,
                    open_leak_started_at=open_leak.started_at if open_leak else None,
                    open_leak_volume=volume,
                    open_leak_cost=cost,
                    open_leak_currency=currency,
                )

        return snapshots
    finally:
        try:
            client.logout()
        except Exception:
            _LOGGER.debug("Dropcountr logout failed", exc_info=True)
        client.close()


class DropcountrDataUpdateCoordinator(DataUpdateCoordinator[dict[str, MeterSnapshot]]):
    """Coordinator that polls Dropcountr for meter snapshots."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry

    async def _async_update_data(self) -> dict[str, MeterSnapshot]:
        try:
            return await self.hass.async_add_executor_job(
                _fetch_all,
                self.entry.data[CONF_EMAIL],
                self.entry.data[CONF_PASSWORD],
            )
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Dropcountr: {err}") from err
