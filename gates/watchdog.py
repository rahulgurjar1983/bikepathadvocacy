import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

STATUS = Path(".ralph/status.json")
USAGE = Path(".ralph/model-usage.jsonl")
STATE = Path(".ralph/watchdog.json")
REPAIR_NOTE = Path(".ralph/repair-note")
RESTART_KEYS = ("heartbeat", "turns")
NOTIFY = Path(__file__).resolve().parents[1] / "scripts" / "notify.sh"
PULLS = "https://github.com/rahulgurjar1983/bikepathadvocacy/pulls"
HEARTBEAT_LIMIT = datetime.timedelta(minutes=15)
TURN_LIMIT = datetime.timedelta(hours=4)
TIMEOUT_RUN = 3
QUIET_PHASES = ("idle", "quota_wait")


def now():
    stamp = os.environ.get("WATCHDOG_NOW")
    if stamp:
        return datetime.datetime.fromisoformat(stamp)
    return datetime.datetime.now(datetime.UTC)


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def usage_rows():
    if not USAGE.exists():
        return []
    return [json.loads(line) for line in USAGE.read_text().splitlines() if line.strip()]


def problems(status, rows, turn_at, clock):
    found = {}
    beat = status.get("heartbeat_at")
    if beat is None:
        found["heartbeat"] = "the loop has written no heartbeat"
    else:
        age = clock - datetime.datetime.fromisoformat(beat)
        if age > HEARTBEAT_LIMIT:
            found["heartbeat"] = f"no heartbeat for {int(age.total_seconds() // 60)} minutes"
    idle = clock - turn_at
    if status.get("phase") not in QUIET_PHASES and idle > TURN_LIMIT:
        hours = idle.total_seconds() / 3600
        found["turns"] = f"no model turn has finished for {hours:.1f} hours"
    last = rows[-TIMEOUT_RUN:]
    if len(last) == TIMEOUT_RUN and all(row.get("exit") == 124 for row in last):
        idents = {row.get("row") for row in last}
        if len(idents) == 1:
            ident = idents.pop()
            found[f"timeouts:{ident}"] = (
                f"the last {TIMEOUT_RUN} model turns on {ident} all hit the time bound"
            )
    return found


def message(text, status):
    parts = [
        f"phase {status.get('phase', 'unknown')}",
        f"row {status.get('row', 'none')}",
        f"PR {status.get('pr', 'none')}",
        f"reason {status.get('reason', 'none')}",
    ]
    return f"watchdog: {text}; {', '.join(parts)}. Open PRs: {PULLS}"


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temporary.replace(STATE)


def restart(command, text):
    REPAIR_NOTE.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_NOTE.write_text(f"the watchdog restarted the loop because {text}\n")
    result = subprocess.run(["bash", "-c", command], capture_output=True)
    return result.returncode == 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gates.watchdog")
    parser.add_argument("--restart")
    args = parser.parse_args(argv)
    clock = now()
    status = read_json(STATUS, {})
    rows = usage_rows()
    state = read_json(STATE, {})
    if state.get("turns") != len(rows) or "turn_at" not in state:
        state["turns"] = len(rows)
        state["turn_at"] = clock.isoformat()
    found = problems(status, rows, datetime.datetime.fromisoformat(state["turn_at"]), clock)
    sent = [key for key in state.get("sent", []) if key in found]
    sender = os.environ.get("WATCHDOG_NOTIFY", str(NOTIFY))
    failed = False
    for key in sorted(found):
        if key in sent:
            continue
        text = found[key]
        if args.restart and key in RESTART_KEYS:
            if restart(args.restart, text):
                text = f"{text}; restarted the loop"
            else:
                text = f"{text}; restart failed"
                failed = True
        result = subprocess.run([sender, message(text, status)], capture_output=True)
        if result.returncode != 0:
            sys.stderr.write(f"watchdog: send failed for {key}\n")
            failed = True
            continue
        sent.append(key)
    state["sent"] = sorted(sent)
    save(state)
    if failed:
        return 1
    print(f"watchdog: {len(found)} problem(s), {len(sent)} sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
