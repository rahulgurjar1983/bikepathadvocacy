#!/usr/bin/env bash
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
base="$(cat "$root/artifacts/Q1.5/base-commit.txt")"
probe="$(mktemp -d)"
git worktree add --detach "$probe" "$base"
trap 'git worktree remove --force "$probe"' EXIT
cd "$probe"
uv run --project "$root" pytest tests/test_report.py::test_fr13_1_figures_are_sorted_with_every_field -q
git apply "$root/artifacts/Q1.5/people-output.patch"
set +e
uv run --project "$root" pytest tests/test_report.py::test_fr13_1_figures_are_sorted_with_every_field -q
status=$?
set -e
test "$status" -eq 1
test -z "$(git diff -- tests/)"
