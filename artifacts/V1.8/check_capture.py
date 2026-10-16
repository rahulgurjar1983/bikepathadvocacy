import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

parser = argparse.ArgumentParser()
parser.add_argument("capture", type=Path)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
files = [args.capture / name for name in ("source", "source-manifest.json", "review.yaml")]
manifest = json.loads(files[1].read_text())
sums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
assert manifest["sha256"] == sums["source"]
assert manifest["bytes"] == files[0].stat().st_size
assert manifest["path"] == "source"
assert all(manifest[key] for key in ("url", "licence", "attribution", "retrieved_at"))
assert yaml.safe_load(files[2].read_text()) == {"public": False}
ignored = subprocess.run(
    ["git", "check-ignore", *map(str, files)], check=True, capture_output=True, text=True
)
assert len(ignored.stdout.splitlines()) == len(files)
status = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=all", "--", str(args.capture)],
    check=True,
    capture_output=True,
    text=True,
)
assert not status.stdout
args.out.write_text(
    json.dumps({"sha256": sums, "verdict_counts": {}}, indent=2, sort_keys=True) + "\n"
)
