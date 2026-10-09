#!/usr/bin/env bash
set -euo pipefail
project_root="$(pwd)"
proof_root="$(mktemp -d)"
proof_commit="$(cat artifacts/Q1.3/base-commit.txt)"
proof_python="$project_root/.venv/bin/python"
proof_cases=(
  tests/test_fit_options.py::test_fr6_2_case_6_road_diet_barred_by_adt_and_verge_path_fits
  tests/test_fit_choice.py::test_fr6_7_short_street_prefers_the_verge_path_to_parking_removal
  tests/test_fit_separation.py::test_fr6_11_least_disruptive_separated_fix_is_picked_among_separated
)
git worktree add --detach "$proof_root/main" "$proof_commit"
trap 'git -C "$project_root" worktree remove --force "$proof_root/main"; rmdir "$proof_root"' EXIT
cd "$proof_root/main"
"$proof_python" -m pytest "${proof_cases[@]}" -q
git apply "$project_root/artifacts/Q1.3/survey-probe.patch"
set +e
"$proof_python" -m pytest "${proof_cases[@]}" -q
proof_status=$?
set -e
if [ "$proof_status" -ne 1 ]; then
  exit 1
fi
