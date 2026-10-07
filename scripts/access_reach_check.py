import sys

from pyproj import Transformer

from bikeplan.access import in_scope_places, places, reach, snap_points
from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.stress import score_edges

snapshot, region_file = sys.argv[1:3]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
aaa = {key for key, score in score_edges(graph, profile).items() if score["aaa"]}
to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
found = places(snapshot)
for place in found:
    place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
kept = in_scope_places(found, graph.graph["boundary"], region.analysis_buffer_m)
nodes, _ = snap_points([(p["x"], p["y"]) for p in kept], graph)
sources = [node for node in nodes if node is not None]
results = reach(graph, sources, region.access.reach_m, region.access.detour_max, aaa)
within = sum(len(r.within) for r in results)
safe = sum(len(r.safe) for r in results)
with_safe = sum(1 for r in results if len(r.safe) > 1)
print(f"places {len(sources)} aaa edges {len(aaa)}")
print(f"home-place pairs in reach {within} safe {safe}")
print(f"places with a safe route to another node {with_safe}")
