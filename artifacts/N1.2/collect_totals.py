import json
import sys
import time
from pathlib import Path

from pyproj import Transformer

from bikeplan.access import in_scope_places, places
from bikeplan.config import load_profile, load_region
from bikeplan.fit import segment_fit
from bikeplan.network import bike_segments, build
from bikeplan.options import build_options, join_places
from bikeplan.rating import model_ratings
from bikeplan.stress import score_edges

REGION, SNAPSHOT, OUT = sys.argv[1:4]
start = time.time()

region = load_region(REGION)
profile = load_profile(region.profile)
graph = build(SNAPSHOT, region, profile)
weights = region.proposals.disruption_weights
scores = score_edges(graph, profile)
fits = {
    segment_id: segment_fit(segment, profile, weights)
    for segment_id, segment in bike_segments(graph).items()
}
ratings = model_ratings(graph, scores, fits)
to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
found = places(SNAPSHOT)
for place in found:
    place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
found = in_scope_places(found, graph.graph["boundary"], region.analysis_buffer_m)
joined = join_places(graph, found, [], profile.network)
options = build_options(graph, joined, ratings, profile.network)
result = {
    "region": region.id,
    "options": [
        {
            "id": item["id"],
            "name": item["name"],
            "same_as": item["same_as"],
            "link_count": len(item["links"]),
            "km": round(item["km"], 3),
            "totals": item["totals"],
        }
        for item in options
    ],
}
Path(OUT).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
for item in result["options"]:
    totals = item["totals"]
    print(
        item["id"],
        item["km"],
        totals["safe_trips"],
        totals["trips"],
        round(totals["score"], 2),
        round(totals["assumed_share"], 3),
    )
print("seconds", round(time.time() - start, 1))
