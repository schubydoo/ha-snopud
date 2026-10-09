# Changelog

knope writes this file from the fragments in `.changeset/`. Do not edit it by
hand. The entries for 0.2.0 and earlier come from the GitHub release notes of
those versions.

## 0.2.1 (2026-10-09)

### Fixes

- The HACS metadata now states that the integration is for the United States ([#13](https://github.com/schubydoo/ha-snopud/pull/13))

## 0.2.0 (2026-09-26)

### Features

- New statistic: water cost. The CSV export has no water cost, so the integration reads your closed water bills from the portal's Charts view. Each hour gets its cubic feet times the rate of its bill. The rate is the bill dollars divided by the bill cubic feet. The hours of a closed bill then add up to the bill amount.
- Hours after the newest bill use that bill's rate as an estimate. The next update after a new bill prices them again.
- The first update after the upgrade fills in water cost for the full imported history.
- The portal saves your Charts view. The integration puts back the service, interval, and type that you had.

## 0.1.1 (2026-09-26)

### Fixes

- The setup form no longer fills the password field again after a failed login. It keeps only the email.
- Renovate now keeps the CI actions and the test dependencies up to date. All actions are pinned by commit SHA.

## 0.1.0 (2026-09-26)

### Features

- Imports hourly electricity (kWh and cost) and water (cubic feet) usage from MySnoPUD into Home Assistant long-term statistics, with the real reading times.
- The first update imports 365 days. Later updates download again from 3 days before the newest hour, to pick up corrections.
- Setup asks for the MySnoPUD email and password and tests them with a real login. A later login failure starts reauthentication.
- Two sensors show the newest hour of data for each service.
