# Contributing to ha-snopud

Thank you for your interest. One person maintains this project in their spare
time. Bug reports and pull requests are welcome.

## Before you write code

For a bug fix, send the pull request. You do not need an issue first.

For a new feature, open an issue first. The integration has a narrow scope: it
reads usage data from your own MySnoPUD account and writes it to Home Assistant
statistics. It never changes an account and never pays a bill. A pull request
that makes the integration write to the portal will be declined.

## Development setup

You need Python 3.14.

```sh
git clone https://github.com/schubydoo/ha-snopud
cd ha-snopud
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
```

Install the pre-commit hooks one time. The hooks run the same lint and format
steps as CI, and they run the tests before each push.

```sh
uvx pre-commit install --install-hooks
```

The `uvx` command comes with [uv](https://docs.astral.sh/uv/). Without uv, use
this command:

```sh
pipx run pre-commit install --install-hooks
```

## Tests

```sh
.venv/bin/pytest
uvx ruff check
uvx ruff format --check
```

The tests run with no network. A test that needs the real portal is in the
wrong place. CI also runs hassfest and the HACS action, which make sure that
the integration manifest is valid.

[docs/protocol.md](docs/protocol.md) describes the portal protocol.

## Fixtures and private data

The files in `tests/fixtures/` are made up. Never commit a real portal
response, a CSV download, or a HAR file. They contain account numbers, meter
numbers, addresses, and in the case of a HAR file, your password.

If you add a fixture, write it by hand or replace every real value first. If
you think that you committed real data, treat it as a security report. See
[SECURITY.md](SECURITY.md).

## Pull requests

- Branch from `main`, and open the pull request against `main`.
- Keep the pull request to one change.
- Use [Conventional Commits](https://www.conventionalcommits.org) for the
  title, for example `fix: keep the email after a failed login`. The repository
  squash-merges, so the title becomes the commit subject.
- Say what you tested and what you saw.
- CI must pass: `lint`, `pytest`, `hassfest`, and `hacs`.

Expect a review in days, not hours.

## Changesets

A change that a user can see needs a changeset. A changeset is a small file in
`.changeset/` that becomes the changelog entry and sets the version bump. Run
`knope document-change`, or create `.changeset/<short-name>.md` by hand:

```markdown
---
default: minor
---

Import the gas usage as a new statistic
```

- `default:` is one of `major` (a breaking change), `minor` (a new feature),
  `patch` (a fix), `security`, or `perf`.
- The body must be exactly one line. knope renders a second line as a heading
  in the middle of the list.
- Do not add a `README.md` or any other Markdown file to `.changeset/`. knope
  reads each `.md` file there as a changeset.
- Do not edit `CHANGELOG.md` by hand. knope writes it.

A pull request with no user-visible change (CI, tests, refactor, documentation)
needs no changeset. A maintainer adds the `no-changelog` label, which clears the
reminder comment.

## Releases

[knope](https://knope.tech) makes the releases. After a pull request with a
changeset merges, a workflow opens a `chore: prepare release X.Y.Z` pull
request. That pull request bumps the version in
`custom_components/snopud/manifest.json` and updates `CHANGELOG.md`. When a
maintainer merges it, a second workflow creates the tag and the GitHub release.
HACS then offers the new version.

## Security

Do not open a public issue for a security problem. See
[SECURITY.md](SECURITY.md).

## Conduct

The [Code of Conduct](CODE_OF_CONDUCT.md) applies everywhere in this project.
