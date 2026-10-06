#!/usr/bin/env bash
set -uo pipefail
pr="${1:?usage: wait-ci.sh PR}"
limit="${WAIT_CI_SECS:-570}"
poll="${WAIT_CI_POLL_SECS:-20}"
query='(.statusCheckRollup // [] | map(select(.conclusion != "SKIPPED" and .conclusion != "NEUTRAL")) | group_by(.name) | map(max_by(.startedAt // ""))) as $checks | [.state, ($checks | map(select(.status != "COMPLETED")) | length), ($checks | map(select(.conclusion == "FAILURE" or .conclusion == "CANCELLED" or .conclusion == "TIMED_OUT" or .conclusion == "ACTION_REQUIRED" or .conclusion == "STARTUP_FAILURE") | .name) | join(" ")), ($checks | length)] | map(tostring) | join("|")'
deadline=$((SECONDS + limit))
while :; do
  if ! line="$(gh pr view "$pr" --json state,statusCheckRollup --jq "$query" 2>&1)"; then
    echo "wait-ci: gh failed: $line" >&2
    exit 2
  fi
  IFS='|' read -r state pending failed total <<<"$line"
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
  if [ "${total:-0}" -gt 0 ] && [ "${pending:-1}" -eq 0 ]; then
    echo "wait-ci: PR $pr passed every check but is not merged; run scripts/ship-pr.sh $pr"
    exit 4
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "wait-ci: PR $pr is still running after ${limit}s"
    exit 3
  fi
  sleep "$poll"
done
