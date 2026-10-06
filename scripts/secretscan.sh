#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
bin="${GITLEAKS_BIN:-$root/.tools/bin/gitleaks}"
target="${1:?usage: secretscan.sh BASE | --all}"

if [ ! -x "$bin" ]; then
  echo "secretscan: gitleaks is required at $bin; run scripts/install-gitleaks.sh" >&2
  exit 2
fi
if [ "$target" = "--all" ]; then
  exec "$bin" git --no-banner --redact --exit-code 1 .
fi
exec "$bin" git --no-banner --redact --exit-code 1 --log-opts="$target..HEAD" .
