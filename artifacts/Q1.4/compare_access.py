import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from bikeplan.access import write_access
from bikeplan.config import config_hash, load_profile, load_region
from bikeplan.network import build

region = load_region("regions/au-nsw-bayside.yaml")
profile = load_profile(region.profile)
snapshot = Path("data/cache/au-nsw-bayside/2026-10-01")
graph = build(snapshot, region, profile)
with tempfile.TemporaryDirectory(prefix="q14-access-") as folder:
    summaries = {
        name: write_access(graph, region, profile, snapshot, Path(folder) / name, assumptions)
        for name, assumptions in [("confirmed", False), ("assumptions", True)]
    }
proof = {
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "config_hash": config_hash(region, profile),
    "snapshot_hash": hashlib.sha256((snapshot / "manifest.json").read_bytes()).hexdigest(),
    "command": "uv run python artifacts/Q1.4/compare_access.py",
    "scope": "Access comparison only; not full Q1.4 proof or field validation",
    "summaries": summaries,
}
Path("artifacts/Q1.4/access-comparison.json").write_text(json.dumps(proof, indent=2) + "\n")
print("Saved artifacts/Q1.4/access-comparison.json")
