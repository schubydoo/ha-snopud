"""Async client for the MySnoPUD customer portal.

The portal runs on the MyMeter platform. This module has no Home Assistant
imports, so that it can move to a separate library later.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, tzinfo
from enum import StrEnum
from html.parser import HTMLParser
import io
import json
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp

from .const import DEFAULT_BASE_URL

_LOGGER = logging.getLogger(__name__)

XHR = {"X-Requested-With": "XMLHttpRequest"}
TIMEOUT = aiohttp.ClientTimeout(total=60)
HOURLY = "5"
FORMAT_CSV = "2"
USAGE_CONSUMPTION = "1"
USAGE_DOLLARS = "3"
BILLING = "7"
METER_FIELD = re.compile(r"Meters\[(\d+)\]\.Value")
CHART_FORM = re.compile(
    r'(?s)<form[^>]*class="[^"]*chartControlForm[^"]*"[^>]*>.*?</form>'
)
CHART_SERVICE = re.compile(
    r'class="current setServiceTypeChartButton"\s+data-value="(\d+)"'
)


class SnoPUDError(Exception):
    """Base error for the portal client."""


class CannotConnect(SnoPUDError):
    """The portal did not answer, or answered with a server error."""


class InvalidAuth(SnoPUDError):
    """The portal rejected the email or password."""


class ExtraLoginStep(SnoPUDError):
    """The portal asked for a step this client cannot do, such as two-factor."""


class PortalError(SnoPUDError):
    """The portal returned a page this client does not understand."""


class SessionExpired(PortalError):
    """The portal sent the client back to the login page."""


class ServiceType(StrEnum):
    """Portal service type codes."""

    ELECTRIC = "1"
    WATER = "2"


@dataclass(frozen=True)
class Property:
    """A property (meter group) on the account."""

    id: str
    name: str


@dataclass(frozen=True)
class UsageRead:
    """Usage for one interval. `start` is timezone-aware."""

    start: datetime
    consumption: float
    cost: float | None


@dataclass(frozen=True)
class Bill:
    """One closed billing period. `start` and `end` are both included."""

    start: date
    end: date
    cost: float
    consumption: float


class _FormParser(HTMLParser):
    """Collect the fields of one form the way a browser serializes them."""

    def __init__(self, action: str | None) -> None:
        super().__init__()
        self.action = action
        self.in_form = action is None
        self.fields: list[list[str]] = []
        self._select: list[Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        action = (a.get("action") or "").lower()
        if tag == "form" and self.action and action == self.action.lower():
            self.in_form = True
        if tag == "option" and self._select is not None:
            if "selected" in a or self._select[1] is None:
                self._select[1] = a.get("value") or ""
            return
        name = a.get("name")
        if not self.in_form or not name:
            return
        if tag == "input":
            kind = (a.get("type") or "text").lower()
            if kind in ("checkbox", "radio"):
                if "checked" in a:
                    value = a.get("value")
                    self.fields.append([name, "on" if value is None else value])
            elif kind not in ("submit", "button", "file", "image", "reset"):
                self.fields.append([name, a.get("value") or ""])
        elif tag == "select":
            self._select = [name, None]

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self._select is not None:
            self.fields.append([self._select[0], self._select[1] or ""])
            self._select = None
        elif tag == "form" and self.action:
            self.in_form = False


class _PropertyParser(HTMLParser):
    """Find the properties in the dashboard's "Select Property" list."""

    def __init__(self) -> None:
        super().__init__()
        self.properties: list[tuple[str, str, bool]] = []
        self._current: list[Any] | None = None
        self._in_h2 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "li" and a.get("data-property-id"):
            is_current = "current" in (a.get("class") or "").split()
            self._current = [a["data-property-id"], "", is_current]
        elif tag == "h2" and self._current is not None:
            self._in_h2 = True

    def handle_data(self, data: str) -> None:
        if self._in_h2 and self._current is not None:
            self._current[1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_h2 = False
        elif tag == "li" and self._current is not None:
            prop_id, name, is_current = self._current
            self.properties.append((prop_id, " ".join(name.split()), is_current))
            self._current = None


def form_fields(html: str, action: str | None = None) -> list[list[str]]:
    """Return the fields of the form with this action, or of all forms."""
    parser = _FormParser(action)
    parser.feed(html)
    return parser.fields


def set_field(fields: list[list[str]], name: str, value: str) -> None:
    """Set the first field with this name, or add it."""
    for field in fields:
        if field[0] == name:
            field[1] = value
            return
    fields.append([name, value])


def get_field(fields: list[list[str]], name: str) -> str | None:
    """Return the value of the first field with this name."""
    return next((v for k, v in fields if k == name), None)


def parse_ajax(text: str) -> tuple[str, str | None, dict[str, Any]]:
    """Split the portal's JSON wrapper into (html, redirect, data).

    The wrapper looks like
    {"AjaxResults": [{"Action": "Replace", "Value": "<html>"}], "Data": null}.
    Text that is not JSON comes back as the HTML.
    """
    try:
        body = json.loads(text)
    except ValueError:
        return text, None, {}
    if not isinstance(body, dict):
        return text, None, {}
    html, redirect = [], None
    for result in body.get("AjaxResults") or []:
        if result.get("Action") == "Redirect":
            redirect = result.get("Value")
        else:
            html.append(result.get("Value") or "")
    return "".join(html), redirect, body.get("Data") or {}


def parse_properties(html: str) -> list[Property]:
    """Return the properties on the dashboard, the selected one first."""
    parser = _PropertyParser()
    parser.feed(html)
    ordered = sorted(parser.properties, key=lambda p: not p[2])
    return [Property(id=p[0], name=p[1] or p[0]) for p in ordered]


def _number(text: str) -> float | None:
    text = text.strip().replace("$", "").replace(",", "")
    if not text:
        return None
    return float(text)


def parse_usage_csv(text: str, tz: tzinfo) -> list[UsageRead]:
    """Parse a usage CSV into reads sorted by start time.

    The consumption column is `kWh` or `CF`. The `$` column is optional. Rows
    that share a start time (one per meter) are summed.

    Timestamps are local wall-clock times. On the fall-back daylight saving
    day the portal leaves out the first 1 AM hour, and its 1 AM row is the
    second one (standard time). Green Button data from the same portal shows
    this. So `fold=1` picks the correct instant.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    columns = reader.fieldnames or []
    usage_col = next((c for c in columns if c in ("kWh", "CF")), None)
    if "Start" not in columns or usage_col is None:
        raise PortalError(f"Unexpected CSV columns: {columns}")
    cost_col = "$" if "$" in columns else None
    totals: dict[datetime, list[float | None]] = {}
    for row in reader:
        usage = _number(row.get(usage_col) or "")
        if usage is None:
            continue
        cost = _number(row.get(cost_col) or "") if cost_col else None
        local = datetime.strptime(row["Start"].strip(), "%m/%d/%Y %I:%M:%S %p")
        start = local.replace(tzinfo=tz, fold=1)
        if start in totals:
            total = totals[start]
            total[0] = (total[0] or 0.0) + usage
            if cost is not None:
                total[1] = (total[1] or 0.0) + cost
        else:
            totals[start] = [usage, cost]
    return [
        UsageRead(start=start, consumption=v[0] or 0.0, cost=v[1])
        for start, v in sorted(totals.items())
    ]


def parse_bill_series(data: dict[str, Any], usage_type: str) -> dict[int, Any]:
    """Return {x: point} for the billing chart's data series.

    `data` is the `Data` object of a /Dashboard/ChartData response. The
    first series is the range navigator. The second one holds one point
    per billing period, keyed by `x`, with the period dates in `hs`.
    `usage_type` is "Dollar" or "Consumption". The portal falls back to
    consumption for intervals that have no dollars, so the value is
    checked.
    """
    if data.get("usageType") != usage_type:
        raise PortalError(f"Chart returned {data.get('usageType')!r}, not {usage_type}")
    series = data.get("series") or []
    if len(series) < 2:
        raise PortalError("Chart data has no billing series")
    return {
        point["x"]: point
        for point in series[1].get("data") or []
        if isinstance(point, dict) and point.get("y") is not None
    }


def parse_bills(dollars: dict[int, Any], usage: dict[int, Any]) -> list[Bill]:
    """Join the dollar and consumption series into bills, oldest first."""
    bills = []
    for x, point in sorted(dollars.items()):
        if x not in usage or "hs" not in point:
            continue
        bills.append(
            Bill(
                start=datetime.strptime(point["hs"]["start"], "%m/%d/%Y").date(),
                end=datetime.strptime(point["hs"]["end"], "%m/%d/%Y").date(),
                cost=float(point["y"]),
                consumption=float(usage[x]["y"]),
            )
        )
    return bills


def price_reads(
    reads: list[UsageRead], bills: list[Bill], tz: tzinfo
) -> list[UsageRead]:
    """Give each read a cost from the rate of its bill.

    The rate is bill cost / bill consumption, so the hourly costs of a
    closed bill add up to that bill. A read uses the newest bill that
    starts on or before its local day. Reads after the last bill use the
    last rate until the next bill arrives. Reads before the first bill use
    the first rate.
    """
    if not bills:
        return reads
    rates = [(b.start, b.cost / b.consumption if b.consumption else 0.0) for b in bills]
    priced = []
    for read in reads:
        day = read.start.astimezone(tz).date()
        rate = next((r for start, r in reversed(rates) if start <= day), rates[0][1])
        priced.append(replace(read, cost=read.consumption * rate))
    return priced


class SnoPUDClient:
    """Log in to the portal and download usage.

    Give the client its own `aiohttp.ClientSession` with its own cookie jar.
    The portal keeps the login in cookies.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        """Store the session and the credentials."""
        self._session = session
        self._username = username
        self._password = password
        self._base = base_url.rstrip("/")
        self._properties: list[Property] = []

    @property
    def properties(self) -> list[Property]:
        """Properties found at the last login, the selected one first."""
        return self._properties

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> tuple[str, str, str]:
        """Send a request. Return (final URL, content type, body text)."""
        url = urljoin(self._base + "/", path)
        try:
            async with self._session.request(
                method, url, timeout=TIMEOUT, **kwargs
            ) as resp:
                text = await resp.text()
                if resp.status >= 500:
                    raise CannotConnect(f"{method} {path}: HTTP {resp.status}")
                if resp.status >= 400:
                    raise PortalError(f"{method} {path}: HTTP {resp.status}")
                return str(resp.url), resp.headers.get("Content-Type", ""), text
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(f"{method} {path}: {err!r}") from err

    async def _ajax(
        self, method: str, path: str, **kwargs: Any
    ) -> tuple[str, dict[str, Any]]:
        """Send an XHR request. Return the HTML and the data of the wrapper."""
        _, _, text = await self._request(method, path, headers=XHR, **kwargs)
        html, redirect, data = parse_ajax(text)
        if redirect is not None and urlsplit(redirect).path in ("", "/"):
            raise SessionExpired(f"{path}: the portal asked for a new login")
        return html, data

    async def async_login(self) -> None:
        """Log in and read the property list from the dashboard."""
        _, _, home = await self._request("GET", "/")
        token = get_field(form_fields(home), "__RequestVerificationToken")
        if not token:
            raise PortalError("Login page has no __RequestVerificationToken")
        form = {
            "RedirectUrl": "",
            "LoginErrorMessage": "",
            "LoginEmail": self._username,
            "LoginPassword": self._password,
            "ExternalLogin": "False",
            "TwoFactorRendered": "False",
            "SecretQuestionRendered": "False",
            "__RequestVerificationToken": token,
        }
        _, _, text = await self._request(
            "POST",
            "/Home/Login",
            data=form,
            headers={**XHR, "Referer": self._base + "/"},
        )
        _, redirect, data = parse_ajax(text)
        if message := data.get("LoginErrorMessage"):
            raise InvalidAuth(message)
        if redirect is None:
            # No error and no redirect: the portal wants another step, most
            # likely a two-factor code or a security question.
            raise ExtraLoginStep("The portal asked for an extra login step")
        # A browser follows the redirect (/Integration/LoginActions), which
        # ends on the dashboard.
        target = urljoin(self._base + "/", redirect)
        if urlsplit(target).netloc != urlsplit(self._base).netloc:
            target = self._base + "/Dashboard"
        url, _, page = await self._request("GET", target)
        if urlsplit(url).path.rstrip("/").lower() != "/dashboard":
            url, _, page = await self._request("GET", "/Dashboard")
        if (
            urlsplit(url).path.rstrip("/").lower() != "/dashboard"
            or "LoginPassword" in page
        ):
            raise PortalError(f"Login did not reach the dashboard (ended on {url})")
        self._properties = parse_properties(page)
        _LOGGER.debug("Logged in, %d properties found", len(self._properties))

    async def async_get_usage(
        self, service: ServiceType, start: date, end: date, tz: tzinfo
    ) -> list[UsageRead]:
        """Download hourly usage from `start` to `end`, both days included.

        `tz` is the portal's time zone. The CSV has local times.
        """
        html, _ = await self._ajax("GET", "/Usage/InitializeDownloadSettings")
        fields = form_fields(html, "/Usage/Download")
        if not fields:
            raise PortalError("Download form not found")
        if get_field(fields, "SelectedServiceType") != service:
            set_field(fields, "SelectedServiceType", service)
            html, _ = await self._ajax(
                "POST", "/Usage/UpdateDownloadSettings", data=fields
            )
            fields = form_fields(html, "/Usage/Download") or form_fields(html)
            if not fields:
                raise PortalError(f"Could not switch to service type {service}")
            set_field(fields, "SelectedServiceType", service)
        # The portal saves the last download settings, including the meter
        # choice, so set every option that matters. Select every meter: a
        # replaced meter has no data after its removal date.
        for name, _ in list(fields):
            if match := METER_FIELD.fullmatch(name):
                set_field(fields, f"Meters[{match[1]}].Selected", "true")
        for name, value in (
            ("FileFormat", "download-usage-csv"),
            ("SelectedFormat", FORMAT_CSV),
            ("SelectedInterval", HOURLY),
            ("SelectedUsageType", USAGE_CONSUMPTION),
            ("Start", start.isoformat()),
            ("End", end.isoformat()),
        ):
            set_field(fields, name, value)
        errors, _ = await self._ajax(
            "POST", "/Usage/PresentDownloadErrors", data=fields
        )
        if errors.strip():
            raise PortalError(f"Portal rejected the download: {errors.strip()[:300]}")
        url, content_type, text = await self._request(
            "POST",
            "/Usage/Download",
            data=fields,
            headers={"Origin": self._base, "Referer": self._base + "/Dashboard"},
        )
        if "csv" not in content_type:
            if "LoginPassword" in text or urlsplit(url).path in ("", "/"):
                raise SessionExpired("Download: the portal asked for a new login")
            raise PortalError(f"Download returned {content_type!r}, not CSV")
        return parse_usage_csv(text, tz)

    async def _chart_state(self) -> tuple[str | None, list[list[str]]]:
        """Return the chart's service type and the fields of its forms."""
        html, _ = await self._ajax("GET", "/Dashboard/Chart")
        fields: list[list[str]] = []
        for form in CHART_FORM.findall(html):
            fields += form_fields(form)
        if not fields:
            raise PortalError("Chart form not found")
        match = CHART_SERVICE.search(html)
        return (match[1] if match else None), fields

    async def _set_service(self, service: str) -> None:
        await self._request(
            "GET",
            f"/Dashboard/SetServiceType?ServiceType={service}",
            allow_redirects=False,
        )

    async def _set_chart(
        self, fields: list[list[str]], interval: str, usage_type: str
    ) -> None:
        fields = [list(field) for field in fields]
        set_field(fields, "UsageInterval", interval)
        set_field(fields, "UsageType", usage_type)
        await self._ajax("POST", "/Dashboard/Chart/", data=fields)

    async def async_get_bills(self, service: ServiceType) -> list[Bill]:
        """Return the closed bills of one service from the Charts view.

        The CSV export has no water cost, but the chart shows cost per
        billing period. The portal saves the chart view for the account, so
        this method puts the service, interval and type back afterwards.
        """
        old_service, fields = await self._chart_state()
        old_interval = get_field(fields, "UsageInterval") or BILLING
        old_type = get_field(fields, "UsageType") or USAGE_DOLLARS
        now = datetime.now(UTC)
        query = (
            f"/Dashboard/ChartData?unixTimeStart="
            f"{int((now - timedelta(days=400)).timestamp() * 1000)}"
            f"&unixTimeEnd={int((now + timedelta(days=1)).timestamp() * 1000)}"
        )
        try:
            if old_service != service:
                await self._set_service(service)
                _, fields = await self._chart_state()
            series = {}
            for usage_type, name in (
                (USAGE_DOLLARS, "Dollar"),
                (USAGE_CONSUMPTION, "Consumption"),
            ):
                await self._set_chart(fields, BILLING, usage_type)
                _, data = await self._ajax("GET", query)
                series[name] = parse_bill_series(data, name)
        finally:
            await self._set_chart(fields, old_interval, old_type)
            if old_service is not None and old_service != service:
                await self._set_service(old_service)
        return parse_bills(series["Dollar"], series["Consumption"])
