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
ratings = {}
for u, v, k, data in graph.edges(keys=True, data=True):
    if not data["bike_ok"]:
        continue
    fit = fits[data["segment_id"]]
    status = fit["status"] if fit else "aaa"
    ratings[(u, v, k)] = {
        "lts": scores[(u, v, k)]["lts"],
        "separated": status == "fix" and fit["fix"] != "quietway",
        "no_fix": status == "no_fit",
    }
to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
found = places(SNAPSHOT)
for place in found:
    place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
found = in_scope_places(found, graph.graph["boundary"], region.analysis_buffer_m)
joined = join_places(graph, found, [], profile.network)
options = build_options(graph, joined, ratings, profile.network)
result = {
    "region": region.id,
    "counts": joined.counts,
    "unjoined": joined.unjoined,
    "options": [
        {**item, "links": [list(link) for link in item["links"]], "link_count": len(item["links"])}
        for item in options
    ],
}
again = build_options(graph, joined, ratings, profile.network)
assert again == options
Path(OUT).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
for item in options:
    print(item["id"], len(item["links"]), round(item["km"], 3), item["same_as"])
print(joined.counts, len(joined.unjoined))
print("seconds", round(time.time() - start, 1))
