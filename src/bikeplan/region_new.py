import json
import re
from pathlib import Path
from urllib.parse import urlencode

import yaml

from bikeplan.config import PROFILE_DIR, ConfigError, load_region
from bikeplan.snapshot import OverpassError, read_url

NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"
MIN_ADMIN_LEVEL = 5
MAX_ADMIN_LEVEL = 10
PLACE_WORDS = {
    "council",
    "city",
    "of",
    "the",
    "shire",
    "municipality",
    "municipal",
    "borough",
    "district",
    "county",
}
TEMPLATE = Path(__file__).resolve().parents[2] / "regions" / "templates" / "new-region.yaml"


class RegionNewError(Exception):
    pass


def admin_level(item: dict) -> int | None:
    value = (item.get("extratags") or {}).get("admin_level")
    return int(value) if value and str(value).isdigit() else None


def search(name: str, endpoint: str = NOMINATIM_ENDPOINT) -> list[dict]:
    query = urlencode(
        {"q": name, "format": "jsonv2", "addressdetails": 1, "extratags": 1, "limit": 20}
    )
    try:
        found = json.loads(read_url(f"{endpoint}?{query}"))
    except (OverpassError, ValueError) as error:
        raise RegionNewError(f"{endpoint}: search failed: {error}") from error
    return [
        item
        for item in found
        if item.get("osm_type") == "relation"
        and admin_level(item) is not None
        and MIN_ADMIN_LEVEL <= admin_level(item) <= MAX_ADMIN_LEVEL
    ]


def describe(number: int, item: dict) -> str:
    return (
        f"{number}. {item['display_name']} "
        f"(admin level {admin_level(item)}, relation {item['osm_id']})"
    )


def slug(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return "-".join([w for w in words if w not in PLACE_WORDS] or words)


def profile_for(country: str, subdivision: str) -> str:
    for candidate in (subdivision.lower(), country.lower()):
        if (PROFILE_DIR / f"{candidate}.yaml").exists():
            return candidate
    return "generic"


def settings_for(profile: str) -> dict:
    template = yaml.safe_load(TEMPLATE.read_text())
    adapters = template["adapters"].get(profile, template["adapters"]["default"])
    settings = template["settings"]
    return {
        "analysis_buffer_m": settings.pop("analysis_buffer_m"),
        "snapshot": {"osm_date": template["snapshot_date"], "adapters": adapters},
        **settings,
    }


def write_region(
    item: dict, out: str | Path, region_id: str | None = None, like: str | Path | None = None
) -> Path:
    address = item.get("address") or {}
    country = str(address.get("country_code", "")).upper()
    subdivision = address.get("ISO3166-2-lvl4")
    if not country or not subdivision:
        raise RegionNewError(f"{item['display_name']}: the match has no country or subdivision")
    name = item.get("name") or item["display_name"].split(",")[0]
    state = address.get("state")
    place = {
        "id": region_id or f"{subdivision.lower()}-{slug(name)}",
        "name": f"{name}, {state}" if state else name,
        "country": country,
        "subdivision": subdivision,
        "boundary": {"osm_relation": int(item["osm_id"])},
    }
    if like:
        try:
            load_region(like)
        except ConfigError as error:
            raise RegionNewError(str(error)) from error
        raw = yaml.safe_load(Path(like).read_text())
        made = {key: place.get(key, value) for key, value in raw.items()}
    else:
        profile = profile_for(country, subdivision)
        settings = settings_for(profile)
        buffer = settings.pop("analysis_buffer_m")
        made = {**place, "analysis_buffer_m": buffer, "profile": profile, **settings}
    out = Path(out)
    target = out / f"{made['id']}.yaml"
    if target.exists():
        raise RegionNewError(f"{target}: exists; remove it first")
    out.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(made, sort_keys=False))
    try:
        load_region(target)
    except ConfigError as error:
        target.unlink()
        raise RegionNewError(str(error)) from error
    return target
