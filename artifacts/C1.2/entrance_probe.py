import gzip
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

snapshot = Path(sys.argv[1])
BIKE = ("yes", "designated", "permissive")
GATES = ("gate", "kissing_gate", "turnstile", "lift_gate")
with gzip.open(snapshot / "network.osm.gz") as handle:
    root = ET.parse(handle).getroot()
bike_gates = []
tagged = 0
for node in root.iter("node"):
    tags = {t.get("k"): t.get("v") for t in node.findall("tag")}
    if "entrance" in tags or tags.get("barrier") in GATES:
        tagged += 1
        if tags.get("bicycle") in BIKE:
            bike_gates.append((float(node.get("lat")), float(node.get("lon"))))
places = json.loads((snapshot / "places.json").read_text())
schools = near = 0
for e in places["elements"]:
    if e.get("tags", {}).get("amenity") != "school":
        continue
    lat = e.get("lat") or e.get("center", {}).get("lat")
    lon = e.get("lon") or e.get("center", {}).get("lon")
    schools += 1
    near += any(math.hypot((a - lat) * 111000, (b - lon) * 92000) < 150 for a, b in bike_gates)
result = {
    "entrance_or_gate_nodes": tagged,
    "with_explicit_bike_access": len(bike_gates),
    "school_points": schools,
    "school_points_with_such_a_node_within_150m": near,
    "school_boundary_polygons_in_snapshot": 0,
    "trip_evidence_block_in_places_json": "trip_evidence" in places,
}
Path("artifacts/C1.2/entrance_probe.json").write_text(json.dumps(result, indent=2, sort_keys=True))
print(json.dumps(result, indent=1))
