#!/usr/bin/env bash
set -uo pipefail
pr="${1:?usage: ship-pr.sh PR}"
tries="${SHIP_PR_TRIES:-10}"
pause="${SHIP_PR_WAIT_SECS:-15}"
if ! out="$(gh pr ready "$pr" 2>&1)"; then
  case "$out" in
    *already*) ;;
    *)
      echo "ship-pr: gh pr ready failed: $out" >&2
      exit 2
      ;;
  esac
fi
for _ in $(seq 1 "$tries"); do
  gh pr merge "$pr" --auto --merge >/dev/null 2>&1
  if ! line="$(gh pr view "$pr" --json state,autoMergeRequest --jq '[.state, (.autoMergeRequest != null)] | map(tostring) | join("|")' 2>&1)"; then
    echo "ship-pr: gh pr view failed: $line" >&2
    exit 2
  fi
  IFS='|' read -r state auto <<<"$line"
  if [ "$state" = MERGED ]; then
    echo "ship-pr: PR $pr merged"
    exit 0
  fi
  if [ "$auto" = true ]; then
    echo "ship-pr: PR $pr is ready and will merge itself when CI passes"
    exit 0
  fi
  sleep "$pause"
done
echo "ship-pr: auto-merge did not turn on for PR $pr after $tries tries" >&2
exit 1
