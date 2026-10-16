import argparse
import hashlib
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("measures", type=Path)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
file = args.measures / "measures.json"
found = json.loads(file.read_text())
assert found["route_km"] > 0
assert 0 <= found["people"]["within_500_m"] <= found["people"]["within_1000_m"] <= 1
assert found["schools"]["within_100_m"] <= found["schools"]["schools"]
assert set(found["shared_street_km_by_lts"]) == {"1", "2", "3", "4"}
assert found["paved_offroad_km"] + found["unpaved_km"] <= found["route_km"]
subprocess.run(["git", "check-ignore", str(file)], check=True, capture_output=True)
args.out.write_text(
    json.dumps(
        {
            "sha256": {file.name: hashlib.sha256(file.read_bytes()).hexdigest()},
            "measure_keys": sorted(found),
            "verdict_counts": {},
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
