"""Tests for the statistics import."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.snopud.api import (
    CannotConnect,
    InvalidAuth,
    Property,
    ServiceType,
    UsageRead,
)
from custom_components.snopud.const import DOMAIN

CLIENT = "custom_components.snopud.coordinator.SnoPUDClient"
ELEC = "snopud:2000002_electric_consumption"
ELEC_COST = "snopud:2000002_electric_cost"
WATER = "snopud:2000002_water_consumption"


def hours(start: datetime, values: list[float], cost: bool) -> list[UsageRead]:
    """Build hourly reads."""
    return [
        UsageRead(
            start=start + timedelta(hours=i),
            consumption=v,
            cost=round(v / 10, 2) if cost else None,
        )
        for i, v in enumerate(values)
    ]


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "pw"},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def client():
    """A mocked portal client with one property."""
    with patch(CLIENT, autospec=True) as cls:
        api = cls.return_value
        api.properties = [Property(id="2000002", name="Main House")]
        yield api


async def _stats(hass: HomeAssistant, ids: set[str]) -> dict:
    await async_wait_recording_done(hass)
    return await hass.async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(2026, 1, 1, tzinfo=UTC),
        None,
        ids,
        "hour",
        None,
        {"state", "sum"},
    )


async def test_first_import_then_update(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The first run backfills. The next run rewrites the overlap from the right sum."""
    freezer.move_to("2026-09-25 20:00:00+00:00")
    start = datetime(2026, 9, 20, 7, tzinfo=UTC)  # midnight local time
    usage = {
        ServiceType.ELECTRIC: hours(start, [1.0] * 48, cost=True),
        ServiceType.WATER: hours(start, [2.0] * 48, cost=False),
    }
    client.async_get_usage = AsyncMock(side_effect=lambda s, *a: usage[s])

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    first = client.async_get_usage.call_args_list[0].args
    assert first[1:3] == (date(2025, 9, 25), date(2026, 9, 25))

    stats = await _stats(hass, {ELEC, ELEC_COST, WATER})
    assert len(stats[ELEC]) == 48
    assert stats[ELEC][-1]["sum"] == pytest.approx(48.0)
    assert stats[ELEC_COST][-1]["sum"] == pytest.approx(4.8)
    assert stats[WATER][-1]["sum"] == pytest.approx(96.0)
    assert "snopud:2000002_water_cost" not in stats

    state = hass.states.get("sensor.snopud_main_house_latest_electricity_reading")
    assert state is not None
    assert datetime.fromisoformat(state.state) == start + timedelta(hours=47)

    # The portal corrects the second day and adds a third day.
    usage[ServiceType.ELECTRIC] = hours(
        start + timedelta(hours=24), [3.0] * 48, cost=True
    )
    usage[ServiceType.WATER] = []
    client.async_get_usage.reset_mock()
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    elec_call = client.async_get_usage.call_args_list[0].args
    # Newest hour is 2026-09-21 23:00 local, so the overlap starts 3 days before.
    assert elec_call[1:3] == (date(2026, 9, 18), date(2026, 9, 25))

    stats = await _stats(hass, {ELEC, WATER})
    assert len(stats[ELEC]) == 72
    assert stats[ELEC][23]["sum"] == pytest.approx(24.0)
    assert stats[ELEC][24]["state"] == pytest.approx(3.0)
    assert stats[ELEC][-1]["sum"] == pytest.approx(24.0 + 48 * 3.0)
    assert len(stats[WATER]) == 48


async def test_auth_failure_starts_reauth(
    recorder_mock: Recorder, hass: HomeAssistant, entry: MockConfigEntry, client
) -> None:
    """A rejected password starts the reauth flow and does not retry."""
    client.async_login.side_effect = InvalidAuth("bad")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_connection_failure_retries_later(
    recorder_mock: Recorder, hass: HomeAssistant, entry: MockConfigEntry, client
) -> None:
    """A network error leaves the entry to retry setup."""
    client.async_login.side_effect = CannotConnect("down")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
