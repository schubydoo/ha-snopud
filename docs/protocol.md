# MySnoPUD portal protocol

This file records how the MySnoPUD portal works, as tested on 2026-09-25.
The portal runs on the MyMeter platform, which other utilities also use under
their own domains. The client keeps the base URL as a parameter for that
reason.

## Login

1. Send `GET /`. Read the `__RequestVerificationToken` hidden input.
   This token is a per-session CSRF token (a code that proves the request came
   from the site's own page).
2. Send `POST /Home/Login` as a form, with the header
   `X-Requested-With: XMLHttpRequest`. The fields are `RedirectUrl=`,
   `LoginErrorMessage=`, `LoginEmail`, `LoginPassword`, `ExternalLogin=False`,
   `TwoFactorRendered=False`, `SecretQuestionRendered=False`, and the token.
3. Follow the redirect in the response, then make sure that the final page is
   `/Dashboard`.

The login response is `200` with `text/plain` JSON in both cases:

```json
{"AjaxResults":[{"Identifier":null,"Action":"Redirect","Value":"https://my.snopud.com/Integration/LoginActions"}],"Data":null}
```

```json
{"AjaxResults":[],"Data":{"LoginErrorMessage":"Invalid email address or password"}}
```

An unknown email and a wrong password give the same error. The session lives
in the `MM_SID` cookie.

The browser also calls `/Integration/LoginActionsComplete` after login. The
dashboard and the downloads work without that call.

## Expired session

An XHR request without a valid session returns
`{"AjaxResults":[{"Identifier":null,"Action":"Redirect","Value":"/"}],"Data":null}`.
A normal page request returns `302` to `/`. The integration logs in at the
start of each update, so it does not depend on the session length.

## Properties

The dashboard lists properties as
`<li data-property-id="..." class="current">` elements, with the property
name in an `<h2>`. The selected property has the class `current`. The
integration uses `data-property-id` in its statistic IDs.

## Download

1. Send `GET /Usage/InitializeDownloadSettings` (XHR). The response wraps the
   HTML of `<form id="downloadOptions" action="/Usage/Download">`.
2. If `SelectedServiceType` is not the wanted service, change it and send the
   form to `POST /Usage/UpdateDownloadSettings` (XHR). Parse the new form from
   the response, because the meter list changes.
3. Set the fields, then send `POST /Usage/PresentDownloadErrors` (XHR). The
   reply `{"AjaxResults":[],"Data":null}` means that there are no errors.
4. Send the same fields to `POST /Usage/Download`. The response is `text/csv`.

Serialize the form the way a browser does. Checkboxes use the ASP.NET
pattern: a checked box sends `true`, and a hidden input with the same name
sends `false` after it. The server uses the first value.

The portal saves the last download settings for the account. That includes
the service type, the meter choice, and the columns. The integration sets
every option that matters on each download.

| Field | Values |
|---|---|
| `SelectedFormat` | `1` = Green Button, `2` = CSV |
| `FileFormat` | `download-usage-csv` |
| `SelectedServiceType` | `1` = electric, `2` = water |
| `SelectedInterval` | `3` = 15 minutes (electric only), `4` = 30 minutes (electric only), `5` = hourly, `6` = daily, `8` = weekly, `7` = billing |
| `SelectedUsageType` | `1` = consumption, `3` = dollars (electric only) |
| `Start`, `End` | `YYYY-MM-DD`, both days included |
| `Meters[i].Value`, `Meters[i].Selected` | one pair per meter |

## CSV format

```
Start,kWh,$
"09/24/2026 12:00:00 AM","0.500","$0.05"
```

```
Start,CF
"09/24/2026 12:00:00 AM","1.200"
```

Times are local (America/Los_Angeles), with no offset, and mark the start of
each interval. If the Meter column is selected, each meter gets its own row.
The integration sums rows that share a start time.

## Charts view (water cost)

Tested on 2026-09-25. The CSV export has no cost column for water, but the
Charts view shows water dollars per billing period.

1. Send `GET /Dashboard/Chart` (XHR). The HTML has forms with the class
   `chartControlForm`. They hold `UsageInterval`, `UsageType`, `meterIds`,
   and the token. The current service is the
   `<li class="current setServiceTypeChartButton" data-value="...">`.
2. To change the service, send `GET /Dashboard/SetServiceType?ServiceType=2`.
   The response is `302` to `/Dashboard`.
3. To change the interval or the type, send all `chartControlForm` fields to
   `POST /Dashboard/Chart/` (XHR).
4. Send `GET /Dashboard/ChartData?unixTimeStart=<ms>&unixTimeEnd=<ms>` (XHR).
   The wrapper's `Data` has `usageType` (`Dollar` or `Consumption`) and
   `series`. The first series is the range navigator. The second series has
   one point per bill, such as
   `{"x": ..., "y": 50.00, "hs": {"start": "1/6/2026", "end": "2/5/2026"}}`.

Findings:

- Water dollars exist only with `UsageInterval=7` (billing). For hourly,
  daily, and weekly intervals, the portal quietly sets `UsageType` back to
  `1` and returns cubic feet. Always check `usageType` in the response.
- The portal saves the chart's service, interval, and type for the account.
  Put them back after reading.
- A bill's cubic feet equal the sum of the hourly CSV rows from its start
  date through its end date, both days included. So bill dollars divided by
  bill cubic feet, applied to each hour, adds up to the bill exactly.
- Only closed bills appear. The current period has no dollars until its bill
  is issued.

## Answers to the early questions

- Date range: one request for 400 days of hourly electric data, or 120 days
  of 15-minute data, took less than one second. Hourly data went back about
  13 months on the test account. Daily data went back further.
- Two meters: the test account lists two meters per service. One meter has
  no data at all, probably a meter that was replaced. With both selected, the
  CSV equals the active meter alone. The integration selects all meters.
- Green Button: the export is Atom XML with epoch timestamps. Electric values
  are in Wh with full precision. Water values are rounded to whole cubic feet,
  there is no cost, and each reading repeats once per meter. CSV is the better
  source.
- Daylight saving time: on 2025-11-02 both formats have only one 1 AM hour.
  Green Button places it at 09:00 UTC, which is 1 AM standard time. The
  portal has no data for the first 1 AM hour (08:00 UTC). The CSV 1 AM row
  therefore maps to `fold=1`.
- Two-factor and security questions: the test account has neither. The
  integration treats a login response with no error and no redirect as an
  extra step that it cannot do.
- Several properties: the test account has one. The integration imports the
  selected property only. Switching properties is not yet mapped.
