import gzip
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from bikeplan.config import config_hash, load_profile, load_region

root = Path(sys.argv[1]).resolve()
snapshot = root / "tests/fixtures/test-grid/snapshot"
region = load_region(root / "regions/test-grid.yaml")
profile = load_profile(region.profile, root / "profiles")
xml = ET.fromstring(gzip.decompress((snapshot / "network.osm.gz").read_bytes()))
ways = [
    {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")} for way in xml.findall("way")
]
signals = [
    {"node": node.attrib["id"], "tags": tags}
    for node in xml.findall("node")
    for tags in [{tag.attrib["k"]: tag.attrib["v"] for tag in node.findall("tag")}]
    if tags.get("highway") == "traffic_signals"
]
old = (root / "specs/11-generic.md").read_text()
new = (root / "specs/15-review-improvements.md").read_text()
assert "The baseline region score is 25.0" in old
assert "score after of 100.0" in old
assert "tests assert every fact in its table" in old
assert "Main access and picks use confirmed links" in new
assert not (snapshot / "safety_evidence.json").exists()
assert all("adt" not in tags for tags in ways)
assert all(set(item["tags"]) == {"highway"} for item in signals)
proof = {
    "base_commit": subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip(),
    "config_hash": config_hash(region, profile),
    "snapshot_hash": hashlib.sha256((snapshot / "manifest.json").read_bytes()).hexdigest(),
    "required_baseline_score": 25.0,
    "required_after_score": 100.0,
    "residential_adt": {
        "value": profile.road_classes["residential"].adt.value,
        "source": profile.road_classes["residential"].adt.source,
        "assumption": profile.road_classes["residential"].adt.assumption,
    },
    "signals": signals,
    "movement_evidence_present": False,
    "way_adt_evidence_present": False,
    "command": "uv run python artifacts/Q1.4/check_inputs.py /tmp/bikeplan-q14-input-proof",
    "test_command": (
        "uv run --directory /tmp/bikeplan-q14-input-proof pytest tests/test_test_grid.py -q "
        "-k 'baseline_region_score_is_25 or side_streets_at_the_signals_are_lts_1_and_aaa'"
    ),
}
print(json.dumps(proof, indent=2))
