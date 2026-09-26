"""Coordinator that downloads SnoPUD usage and imports it as statistics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter, VolumeConverter

from .api import (
    Bill,
    CannotConnect,
    ExtraLoginStep,
    InvalidAuth,
    PortalError,
    Property,
    ServiceType,
    SnoPUDClient,
    price_reads,
)
from .const import (
    BACKFILL_DAYS,
    DOMAIN,
    OVERLAP_DAYS,
    PORTAL_TIME_ZONE,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type SnoPUDConfigEntry = ConfigEntry[SnoPUDCoordinator]

SERVICE_KEYS = {ServiceType.ELECTRIC: "electric", ServiceType.WATER: "water"}
SERVICE_NAMES = {ServiceType.ELECTRIC: "electricity", ServiceType.WATER: "water"}


@dataclass
class SnoPUDData:
    """Data for the sensors."""

    property: Property
    # Start of the newest hour of data, per service.
    last_reading: dict[ServiceType, datetime | None] = field(default_factory=dict)


def statistic_id(property_id: str, service: ServiceType, kind: str) -> str:
    """Return the external statistic ID, for example snopud:123_electric_cost."""
    return f"{DOMAIN}:{property_id}_{SERVICE_KEYS[service]}_{kind}"


class SnoPUDCoordinator(DataUpdateCoordinator[SnoPUDData]):
    """Log in, download hourly usage, and write it to long-term statistics."""

    config_entry: SnoPUDConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: SnoPUDConfigEntry) -> None:
        """Create the portal client with a session of its own."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = SnoPUDClient(
            async_create_clientsession(hass),
            config_entry.data[CONF_USERNAME],
            config_entry.data[CONF_PASSWORD],
        )
        self._tz: tzinfo | None = None

    async def _async_update_data(self) -> SnoPUDData:
        """Log in, then import each service."""
        if self._tz is None:
            self._tz = await dt_util.async_get_time_zone(PORTAL_TIME_ZONE)
        try:
            # Updates are hours apart, so start each one with a new login.
            await self.api.async_login()
            if not self.api.properties:
                raise UpdateFailed("No property found on the portal dashboard")
            prop = self.api.properties[0]
            data = SnoPUDData(property=prop)
            for service in ServiceType:
                data.last_reading[service] = await self._import_service(prop, service)
        except (InvalidAuth, ExtraLoginStep) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (CannotConnect, PortalError) as err:
            raise UpdateFailed(str(err)) from err
        return data

    async def _import_service(
        self, prop: Property, service: ServiceType
    ) -> datetime | None:
        """Download one service and write its statistics.

        Return the start of the newest hour. The first run imports
        BACKFILL_DAYS of history. Later runs download again from OVERLAP_DAYS
        before the newest statistic and rewrite those hours, so that the
        portal's late corrections replace the old values.
        """
        assert self._tz is not None
        consumption_id = statistic_id(prop.id, service, "consumption")
        cost_id = statistic_id(prop.id, service, "cost")
        recorder = get_instance(self.hass)

        last = await recorder.async_add_executor_job(
            get_last_statistics, self.hass, 1, consumption_id, True, set()
        )
        today = dt_util.now(self._tz).date()
        if last:
            last_start = dt_util.utc_from_timestamp(last[consumption_id][0]["start"])
            first_day = last_start.astimezone(self._tz).date() - timedelta(
                days=OVERLAP_DAYS
            )
        else:
            last_start = None
            first_day = today - timedelta(days=BACKFILL_DAYS)

        # The water CSV has no cost, so water cost comes from the bills.
        bills: list[Bill] = []
        if service is ServiceType.WATER:
            try:
                bills = await self.api.async_get_bills(service)
            except PortalError as err:
                _LOGGER.warning("Water cost is not available: %s", err)
        if bills and last:
            has_cost = await recorder.async_add_executor_job(
                get_last_statistics, self.hass, 1, cost_id, True, set()
            )
            if not has_cost:
                # The cost statistic is new: import its full history.
                first_day = today - timedelta(days=BACKFILL_DAYS)
            else:
                # Hours after the previous bill used an estimated rate. Price
                # them again now that their bill can be closed.
                first_day = min(first_day, bills[-1].start)

        reads = await self.api.async_get_usage(service, first_day, today, self._tz)
        if not reads:
            _LOGGER.debug("No %s usage since %s", SERVICE_KEYS[service], first_day)
            return last_start
        reads = price_reads(reads, bills, self._tz)

        # The running sums continue from the newest statistic before the window.
        sums = {consumption_id: 0.0, cost_id: 0.0}
        if last:
            window_start = reads[0].start
            before = await recorder.async_add_executor_job(
                statistics_during_period,
                self.hass,
                window_start - timedelta(days=30),
                window_start,
                set(sums),
                "hour",
                None,
                {"sum"},
            )
            for stat_id, rows in before.items():
                if rows and rows[-1].get("sum") is not None:
                    sums[stat_id] = float(rows[-1]["sum"])

        consumption: list[StatisticData] = []
        cost: list[StatisticData] = []
        for read in reads:
            sums[consumption_id] += read.consumption
            consumption.append(
                StatisticData(
                    start=read.start, state=read.consumption, sum=sums[consumption_id]
                )
            )
            if read.cost is not None:
                sums[cost_id] += read.cost
                cost.append(
                    StatisticData(start=read.start, state=read.cost, sum=sums[cost_id])
                )

        name = f"SnoPUD {prop.name} {SERVICE_NAMES[service]}"
        is_electric = service is ServiceType.ELECTRIC
        _LOGGER.debug("Adding %d statistics for %s", len(consumption), consumption_id)
        async_add_external_statistics(
            self.hass,
            StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=f"{name} consumption",
                source=DOMAIN,
                statistic_id=consumption_id,
                unit_class=(
                    EnergyConverter.UNIT_CLASS
                    if is_electric
                    else VolumeConverter.UNIT_CLASS
                ),
                unit_of_measurement=(
                    UnitOfEnergy.KILO_WATT_HOUR
                    if is_electric
                    else UnitOfVolume.CUBIC_FEET
                ),
            ),
            consumption,
        )
        if cost:
            _LOGGER.debug("Adding %d statistics for %s", len(cost), cost_id)
            async_add_external_statistics(
                self.hass,
                StatisticMetaData(
                    mean_type=StatisticMeanType.NONE,
                    has_sum=True,
                    name=f"{name} cost",
                    source=DOMAIN,
                    statistic_id=cost_id,
                    unit_class=None,
                    unit_of_measurement=None,
                ),
                cost,
            )
        return reads[-1].start
