import argparse
import datetime
import json
from pathlib import Path

PATH = Path(".ralph/status.json")


def now():
    return datetime.datetime.now(datetime.UTC)


def save(record):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(PATH)


def write(phase, *, row=None, reason=None, retry_seconds=None, pr=None):
    record = {"phase": phase, "heartbeat_at": now().isoformat()}
    if pr is None and row is not None and phase in ("running", "quota_wait") and PATH.exists():
        previous = json.loads(PATH.read_text())
        if previous.get("row") == row:
            pr = previous.get("pr")
    for key, value in (("row", row), ("reason", reason), ("pr", pr)):
        if value is not None:
            record[key] = value
    if retry_seconds is not None:
        record["retry_at"] = (now() + datetime.timedelta(seconds=retry_seconds)).isoformat()
    save(record)


def heartbeat():
    record = json.loads(PATH.read_text()) if PATH.exists() else {"phase": "starting"}
    record["heartbeat_at"] = now().isoformat()
    save(record)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("phase")
    parser.add_argument("--row")
    parser.add_argument("--reason")
    parser.add_argument("--retry-seconds", type=float)
    parser.add_argument("--pr", type=int)
    args = parser.parse_args(argv)
    if args.phase == "heartbeat":
        heartbeat()
    elif args.phase == "retry":
        record = json.loads(PATH.read_text())
        record["retry_at"] = (now() + datetime.timedelta(seconds=args.retry_seconds)).isoformat()
        record["heartbeat_at"] = now().isoformat()
        save(record)
    else:
        write(
            args.phase,
            row=args.row,
            reason=args.reason,
            retry_seconds=args.retry_seconds,
            pr=args.pr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
