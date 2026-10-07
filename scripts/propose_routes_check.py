import sys

from pyproj import Transformer

from bikeplan.access import (
    homes,
    in_scope_places,
    places,
    population_units,
    reach,
    snap_points,
)
from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.propose import planning_network, route_fixes, trip_values
from bikeplan.stress import score_edges

snapshot, region_file = sys.argv[1:3]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
planning = planning_network(graph, profile, region)
aaa = {key for key, item in score_edges(graph, profile).items() if item["aaa"]}
to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
found = places(snapshot)
for place in found:
    place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
kept = in_scope_places(found, graph.graph["boundary"], region.analysis_buffer_m)
nodes, _ = snap_points([(p["x"], p["y"]) for p in kept], graph)
placed = [(p["type"], n) for p, n in zip(kept, nodes, strict=True) if n is not None]
results = reach(graph, [n for _, n in placed], region.access.reach_m, region.access.detour_max, aaa)
resident = homes(population_units(snapshot, graph.graph["crs"]), graph, graph.graph["boundary"])
weights = {name: item.weight for name, item in region.destinations.items()}
values = trip_values(resident.people, placed, results, weights)
print(f"unsafe trips {len(values)} total value {sum(values.values()):.2f}")
fixes = route_fixes(
    graph, planning, placed, results, values, region.access.reach_m, region.access.detour_max
)
print(f"route fixes {len(fixes)} total value {sum(fixes.values()):.2f}")
print(f"largest route fix {max(len(item) for item in fixes)} elements")
print(f"best route fix value {max(fixes.values()):.2f}")
