"""Tests for the portal client."""

from datetime import UTC, date, datetime
import json
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.snopud.api import (
    Bill,
    CannotConnect,
    ExtraLoginStep,
    InvalidAuth,
    PortalError,
    ServiceType,
    SessionExpired,
    SnoPUDClient,
    UsageRead,
    form_fields,
    parse_ajax,
    parse_bill_series,
    parse_properties,
    parse_usage_csv,
    price_reads,
)

from .conftest import BASE, load, mock_login

TZ = ZoneInfo("America/Los_Angeles")


def test_parse_ajax() -> None:
    """The wrapper splits into HTML, redirect and data."""
    assert parse_ajax(load("login_ok.json")) == (
        "",
        "https://my.snopud.com/Integration/LoginActions",
        {},
    )
    assert parse_ajax(load("login_bad.json"))[2] == {
        "LoginErrorMessage": "Invalid email address or password"
    }
    assert parse_ajax("plain text") == ("plain text", None, {})
    assert parse_ajax('{"AjaxResults":[],"Data":null}') == ("", None, {})


def test_form_fields_like_a_browser() -> None:
    """Unchecked boxes, buttons and disabled-looking extras follow browser rules."""
    html, _, _ = parse_ajax(load("download_form_water.json"))
    fields = form_fields(html, "/Usage/Download")
    names = [k for k, _ in fields]
    assert "Meters[0].Selected" not in names
    assert ["Meters[1].Selected", "true"] in fields
    assert ["SelectedServiceType", "2"] in fields
    assert ["SelectedInterval", "6"] in fields
    assert ["Start", "2026-01-01"] in fields
    assert names.count("ColumnOptions[0].Checked") == 2


def test_parse_properties_current_first() -> None:
    """The selected property comes first, with its name trimmed."""
    props = parse_properties(load("dashboard.html"))
    assert [(p.id, p.name) for p in props] == [
        ("2000002", "Main House"),
        ("2000001", "Cabin"),
    ]


def test_parse_electric_csv_dst_fall_back() -> None:
    """The 1 AM row on the fall-back day is the standard-time hour."""
    reads = parse_usage_csv(load("usage_electric.csv"), TZ)
    assert [r.start.astimezone(UTC) for r in reads] == [
        datetime(2025, 11, 2, 6, tzinfo=UTC),
        datetime(2025, 11, 2, 7, tzinfo=UTC),
        datetime(2025, 11, 2, 9, tzinfo=UTC),
        datetime(2025, 11, 2, 10, tzinfo=UTC),
    ]
    assert [r.consumption for r in reads] == [1.0, 2.0, 3.0, 4.0]
    assert [r.cost for r in reads] == [0.1, 0.2, 0.3, 0.4]


def test_parse_water_csv_sums_meters() -> None:
    """Rows for the same hour from two meters add up. Blank values drop."""
    reads = parse_usage_csv(load("usage_water.csv"), TZ)
    assert [(r.start.astimezone(UTC), r.consumption, r.cost) for r in reads] == [
        (datetime(2026, 3, 8, 9, tzinfo=UTC), 0.75, None),
        (datetime(2026, 3, 8, 10, tzinfo=UTC), 1.0, None),
    ]


def test_parse_csv_bad_columns() -> None:
    """A CSV without a usage column is an error."""
    with pytest.raises(PortalError):
        parse_usage_csv("Start,Other\r\n", TZ)


async def test_login(hass: HomeAssistant, aioclient_mock) -> None:
    """A good login reads the properties and never sends the password twice."""
    mock_login(aioclient_mock)
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "pw")
    await client.async_login()
    assert [p.id for p in client.properties] == ["2000002", "2000001"]
    login_call = aioclient_mock.mock_calls[1]
    assert login_call[2]["__RequestVerificationToken"] == "test-csrf-token"
    assert login_call[2]["LoginPassword"] == "pw"


async def test_login_invalid(hass: HomeAssistant, aioclient_mock) -> None:
    """The portal's error message becomes InvalidAuth."""
    mock_login(aioclient_mock, "login_bad.json")
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "x")
    with pytest.raises(InvalidAuth):
        await client.async_login()


async def test_login_extra_step(hass: HomeAssistant, aioclient_mock) -> None:
    """No error and no redirect means an extra step, such as two-factor."""
    aioclient_mock.get(f"{BASE}/", text=load("login_page.html"))
    aioclient_mock.post(
        f"{BASE}/Home/Login",
        text='{"AjaxResults":[{"Action":"Replace","Value":"<form></form>"}],"Data":null}',
    )
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "x")
    with pytest.raises(ExtraLoginStep):
        await client.async_login()


async def test_login_lands_on_login_page(hass: HomeAssistant, aioclient_mock) -> None:
    """A dashboard request that shows the login form is an error."""
    aioclient_mock.get(f"{BASE}/", text=load("login_page.html"))
    aioclient_mock.post(f"{BASE}/Home/Login", text=load("login_ok.json"))
    aioclient_mock.get(f"{BASE}/Integration/LoginActions", text="")
    aioclient_mock.get(f"{BASE}/Dashboard", text=load("login_page.html"))
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "x")
    with pytest.raises(PortalError):
        await client.async_login()


async def test_get_usage(hass: HomeAssistant, aioclient_mock) -> None:
    """The client switches service, selects every meter, and parses the CSV."""
    aioclient_mock.get(
        f"{BASE}/Usage/InitializeDownloadSettings",
        text=load("download_form_water.json"),
    )
    aioclient_mock.post(
        f"{BASE}/Usage/UpdateDownloadSettings",
        text=load("download_form_electric.json"),
    )
    aioclient_mock.post(
        f"{BASE}/Usage/PresentDownloadErrors", text='{"AjaxResults":[],"Data":null}'
    )
    aioclient_mock.post(
        f"{BASE}/Usage/Download",
        text=load("usage_electric.csv"),
        headers={"Content-Type": "text/csv"},
    )
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "x")
    reads = await client.async_get_usage(
        ServiceType.ELECTRIC, date(2025, 11, 1), date(2025, 11, 2), TZ
    )
    assert len(reads) == 4

    switch = dict(aioclient_mock.mock_calls[1][2])
    assert switch["SelectedServiceType"] == "1"
    sent = aioclient_mock.mock_calls[3][2]
    fields = dict(reversed(sent))  # first value wins, as in ASP.NET
    assert fields["Meters[0].Selected"] == "true"
    assert fields["Meters[1].Selected"] == "true"
    assert fields["Meters[0].Value"] == "1000003"
    assert fields["SelectedServiceType"] == "1"
    assert fields["SelectedFormat"] == "2"
    assert fields["SelectedInterval"] == "5"
    assert fields["SelectedUsageType"] == "1"
    assert fields["FileFormat"] == "download-usage-csv"
    assert (fields["Start"], fields["End"]) == ("2025-11-01", "2025-11-02")
    assert fields["__RequestVerificationToken"] == "test-form-token"


async def test_get_usage_session_expired(hass: HomeAssistant, aioclient_mock) -> None:
    """A redirect to the login page raises SessionExpired."""
    aioclient_mock.get(
        f"{BASE}/Usage/InitializeDownloadSettings", text=load("session_expired.json")
    )
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "x")
    with pytest.raises(SessionExpired):
        await client.async_get_usage(
            ServiceType.WATER, date(2026, 1, 1), date(2026, 1, 2), TZ
        )


async def test_get_usage_portal_rejects(hass: HomeAssistant, aioclient_mock) -> None:
    """A validation message from the portal raises PortalError."""
    aioclient_mock.get(
        f"{BASE}/Usage/InitializeDownloadSettings",
        text=load("download_form_water.json"),
    )
    aioclient_mock.post(
        f"{BASE}/Usage/PresentDownloadErrors",
        text=(
            '{"AjaxResults":[{"Action":"Replace","Value":"<p>Bad range</p>"}],'
            '"Data":null}'
        ),
    )
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "x")
    with pytest.raises(PortalError, match="Bad range"):
        await client.async_get_usage(
            ServiceType.WATER, date(2026, 1, 1), date(2026, 1, 2), TZ
        )


class FakeChart:
    """The portal's Charts view, which saves its settings for the account."""

    def __init__(self, service: str, interval: str, usage_type: str) -> None:
        """Start with the view that the user left."""
        self.service, self.interval, self.usage_type = service, interval, usage_type

    def register(self, aioclient_mock) -> None:
        """Answer the chart requests from the current state."""
        aioclient_mock.get(f"{BASE}/Dashboard/Chart", side_effect=self._page)
        aioclient_mock.post(f"{BASE}/Dashboard/Chart/", side_effect=self._change)
        aioclient_mock.get(f"{BASE}/Dashboard/ChartData", side_effect=self._data)
        aioclient_mock.get(
            f"{BASE}/Dashboard/SetServiceType", side_effect=self._set_service
        )

    async def _page(self, method, url, data):
        html = load("chart_page.html")
        for key, current in (
            ("SERVICE_", self.service),
            ("INTERVAL_", self.interval),
            ("TYPE_", self.usage_type),
        ):
            for value in ("1", "2", "3", "5", "6", "7"):
                marker = "current" if key == "SERVICE_" else "selected"
                html = html.replace(f"{key}{value}", marker if value == current else "")
        wrapper = {"AjaxResults": [{"Action": "Replace", "Value": html}], "Data": None}
        return AiohttpClientMockResponse(method, url, text=json.dumps(wrapper))

    async def _change(self, method, url, data):
        fields = dict(reversed(data))
        self.interval = fields["UsageInterval"]
        # Like the portal: dollars exist only for billing periods.
        self.usage_type = fields["UsageType"] if self.interval == "7" else "1"
        return AiohttpClientMockResponse(method, url, text='{"AjaxResults":[]}')

    async def _data(self, method, url, data):
        name = "dollar" if self.usage_type == "3" else "consumption"
        return AiohttpClientMockResponse(
            method, url, text=load(f"chart_data_{name}.json")
        )

    async def _set_service(self, method, url, data):
        self.service = url.query["ServiceType"]
        return AiohttpClientMockResponse(method, url, status=302)


@pytest.mark.parametrize("start_service", ["1", "2"])
async def test_get_bills_restores_chart(
    hass: HomeAssistant, aioclient_mock, start_service: str
) -> None:
    """Bills come from the billing chart, and the user's view comes back."""
    chart = FakeChart(start_service, "6", "1")
    chart.register(aioclient_mock)
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "x")
    bills = await client.async_get_bills(ServiceType.WATER)
    assert bills == [
        Bill(date(2026, 1, 6), date(2026, 2, 5), 50.0, 1000.0),
        Bill(date(2026, 2, 6), date(2026, 3, 5), 30.0, 500.0),
    ]
    assert (chart.service, chart.interval, chart.usage_type) == (
        start_service,
        "6",
        "1",
    )


async def test_get_bills_restores_chart_on_error(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A failed chart request still puts the user's view back."""
    chart = FakeChart("1", "5", "1")
    chart.register(aioclient_mock)
    aioclient_mock._mocks.insert(
        0,
        AiohttpClientMockResponse(
            "get", URL(f"{BASE}/Dashboard/ChartData"), status=500
        ),
    )
    client = SnoPUDClient(async_create_clientsession(hass), "user@example.com", "x")
    with pytest.raises(CannotConnect):
        await client.async_get_bills(ServiceType.WATER)
    assert (chart.service, chart.interval, chart.usage_type) == ("1", "5", "1")


def test_parse_bill_series_checks_type() -> None:
    """The portal answers in cubic feet when it has no dollars."""
    data = json.loads(load("chart_data_consumption.json"))["Data"]
    with pytest.raises(PortalError, match="Consumption"):
        parse_bill_series(data, "Dollar")


def test_price_reads() -> None:
    """Each hour gets its bill's rate. Later hours use the last rate."""
    bills = [
        Bill(date(2026, 1, 6), date(2026, 2, 5), 50.0, 1000.0),
        Bill(date(2026, 2, 6), date(2026, 3, 5), 30.0, 500.0),
        Bill(date(2026, 3, 6), date(2026, 4, 5), 10.0, 0.0),
    ]

    def read(day: date, hour: int, cf: float) -> UsageRead:
        return UsageRead(
            datetime(day.year, day.month, day.day, hour, tzinfo=TZ), cf, None
        )

    reads = [
        read(date(2026, 1, 1), 0, 10.0),  # before the first bill
        read(date(2026, 2, 5), 23, 10.0),  # last hour of the first bill
        read(date(2026, 2, 6), 0, 10.0),  # first hour of the second bill
        read(date(2026, 3, 10), 0, 10.0),  # bill with no consumption
    ]
    costs = [r.cost for r in price_reads(reads, bills, TZ)]
    assert costs == pytest.approx([0.5, 0.5, 0.6, 0.0])
    assert price_reads(reads, [], TZ) == reads
