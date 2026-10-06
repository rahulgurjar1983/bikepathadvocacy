#!/usr/bin/env bash
set -uo pipefail
message="${*:-}"
if [ -z "$message" ]; then
  message="$(cat)"
fi
if [ "${NOTIFY_DRY_RUN:-0}" = 1 ]; then
  printf 'notify (dry run): %s\n' "$message"
  exit 0
fi
config="${HOME}/.config/bikepathadvocacy/telegram.json"
if [ ! -r "$config" ]; then
  echo "notify: missing $config; it needs botToken and chatId" >&2
  exit 1
fi
api="${NOTIFY_API:-https://api.telegram.org}"
python3 - "$config" "$api" "$message" <<'PY'
import json
import sys
import urllib.parse
import urllib.request

config_path, api, message = sys.argv[1], sys.argv[2], sys.argv[3]
with open(config_path, encoding="utf-8") as handle:
    config = json.load(handle)
form = urllib.parse.urlencode(
    {
        "chat_id": config["chatId"],
        "text": "Bikepath loop: " + message,
        "disable_web_page_preview": "true",
    }
).encode()
url = f"{api}/bot{config['botToken']}/sendMessage"
try:
    with urllib.request.urlopen(url, data=form, timeout=15) as response:
        accepted = json.load(response).get("ok", False)
except Exception as error:
    sys.stderr.write(f"notify: send failed ({type(error).__name__})\n")
    sys.exit(1)
if not accepted:
    sys.stderr.write("notify: send failed (the API said not ok)\n")
    sys.exit(1)
print("notify: sent")
PY
