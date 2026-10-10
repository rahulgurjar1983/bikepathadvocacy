import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from bikeplan.access import write_access
from bikeplan.config import config_hash, load_profile, load_region
from bikeplan.network import build
from bikeplan.stress import score_edges

region = load_region("regions/au-nsw-bayside.yaml")
profile = load_profile(region.profile)
snapshot = Path("data/cache/au-nsw-bayside/2026-10-01")
graph = build(snapshot, region, profile)
with tempfile.TemporaryDirectory(prefix="q14-access-") as folder:
    summaries = {
        name: write_access(graph, region, profile, snapshot, Path(folder) / name, assumptions)
        for name, assumptions in [("confirmed", False), ("assumptions", True)]
    }
scores = score_edges(graph, profile)
out = Path("data/output/Q1.4/resume-full")
features = json.loads((out / "network.geojson").read_text())["features"]
status_features = [
    item["properties"] for item in features if "all_ages_status" in item["properties"]
]
assert len(status_features) == len(scores)
for item in status_features:
    expected = scores[item["u"], item["v"], item["k"]]
    assert item["all_ages_status"] == expected["all_ages_status"]
    assert item["aaa"] == expected["confirmed_aaa"]
page = (out / "report.html").read_text()
assert "safe for a child to ride alone" not in page
assert "does not guarantee child safety" in page
assert "meets the model" in page
proof = {
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "config_hash": config_hash(region, profile),
    "snapshot_hash": hashlib.sha256((snapshot / "manifest.json").read_bytes()).hexdigest(),
    "command": "uv run python artifacts/Q1.4/compare_access.py",
    "scope": "Fresh full Bayside report and access modes; model evidence, not field validation",
    "full_command": (
        "uv run bikeplan run regions/au-nsw-bayside.yaml "
        "--snapshot data/cache/au-nsw-bayside/2026-10-01 --out data/output/Q1.4/resume-full"
    ),
    "edge_status_counts": dict(
        sorted(Counter(item["all_ages_status"] for item in scores.values()).items())
    ),
    "movement_status_counts": dict(
        sorted(
            Counter(
                item["status"] for score in scores.values() for item in score["movements"]
            ).items()
        )
    ),
    "output_hashes": [
        {"path": file.name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
        for file in sorted(out.iterdir())
        if file.is_file()
    ],
    "status_samples": [
        {
            "edge": list(key),
            **{field: item[field] for field in ("all_ages_status", "safety_reason")},
        }
        for status in ("confirmed", "assumed", "unknown")
        for key, item in list(
            (key, item) for key, item in scores.items() if item["all_ages_status"] == status
        )[:2]
    ],
    "network_status_check": "AAA exports equal confirmed status",
    "public_prose_check": "Model criteria and child safety limits are shown",
    "summaries": summaries,
}
Path("artifacts/Q1.4/access-comparison.json").write_text(json.dumps(proof, indent=2) + "\n")
print("Saved artifacts/Q1.4/access-comparison.json")
