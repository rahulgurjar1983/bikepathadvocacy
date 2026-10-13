import json
import sys
import time
from pathlib import Path

from pyproj import Transformer

from bikeplan.access import in_scope_places, places
from bikeplan.config import load_profile, load_region
from bikeplan.fit import segment_fit
from bikeplan.ladder import build_ladder, link_fixes, link_streets
from bikeplan.network import bike_segments, build
from bikeplan.options import build_options, join_places, link_table
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
table = link_table(graph, ratings)
fixes = link_fixes(graph, table, fits, profile, weights)
streets = link_streets(graph)
result = {"region": region.id, "options": []}
for item in options:
    ladder = build_ladder(table, item["links"], joined.joined, fixes, weights, streets)
    steps = ladder["steps"]
    result["options"].append(
        {
            "id": item["id"],
            "same_as": item["same_as"],
            "link_count": len(item["links"]),
            "work_count": len(ladder["works"]),
            "step_count": len(steps),
            "no_fix": [
                {"street": n["street"], "link_count": len(n["links"]), "km": round(n["km"], 3)}
                for n in ladder["no_fix"]
            ],
            "steps": [
                {
                    "step": s["step"],
                    "works": s["works"],
                    "safe_trips": s["totals"]["safe_trips"],
                    "score": round(s["totals"]["score"], 3),
                    "disruption": {k: round(v, 3) for k, v in s["disruption"].items()},
                }
                for s in steps
            ],
            "works": [
                {
                    k: (round(v, 3) if isinstance(v, float) else v)
                    for k, v in w.items()
                    if k != "links"
                }
                | {"link_count": len(w["links"])}
                for w in ladder["works"]
            ],
        }
    )
Path(OUT).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
for item in result["options"]:
    last = item["steps"][-1]
    print(
        item["id"],
        item["work_count"],
        item["step_count"],
        last["safe_trips"],
        last["score"],
        last["disruption"]["score"],
        len(item["no_fix"]),
    )
print("seconds", round(time.time() - start, 1))
