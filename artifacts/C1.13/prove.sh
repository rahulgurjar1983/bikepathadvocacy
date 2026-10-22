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
uv run --frozen pytest -q -p no:cacheprovider --junitxml="$work/junit.xml" -k "fr17_12 or fr17_14 or fr17_15 or fr19_6 or fr20_7 or fr20_8 or fr20_19 or fr20_20 or fr20_21 or fr20_22 or fr20_23 or fr20_25" tests
uv run --frozen bikeplan checks "$work/junit.xml" --root . --out "$work/checks.html" --release "$release"
cp "$work/checks.html" "$proof/checks.html"
