# Agent rules for ha-snopud

Rules for coding agents that work in this repository. Humans can find the
longer version in [CONTRIBUTING.md](CONTRIBUTING.md).

## What this project is

ha-snopud is a Home Assistant custom integration, installed through HACS. It
logs in to the MySnoPUD portal, downloads hourly electricity and water usage,
and writes it to Home Assistant long-term statistics. The code is in
`custom_components/snopud/`. The portal protocol is in `docs/protocol.md`.

## Rules that do not change

1. The integration only reads from the portal. It submits the login, the
   download form, and the chart settings, and nothing else.
2. Never log the password, the login request, or a session cookie.
3. Never commit real portal data: no real response, CSV download, HAR file,
   account number, meter number, or address. The files in `tests/fixtures/` are
   made up.
4. The integration has no Python dependencies. `requirements` in
   `manifest.json` stays empty unless the maintainer agrees to a change.
5. The portal saves the last download settings and the last Charts view for
   each account. Code that changes the Charts view must put it back.

## Commands

```sh
.venv/bin/pytest              # the tests, with no network
uvx ruff check                # lint
uvx ruff format --check       # format
uvx pre-commit run --all-files
```

The venv needs Python 3.14 and `pip install -r requirements_test.txt`.

## Changes

- Never commit to `main`. Each change goes through a branch and a pull request
  against `main`.
- Use a Conventional Commits title, for example `fix: ...`.
- A change that a user can see needs a one-line changeset in `.changeset/`.
  See the "Changesets" section in CONTRIBUTING.md.
- Do not edit `CHANGELOG.md` or the `version` in `manifest.json`. knope
  writes both.
- Pin each GitHub Action by its full commit SHA, with the version in a comment.
