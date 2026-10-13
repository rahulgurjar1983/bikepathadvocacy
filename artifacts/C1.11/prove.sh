#!/usr/bin/env bash
set -euo pipefail
out="${1:?usage: prove.sh <report folder> <proof folder>}"
proof="${2:?usage: prove.sh <report folder> <proof folder>}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
release="$work/release"
mkdir -p "$release" "$proof"
cp "$out/report.html" "$release/au-nsw-bayside-report.html"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$out" . | gzip -n >"$release/au-nsw-bayside.tar.gz"
uv run --frozen pytest -q -p no:cacheprovider --junitxml="$work/junit.xml" -k "fr17_12 or fr17_11" tests/test_edition.py tests/test_checks_opening.py
uv run --frozen bikeplan checks "$work/junit.xml" --root . --out "$work/checks.html" --release "$release"
uv run --frozen python artifacts/C1.11/excerpt.py "$work/checks.html" "$out" "$proof"
