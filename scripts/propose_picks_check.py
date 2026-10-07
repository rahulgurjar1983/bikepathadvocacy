import dataclasses
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
from bikeplan.propose import greedy_picks, planning_network
from bikeplan.stress import score_edges

snapshot, region_file, rounds, pool = sys.argv[1:5]
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
proposals = dataclasses.replace(
    region.proposals, max_projects=int(rounds), candidate_pool=int(pool), min_gain=0.0
)
picked = greedy_picks(
    graph,
    planning,
    placed,
    resident.people,
    weights,
    proposals,
    region.access.reach_m,
    region.access.detour_max,
)
for number, item in enumerate(picked, start=1):
    print(
        f"pick {number} id {item['id']} elements {len(item['elements'])} "
        f"gain {item['gain']:.4f} cost {item['cost']:.1f} score after {item['score_after']:.4f}"
    )
