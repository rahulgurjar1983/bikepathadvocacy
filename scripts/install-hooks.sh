#!/usr/bin/env bash
set -euo pipefail
git config core.hooksPath .githooks
echo "hooks: git now runs the hooks in .githooks"
