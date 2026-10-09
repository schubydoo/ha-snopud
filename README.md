# SnoPUD for Home Assistant

This Home Assistant custom integration imports your electricity and water
usage from [MySnoPUD](https://my.snopud.com). MySnoPUD is the customer portal
of the Snohomish County PUD. The data goes into Home Assistant
long-term statistics with the real reading times. The Energy dashboard then
shows your usage in the correct hours, even though the portal publishes it
hours late.

This project is not affiliated with, endorsed by, or supported by Snohomish
County PUD, Accelerated Innovations, or MyMeter.

## What it does

The integration logs in to MySnoPUD with your own email and password. It
downloads the same hourly CSV files that the portal's "Download Usage Data"
page gives you. For water cost, it also reads your bills in the portal's
Charts view. It reads only. It never changes your account or pays bills. It
submits only the login, the download form, and the chart settings.

It creates these statistics for the property that is selected on your
dashboard:

| Statistic | Unit | Energy dashboard use |
|---|---|---|
| SnoPUD *property* electricity consumption | kWh | Grid consumption |
| SnoPUD *property* electricity cost | USD | Cost of that consumption |
| SnoPUD *property* water consumption | ft³ | Water source |
| SnoPUD *property* water cost | USD | Cost of that water |

It also creates two sensors, "Latest electricity reading" and "Latest water
reading". Each one shows the start of the newest hour that the portal
published.

## Requirements

- Home Assistant 2025.11 or later.
- A MySnoPUD account that logs in with an email and a password.

## Installation

1. In HACS, open the menu and select "Custom repositories".
2. Add `https://github.com/schubydoo/ha-snopud` with the type "Integration".
3. Download "SnoPUD" in HACS.
4. Restart Home Assistant.
5. Go to Settings > Devices & services > Add integration, and select "SnoPUD".
6. Enter the email and password that you use on my.snopud.com.

## Energy dashboard

1. Go to Settings > Dashboards > Energy.
2. Under "Electricity grid", add a consumption source.
3. Select "SnoPUD *property* electricity consumption".
4. For the cost, select "Use an entity tracking the total costs".
5. Select "SnoPUD *property* electricity cost".
6. Under "Water consumption", add "SnoPUD *property* water consumption".
7. For the water cost, select "Use an entity tracking the total costs".
8. Select "SnoPUD *property* water cost".

## How the import works

- The integration updates every 4 hours. The portal publishes usage several
  hours late, so more frequent updates do not get newer data.
- The first update imports the last 365 days of hourly data. The portal holds
  hourly data for about one year.
- Each later update downloads again from 3 days before the newest imported
  hour. The portal sometimes corrects recent values, and this picks up the
  corrections.
- The portal's hourly CSV has local times with no time zone. On the day that
  daylight saving time ends, the portal has no data for the first 1 AM hour.
  The integration places the portal's 1 AM row in the second (standard time)
  1 AM hour, which matches the portal's own Green Button export.
- The CSV export has no water cost. The Charts view shows the dollars and the
  cubic feet of each closed water bill. The integration divides the two to get
  a rate for each bill. Each hour's cost is its cubic feet times that rate, so
  the hours of a closed bill add up to the bill amount. Fixed monthly charges
  are spread over the hours in the same way.
- Hours after the newest bill use the rate of that bill as an estimate. When
  the next bill closes, the integration prices those hours again with the new
  rate.

## Limits

- Only the property that is selected on your MySnoPUD dashboard is imported.
- Accounts that need a two-factor code or a security question at login are
  not supported. The setup form shows an error for them.
- The portal saves your last download settings. The integration selects the
  CSV format, the hourly interval, and all meters on each download. If you use
  the portal's download page, you will see these settings.
- If you remove the "$" column in the portal's download settings, the
  electricity cost statistic stops updating.
- The portal also saves your last Charts view. To read the water bills, the
  integration switches the view to water, billing periods, and dollars. It
  then puts back the service, interval, and type that you had.

## Privacy

- Home Assistant stores your email and password with the integration entry.
  The integration sends them only to my.snopud.com.
- The integration does not log your password or the login request.
- Your usage data stays in your Home Assistant database.

## Terms of use

The [MySnoPUD Terms and Conditions](https://www.snopud.com/wp-content/uploads/2021/08/MySnoPUD_TC.pdf)
(September 2020) let you use the services for your own residential or business
purposes. "Export history" is one of the listed services. The terms forbid
use that "disproportionately burdens the operation of the Website", and
access to accounts that you are not authorized to use. This integration logs
in to your own account and makes a few requests every 4 hours. This summary
is not legal advice. Read the terms yourself.

## Development

The portal protocol and the answers to the early design questions are in
[docs/protocol.md](docs/protocol.md). The folder `tools/` holds the original
command-line script that first proved the protocol.

To run the tests, you need Python 3.14:

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

Test fixtures in `tests/fixtures/` are made up. Do not commit real portal
responses, CSV downloads, or HAR files. They contain account numbers, meter
numbers, addresses, and in the case of HAR files, your password.

To send a change, read [CONTRIBUTING.md](CONTRIBUTING.md). The release notes
are in [CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).
