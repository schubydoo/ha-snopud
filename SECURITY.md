# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Do not open a public issue for a security problem.

Report it through the private vulnerability reporting of GitHub. Go to the
[Security tab](https://github.com/schubydoo/ha-snopud/security/advisories/new)
of this repository and open a draft advisory. Only the maintainer can see it.

If you cannot use private reporting, open a public issue that says only that
you have a security report. Put no details in it.

### What to include

- The type of vulnerability.
- The affected file paths, and the tag, branch, or commit.
- The steps to reproduce it.
- What an attacker gets.

### What to expect

One person maintains this project in their spare time. Expect an answer in 7
days. After that, there is no fixed schedule. After the fix, the maintainer tells
you. The advisory credits you. If you do not want the credit, say
so in your report.

## What the integration holds

- Home Assistant stores your MySnoPUD email and password with the integration
  entry. The integration sends them only to my.snopud.com.
- The integration downloads your usage data and your bill amounts. That data
  stays in your Home Assistant database.

Report anything that exposes these as a vulnerability. Examples:

- A password or a session cookie in a log line.
- A request to a host other than my.snopud.com.
- A request that changes your account.

## Private data in contributions

Never commit a password, a real portal response, a CSV download, or a HAR
file, also not as a test fixture. The fixtures in `tests/fixtures/` are made
up. If you find real account data in this repository, report it as a
vulnerability.
