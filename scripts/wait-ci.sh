#!/usr/bin/env bash
set -uo pipefail
pr="${1:?usage: wait-ci.sh PR}"
limit="${WAIT_CI_SECS:-570}"
poll="${WAIT_CI_POLL_SECS:-20}"
query='(.statusCheckRollup // [] | map(select(.conclusion != "SKIPPED" and .conclusion != "NEUTRAL")) | group_by(.name) | map(max_by(.startedAt // ""))) as $checks | [.state, ($checks | map(select(.status != "COMPLETED" or .conclusion == "CANCELLED")) | length), ($checks | map(select(.conclusion == "FAILURE" or .conclusion == "TIMED_OUT" or .conclusion == "ACTION_REQUIRED" or .conclusion == "STARTUP_FAILURE") | .name) | join(" ")), ($checks | length), (.autoMergeRequest != null), ($checks | map(.name) | join(" "))] | map(tostring) | join("|")'
base="${WAIT_CI_BASE:-main}"
if ! required="$(gh api "repos/{owner}/{repo}/branches/$base/protection/required_status_checks" --jq '.contexts | join(" ")' 2>&1)"; then
  echo "wait-ci: gh failed: $required" >&2
  exit 2
fi
deadline=$((SECONDS + limit))
while :; do
  if ! line="$(gh pr view "$pr" --json state,statusCheckRollup,autoMergeRequest --jq "$query" 2>&1)"; then
    echo "wait-ci: gh failed: $line" >&2
    exit 2
  fi
  IFS='|' read -r state pending failed total auto names <<<"$line"
  if [ "$state" = MERGED ]; then
    echo "wait-ci: PR $pr merged"
    exit 0
  fi
  if [ -n "${failed:-}" ]; then
    echo "wait-ci: PR $pr has failed checks: $failed"
    exit 1
  fi
  if [ "$state" = CLOSED ]; then
    echo "wait-ci: PR $pr is closed without a merge"
    exit 1
  fi
  missing=""
  for name in $required; do
    case " ${names:-} " in
      *" $name "*) ;;
      *) missing="${missing:+$missing }$name" ;;
    esac
  done
  if [ "${total:-0}" -gt 0 ] && [ "${pending:-1}" -eq 0 ] && [ -n "$missing" ]; then
    echo "wait-ci: PR $pr never reported the required checks: $missing; run git merge origin/main and push"
    exit 5
  fi
  if [ "${total:-0}" -gt 0 ] && [ "${pending:-1}" -eq 0 ] && [ "${auto:-false}" != true ]; then
    echo "wait-ci: PR $pr passed every check but is not merged; run scripts/ship-pr.sh $pr"
    exit 4
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "wait-ci: PR $pr is still running after ${limit}s"
    exit 3
  fi
  sleep "$poll"
done
