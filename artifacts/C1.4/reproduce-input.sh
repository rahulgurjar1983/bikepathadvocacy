#!/usr/bin/env bash
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
proof="$root/artifacts/C1.4"
work="$(mktemp -d /tmp/bikeplan-c14-input.XXXXXX)"
base="$(cat "$proof/input-base-commit.txt")"
git worktree add --detach "$work" "$base"
trap 'git -C "$root" worktree remove --force "$work"' EXIT
cd "$work"
args=(tests/test_report.py::test_fr13_1_figures_are_sorted_with_every_field tests/test_report.py::test_fr13_2_the_figure_links_hold_the_numbers_and_resolve_to_one_entry -q --tb=short)
"$root/.venv/bin/python" -m pytest "${args[@]}" > "$proof/input-base-tests.txt" 2>&1
git apply "$proof/input-feature.patch"
set +e
"$root/.venv/bin/python" -m pytest "${args[@]}" > "$proof/input-feature-tests.txt" 2>&1
status=$?
set -e
test "$status" -eq 1
rg '2 failed' "$proof/input-feature-tests.txt"
rg 'F14' "$proof/input-feature-tests.txt"
