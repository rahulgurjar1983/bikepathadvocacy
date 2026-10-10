#!/usr/bin/env bash
set -euo pipefail
work="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
systemctl --user show bikepath-loop.service --property=ActiveState,SubState,MainPID,NRestarts
python3 - "$work/.ralph/status.json" <<'PY'
import datetime
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text())
for key in ("phase", "row", "pr", "reason", "retry_at", "heartbeat_at"):
    if key in record:
        print(f"{key}: {record[key]}")
age = datetime.datetime.now(datetime.UTC) - datetime.datetime.fromisoformat(record["heartbeat_at"])
print(f"heartbeat_age_seconds: {age.total_seconds():.1f}")
PY
