#!/usr/bin/env sh
# Guard knope changeset fragments: each needs YAML front matter with a valid
# `default:` and a SINGLE-line body. A second line renders as a `#### heading`
# mid-list and corrupts the release notes; a missing front matter fails the
# release outright. Runs in pre-commit and can be run by hand.
set -eu

status=0
for f in .changeset/*.md; do
  [ -e "$f" ] || continue
  case "$(basename "$f")" in README.md) continue ;; esac

  first="$(head -n 1 "$f")"
  if [ "$first" != "---" ]; then
    echo "changeset $f: must start with '---' front matter" >&2
    status=1
    continue
  fi

  # The default: line, between the two fences.
  default="$(awk 'NR>1 && /^---$/{exit} /^default:/{print}' "$f" | sed 's/^default:[[:space:]]*//')"
  case "$default" in
    major|minor|patch|security|perf) : ;;
    *)
      echo "changeset $f: 'default:' must be one of major|minor|patch|security|perf (got '${default:-none}')" >&2
      status=1
      ;;
  esac

  # The body is everything after the closing fence; it must be exactly one
  # non-empty line.
  body_lines="$(awk 'seen && NF {print} /^---$/{c++} c==2{seen=1}' "$f" | wc -l | tr -d ' ')"
  if [ "$body_lines" != "1" ]; then
    echo "changeset $f: body must be exactly one non-empty line (found $body_lines)" >&2
    status=1
  fi
done

[ "$status" -eq 0 ] && echo "changesets: ok"
exit "$status"
