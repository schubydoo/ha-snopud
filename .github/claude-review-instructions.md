# Claude review instructions

Rules for the on-demand Claude reviewer (`.github/workflows/claude-review.yml`).
Ported from lodger. Only the project rules and a few examples are different.

The workflow reads this file from the base branch, never from the pull request
under review. A PR therefore cannot edit the rules that govern its own review.
Keep it that way.

To tune the reviewer, edit this file in a normal PR. Do not move these rules
into the workflow YAML. If the workflow file is different from the copy on the
default branch, `claude-code-action` refuses to run.

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

- Post each line-specific finding as an inline comment, and group them all
  into exactly one submitted review. Do not submit one review per finding.
  Each inline comment becomes a thread that the maintainer answers and
  resolves.
- How to submit it, exactly. One POST carries the body and every anchor. It is
  the only shape that both groups the findings and passes the tool
  permissions:
  1. Use the `Write` tool to create `review.json` in the workspace root. The
     payload has four fields:
     - `commit_id`: the PR head SHA, from `gh pr view <n> --json headRefOid`.
     - `event`: `"COMMENT"`.
     - `body`: the summary.
     - `comments`: an array of `{path, line, side: "RIGHT", body}` entries,
       one for each finding. Use `side: "LEFT"` only for a line that the diff
       removes.
  2. Run `gh api repos/<owner>/<repo>/pulls/<n>/reviews --input review.json`.

  Each `line` must be a line that the diff touches, on that side. If one entry
  names a line outside the diff, GitHub rejects the whole POST with 422. One
  bad anchor then loses the body and every other finding. To flag an
  unchanged line, anchor the comment to the nearest changed line and name the
  real line in the comment body. If the POST returns 422, read `review.json`
  again, correct that entry with `Write`, and repeat the same POST. Never
  change to a shape that posts the findings one at a time.

  Never post a standalone inline comment. GitHub wraps each standalone review
  comment in a submitted review of its own, so each one splits the review.
  `gh pr review` cannot attach inline comments. These are refused, so do not
  try them:
  - JSON inline on the command line
  - shell redirects (`> file`)
  - compound commands (`;`, `&&`, `||`)
  - `python3`, `ls`, `git`
- Put the summary table in the body of the submitted review, and nowhere
  else. The table lists each finding with its file and line.
- Do not repeat the findings in another place. Your final message becomes the
  progress comment at the top of the PR. Keep it to the checklist, a one-line
  verdict, and a pointer to the review.
- Submit a COMMENT review. Never `REQUEST_CHANGES` and never `APPROVE`. This
  reviewer is advisory and must not gate a merge.
- Do not number findings as `#1`, `#2`. GitHub turns a hash plus digits into a
  link to an unrelated issue or PR. Use "Finding 1" or a short description.
- Link code with the full SHA and a line range:
  `https://github.com/schubydoo/ha-snopud/blob/<full-sha>/custom_components/snopud/api.py#L40-L46`
- The first line of the review body is the tally, in exactly this lowercase
  form: `2 important, 3 nits`. For a count of 1, use the singular:
  `1 important, 1 nit`. A clean review starts with `0 important, 0 nits`.
  Nothing goes above that line. The guard step of the workflow parses it.
- If a commit of the block fixes the issue fully, use a committable
  `suggestion` block. If more work is necessary, describe the fix.
- Findings keep their calibration. The reviewer runs with a plain English
  output style that bans hedging modals (should, may, might, could) in
  replies. That rule is about the register, not about confidence. Where a
  claim is uncertain, say "may" or "might", or stay silent as the verification
  bar says. Never promote a hedge to "must" to satisfy the style.
