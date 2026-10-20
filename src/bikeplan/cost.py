import math
from pathlib import Path

import yaml

RATES = Path(__file__).resolve().parents[2] / "references" / "cost-rates.yaml"
ADJECTIVES = {"Victoria": "Victorian"}
CROSSINGS = {
    "raised_zebra_crossing": ("raised_zebra", None),
    "bike_walk_signals": ("signals", None),
    "short_path_crossing": ("short_path", "crossing"),
}


def load_rates(path: Path = RATES) -> dict:
    raw = yaml.safe_load(path.read_text())
    note = f"rough cost from {raw['price_year']} {ADJECTIVES[raw['place']]} rates"
    return {
        "low": raw["range"]["low"],
        "high": raw["range"]["high"],
        "note": note,
        "rates": raw["rates"],
    }


def price(rates: dict, name: str, km: float) -> float | None:
    rate = rates["rates"].get(name)
    if rate is None:
        return None
    return rate["likely"] * (km if rate["unit"] == "per_km" else 1)


def work_cost(work: dict, rates: dict) -> float | None:
    name, extra = CROSSINGS.get(work["fix"], (work["fix"], None))
    cost = price(rates, name, work["km"])
    if cost is None or extra is None:
        return cost
    crossing = price(rates, "signals" if work.get("assumed") else "raised_zebra", 1)
    return None if crossing is None else cost + crossing


def stage_cost(works: list, rates: dict) -> dict:
    costs = [work_cost(work, rates) for work in works]
    likely = sum(cost for cost in costs if cost is not None) / 1_000_000
    missing = sum(cost is None for cost in costs)
    low = likely * rates["low"]
    high = likely * rates["high"]
    if likely == 0:
        text = "cost not known" if missing else "$0"
    else:
        text = f"${math.floor(round(low, 6))} to {math.ceil(round(high, 6))} million"
        if missing:
            text = f"at least {text}"
    return {"likely": likely, "low": low, "high": high, "missing": missing, "text": text}
