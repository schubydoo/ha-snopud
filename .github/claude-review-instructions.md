# Claude review instructions

Project rules for the on-demand Claude reviewer (`.github/workflows/claude-review.yml`,
which calls the central job in `schubydoo/shared-workflows`).
Ported from lodger. Only the project rules and a few examples are different.

The workflow reads this file from the base branch, never from the pull request
under review. A PR therefore cannot edit the rules that govern its own review.
Keep it that way.

To tune what the reviewer looks for, edit this file in a normal PR. How the
review is posted is central: the shared workflow carries that recipe, and it
wins on posting.

Length has a cost. Rules that change review behavior belong here. General
project context belongs in `AGENTS.md`.

---

## Severity

- 🔴 Important: breaks behavior, writes incorrect statistics, exposes private
  data, or breaks a rule below. Fix before merge.
- 🟡 Nit: real but minor. Worth a comment, never blocking.
- 🟣 Pre-existing: a real bug that this PR did not introduce. Post at most two
  per review, and never as Important. Those get their own PR.

Style, naming, and refactoring suggestions are always Nit at most.

## Always check

A change that breaks one of these is wrong. Passing tests do not make it
right. Flag it as Important.

1. The integration only reads. It submits the login, the download form, and
   the chart settings. A request that changes an account, or a request to a
   host other than my.snopud.com, is Important.
2. No secrets in logs. The password, the login request, and the session
   cookies never reach a log line, an exception message, or a diagnostics dump.
3. No real portal data in the diff. The files in `tests/fixtures/` are made
   up. A real account number, meter number, address, CSV download, or HAR file
   is Important.
4. Statistics stay correct. Each hour goes to its real reading time. The local
   times of the portal have no time zone, and the daylight saving rule in
   `docs/protocol.md` decides the repeated 1 AM hour. A sum that can double
   count on a repeated import is Important.
5. The portal saved settings come back. Code that changes the Charts view puts
   back the service, the interval, and the type that the user had.
6. No new Python dependency. `requirements` in `manifest.json` stays empty.
7. The load on the portal stays small. A shorter update interval or a new
   request in each update needs a reason in the PR.
8. The docs are honest. A behavior change updates the README and
   `docs/protocol.md` in the same PR. A claim that the code does not support is
   Important.
9. A changeset body is one line. knope renders a second line as a heading in
   the middle of the list.

## Do not report

CI already enforces these, so a second report is waste:

- Formatting, import order, unused names: `ruff check` and `ruff format --check`
- Manifest and translation shape: hassfest and the HACS action
- Unpinned GitHub Actions: the repository requires SHA pins
- Outdated dependencies: Renovate

Also do not report anything in `CHANGELOG.md`, or a lint finding that a
`# noqa` comment with a reason silences.

## Review independently

You are the only reviewer, or a second opinion.

- Do not read the comments of other reviewers before you form your findings.
  Work from the diff and the code. A finding is not more credible because
  another tool raised it.
- The one exception is your own previous review on the same PR.

## Verification bar

You must be able to prove each finding from the code. Never infer a finding
from a name.

- A claim about behavior needs a `file:line` citation of the code that causes
  it.
- If a finding needs context outside the diff, read that context first. If you
  still cannot prove the finding, do not post it.
- Do not flag a failure that depends on input or state that you did not show
  to be reachable.

A false positive costs the author a round trip and costs the reviewer its
credibility. If you are uncertain, say nothing.

### Do not run the test suite

A review is a reading job here. Do not run `pytest`, `pip`, or `ruff`. CI runs
the suite on every PR. Never contact my.snopud.com.

When a PR states a test result, read the code and the fixtures, and make sure
that the change can produce that result. Name CI as the measurement. "I read
the code. CI is the measurement" is a complete answer. A run attempt is denied,
and the workflow counts each denial.

## Volume

Post at most five Nits per review. If there are more, post the five that
matter and add "plus N similar nits" to the summary. Important findings have
no limit.

## Re-reviews

If the PR was reviewed before, add a `## Previous findings` section below the
tally line. Resolve each earlier Important finding as exactly one of these:

- FIXED: cite the line or commit that fixed it.
- ACCEPTED: quote the technical reason of the author. "Please approve" is not
  a technical reason.
- STILL OPEN: no code and no explanation addressed it.

A finding marked FIXED or ACCEPTED is closed. Do not raise it again. After the
first review, post Important findings only.

## Output

The central workflow writes a posting recipe next to this file, and it governs how the review
is posted: the grouped review, `review.json`, thread replies, the tally line and the allowed
commands. Do not add posting rules here.

Link code in this repo with the full SHA and a line range:
`https://github.com/schubydoo/ha-snopud/blob/<full-sha>/custom_components/snopud/api.py#L40-L46`
