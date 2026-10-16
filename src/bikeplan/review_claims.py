import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import yaml

from bikeplan.config import ConfigError
from bikeplan.review import OPERATORS, ClaimError, judge
from bikeplan.review_clip import MARKER

WINDOW_DAYS = 14

MEASURES = {
    "network_km_total": lambda t: sum(t["layers"]["network_km"].values()),
    "existing_paths_km": lambda t: t["layers"]["network_km"]["Existing Bike Paths"],
    "to_build_km": lambda t: t["layers"]["network_km"]["To Build"],
    "shared_street_km": lambda t: sum(t["measures"]["shared_street_km_by_lts"].values()),
    "people_within_500_m": lambda t: t["measures"]["people"]["within_500_m"],
    "people_within_1000_m": lambda t: t["measures"]["people"]["within_1000_m"],
    "paved_offroad_share": lambda t: t["measures"]["paved_offroad_share"],
    "schools_near_share": lambda t: (
        t["measures"]["schools"]["within_100_m"] / t["measures"]["schools"]["schools"]
    ),
    "source_schools": lambda t: t["source_schools"],
}


def source_schools(source: bytes) -> int:
    text = source.decode("utf-8")
    start = text.find(MARKER)
    if start < 0:
        raise ConfigError(f"The source page has no {MARKER} object")
    data, _ = json.JSONDecoder().raw_decode(text[start + len(MARKER) :])
    return sum(f["properties"].get("k") == "school" for f in data["points"]["features"])


def check(claim: dict) -> None:
    for key in ("id", "quote", "source"):
        if key not in claim:
            raise ClaimError(f"claim {claim.get('id', '?')}: missing {key}")
    if "outside" in claim:
        return
    if claim.get("measure") not in MEASURES:
        raise ClaimError(f"claim {claim['id']}: unknown measure {claim.get('measure')!r}")
    if claim.get("op") not in OPERATORS or not isinstance(claim.get("value"), int | float):
        raise ClaimError(f"claim {claim['id']}: needs an op and a number value")


def verdicts(claims: list[dict], total: dict) -> list[dict]:
    found = []
    for claim in claims:
        check(claim)
        base = {key: claim[key] for key in ("id", "quote", "source")}
        if "outside" in claim:
            found.append({**base, "verdict": "outside this tool", "reason": claim["outside"]})
            continue
        measured = MEASURES[claim["measure"]](total)
        found.append(
            {
                **base,
                "measure": claim["measure"],
                "op": claim["op"],
                "claimed": claim["value"],
                "measured": measured,
                "verdict": judge(claim, measured),
            }
        )
    return found


def reply_window(reply: dict) -> dict:
    sent = [date.fromisoformat(str(item["date"])) for item in reply.get("sent") or []]
    last = max(sent) if sent else None
    return {
        "sent": last.isoformat() if last else None,
        "window_days": WINDOW_DAYS,
        "public_after": (last + timedelta(days=WINDOW_DAYS)).isoformat() if last else None,
        "replies": len(reply.get("replies") or []),
    }


def write_verdicts(measures, layers, source, claims, reply, out) -> Path:
    private = Path.cwd() / "data/private"
    target = Path(out).absolute()
    if not target.is_relative_to(private) or not target.resolve().is_relative_to(private):
        raise ConfigError("Review verdicts must stay under data/private")
    if target.exists():
        raise ConfigError(f"{target}: already exists; use a new verdicts folder")
    content = Path(source).read_bytes()
    layer_data = json.loads(Path(layers).read_text())
    if hashlib.sha256(content).hexdigest() != layer_data["source_sha256"]:
        raise ConfigError("The source sha256 does not match the clip")
    total = {
        "layers": layer_data,
        "measures": json.loads(Path(measures).read_text()),
        "source_schools": source_schools(content),
    }
    found = verdicts(yaml.safe_load(Path(claims).read_text()), total)
    window = reply_window(yaml.safe_load(Path(reply).read_text()) or {})
    target.mkdir(parents=True)
    (target / "verdicts.json").write_text(json.dumps(found, indent=2, sort_keys=True) + "\n")
    (target / "reply-window.json").write_text(json.dumps(window, indent=2, sort_keys=True) + "\n")
    return target
