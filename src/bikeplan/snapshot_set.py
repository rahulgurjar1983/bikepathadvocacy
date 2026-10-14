import json
from pathlib import Path

import yaml

from bikeplan.adapters import OUTPUT_FILES
from bikeplan.config import load_region

CORE_FILES = ["boundary.geojson", "network.osm.gz", "places.json"]


def expected_files(adapters: list[str]) -> list[str]:
    return CORE_FILES + [OUTPUT_FILES[name] for name in adapters]


def council_problems(council: str, base_region, root: Path) -> list[str]:
    found = sorted((root / "snapshots" / council).glob("*/manifest.json"))
    if not found:
        return [f"{council}: no manifest"]
    manifest = json.loads(found[-1].read_text())
    problems = []
    if manifest.get("region") != council:
        problems.append(f"region {manifest.get('region')} is not {council}")
    if manifest.get("osm_date") != base_region.snapshot.osm_date:
        problems.append(
            f"osm_date {manifest.get('osm_date')} is not {base_region.snapshot.osm_date}"
        )
    have = {entry["name"] for entry in manifest.get("files", [])}
    for name in expected_files(base_region.snapshot.adapters):
        if name not in have:
            problems.append(f"missing {name}")
    return [f"{council}: {text}" for text in problems]


def set_problems(set_file: str | Path, root: str | Path) -> list[str]:
    root = Path(root)
    councils = yaml.safe_load(Path(set_file).read_text())["councils"]
    base_region = load_region(root / "regions" / f"{councils[0]['id']}.yaml")
    problems = []
    for council in councils:
        problems.extend(council_problems(council["id"], base_region, root))
    return problems
