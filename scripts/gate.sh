#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-branch}"
for tool in git uv; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "gate: $tool is required" >&2
    exit 2
  fi
done

step() {
  echo "== gate: $*"
  "$@"
}

py=(uv run --frozen python)
step scripts/install-gitleaks.sh
step uv run --frozen ruff check .
step uv run --frozen ruff format --check .
step "${py[@]}" -m gates.nocomments
step "${py[@]}" -m gates.srcgrep
step "${py[@]}" -m gates.generic
step "${py[@]}" -m gates.ledger check
step "${py[@]}" -m gates.speccov
step "${py[@]}" -m gates.verifydoc

case "$mode" in
  main)
    step "${py[@]}" -m gates.readability
    step scripts/secretscan.sh --all
    ;;
  branch)
    base="${GATE_BASE:-$(git merge-base origin/main HEAD)}"
    step "${py[@]}" -m gates.readability --changed "$base"
    step "${py[@]}" -m gates.inputs --base "$base"
    step "${py[@]}" -m gates.redgreen mixed "$base"
    step "${py[@]}" -m gates.retention --base "$base"
    step scripts/secretscan.sh "$base"
    step "${py[@]}" -m gates.redgreen red "$base"
    ;;
  *)
    echo "gate: mode must be 'branch' or 'main', not '$mode'" >&2
    exit 2
    ;;
esac

if [ "${GATE_SKIP_TESTS:-0}" != 1 ]; then
  step scripts/test.sh
fi
echo "== gate: all green ($mode)"
