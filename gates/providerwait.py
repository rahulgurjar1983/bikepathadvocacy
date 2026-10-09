import argparse
import datetime
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

RESET = re.compile(
    r"(?:resets?|try again at|available at)\s+"
    r"(?:(?P<date>[a-z]+\s+\d{1,2}(?:,?\s+\d{4})?)\s*,?\s*)?"
    r"(?P<clock>\d{1,2}(?::\d{2})?\s*(?:am|pm))"
    r"(?:\s*\((?P<zone>[a-z_/+-]+)\))?",
    re.IGNORECASE,
)


def messages(path: Path) -> list[str]:
    found = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            found.append(line)
            continue
        if not isinstance(record, dict):
            continue
        if record.get("type") == "result":
            found.append(str(record.get("result", "")))
        elif record.get("type") == "error":
            found.append(str(record.get("message", "")))
        elif record.get("type") == "turn.failed":
            found.append(str(record.get("error", {}).get("message", "")))
    return found


def reset_time(message: str, now: datetime.datetime) -> datetime.datetime | None:
    match = RESET.search(message)
    if match is None:
        return None
    try:
        zone_name = match["zone"] or os.environ.get("TZ")
        if zone_name:
            zone = ZoneInfo(zone_name)
        else:
            with Path("/etc/localtime").open("rb") as handle:
                zone = ZoneInfo.from_file(handle)
        local_now = now.astimezone(zone)
        clock = re.sub(r"\s+", "", match["clock"]).upper()
        pattern = "%I:%M%p" if ":" in clock else "%I%p"
        clock_time = datetime.datetime.strptime(clock, pattern).time()
        day = local_now.date()
        if match["date"]:
            text = match["date"].replace(",", "")
            explicit_year = bool(re.search(r"\b\d{4}$", text))
            if not explicit_year:
                text += f" {local_now.year}"
            for pattern in ("%b %d %Y", "%B %d %Y"):
                try:
                    day = datetime.datetime.strptime(text, pattern).date()
                    break
                except ValueError:
                    continue
            else:
                return None
        target = datetime.datetime.combine(day, clock_time, zone)
        if target <= local_now:
            if match["date"]:
                if explicit_year:
                    return None
                target = target.replace(year=target.year + 1)
            else:
                target += datetime.timedelta(days=1)
        return target
    except (ValueError, ZoneInfoNotFoundError):
        return None


def retry_seconds(paths: list[Path], default: int, *, now: datetime.datetime | None = None) -> int:
    now = now or datetime.datetime.now(datetime.UTC)
    waits = []
    for path in paths:
        resets = [reset_time(message, now) for message in messages(path)]
        known = [value for value in resets if value is not None]
        waits.append(
            min(int((value - now).total_seconds()) + 60 for value in known) if known else default
        )
    return max(0, min(waits, default=default))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--default", type=int, required=True)
    parser.add_argument("logs", type=Path, nargs="+")
    args = parser.parse_args(argv)
    print(retry_seconds(args.logs, args.default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
