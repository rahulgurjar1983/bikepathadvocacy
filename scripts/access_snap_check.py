import sys

from pyproj import Transformer

from bikeplan.access import homes, in_scope_places, places, population_units, snap_points
from bikeplan.config import load_profile, load_region
from bikeplan.network import build

snapshot, region_file = sys.argv[1:3]
region = load_region(region_file)
graph = build(snapshot, region, load_profile(region.profile))
to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
found = places(snapshot)
for place in found:
    place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
boundary = graph.graph["boundary"]
kept = in_scope_places(found, boundary, region.analysis_buffer_m)
nodes, missed = snap_points([(p["x"], p["y"]) for p in kept], graph)
result = homes(population_units(snapshot, graph.graph["crs"]), graph, boundary)
print(f"places {len(found)} in scope {len(kept)} not snapped {len(missed)}")
people = round(sum(result.people.values()))
print(f"home nodes {len(result.people)} people {people} not snapped {round(result.unsnapped)}")
