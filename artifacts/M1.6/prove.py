import json
import sys
from pathlib import Path

from bikeplan.config import load_profile, load_region
from bikeplan.corridors import indicative_routes, load_corridors
from bikeplan.edition import CORRIDORS, buffered_box, build_options_report
from bikeplan.network import build
from bikeplan.stress import score_edges

region_file, snapshot, out = sys.argv[1:4]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
scores = score_edges(graph, profile)
options, marks, joined = build_options_report(graph, region, profile, snapshot, scores)
boundary = json.loads((Path(snapshot) / "boundary.geojson").read_text())
corridors = load_corridors(CORRIDORS, buffered_box(boundary, region.analysis_buffer_m))
routes = indicative_routes(graph, corridors, getattr(profile.network, "snap_max_m", 300.0))
names = ("Matraville Public School", "Bayside High School", "Arncliffe Public School")
proof = {
    "row": "M1.6",
    "snap_max_m": getattr(profile.network, "snap_max_m", None),
    "joined": len(joined.joined),
    "unjoined": [
        {"name": item["name"], "type": item["type"], "reason": item["reason"]}
        for item in joined.unjoined
    ],
    "named": {
        name: [
            "joined" if item in joined.joined else "unjoined"
            for item in joined.joined + joined.unjoined
            if name in item["name"]
        ]
        for name in names
    },
    "routes": {route.id: {"nodes": len(route.nodes), "km": round(route.km, 2)} for route in routes},
    "no_route": [route.id for route in routes if not route.nodes],
}
Path(out).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
sys.stdout.write(json.dumps(proof, indent=2, sort_keys=True)[:4000])
