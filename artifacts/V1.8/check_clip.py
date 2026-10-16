import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

parser = argparse.ArgumentParser()
parser.add_argument("clip", type=Path)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
files = [args.clip / name for name in ("lines.geojson", "layers.json", "review.yaml")]
layers = json.loads(files[1].read_text())
lines = json.loads(files[0].read_text())
assert yaml.safe_load(files[2].read_text()) == {"public": False}
assert set(layers["inside_km"]) <= set(layers["network_km"])
assert all(layers["inside_km"][k] <= layers["network_km"][k] for k in layers["inside_km"])
assert lines["features"]
ignored = subprocess.run(
    ["git", "check-ignore", *map(str, files)], check=True, capture_output=True, text=True
)
assert len(ignored.stdout.splitlines()) == len(files)
args.out.write_text(
    json.dumps(
        {
            "source_sha256": layers["source_sha256"],
            "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            "layers_inside": len(layers["inside_km"]),
            "clipped_features": len(lines["features"]),
            "verdict_counts": {},
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
