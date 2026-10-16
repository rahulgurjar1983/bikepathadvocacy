import json
import sys
from pathlib import Path

import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString, Point

from bikeplan.config import load_profile, load_region
from bikeplan.edition import build_options_report
from bikeplan.network import build
from bikeplan.stress import score_edges

region_file, snapshot, out = sys.argv[1:4]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
scores = score_edges(graph, profile)
options, marks, joined = build_options_report(graph, region, profile, snapshot, scores)
boundary = graph.graph["boundary"]
widened = boundary.buffer(profile.network.boundary_buffer_m)
to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
places_outside = [
    item["id"]
    for item in joined.joined
    if not boundary.covers(Point(*(graph.nodes[item["node"]][k] for k in ("x", "y"))))
    and not widened.covers(Point(*(graph.nodes[item["node"]][k] for k in ("x", "y"))))
]
lengths = nx.Graph()
whole = nx.Graph()
for u, v, data in graph.edges(data=True):
    if not data["bike_ok"]:
        continue
    shape = data.get("geometry") or LineString(
        [(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in (u, v)]
    )
    for target, keep in ((whole, True), (lengths, widened.covers(shape))):
        if keep and (not target.has_edge(u, v) or target[u][v]["w"] > data["length_m"]):
            target.add_edge(u, v, w=data["length_m"])
limit_m = profile.network.max_trip_km * 1000
trip_counts = {}
longest = 0.0
for option in options:
    totals = option["steps"][0]["totals"]
    trip_counts[option["id"]] = totals["trips"]
people = sorted(joined.joined, key=lambda item: item["id"])
pairs = 0
whole_pairs = 0
for index, first in enumerate(people):
    reach = nx.single_source_dijkstra_path_length(lengths, first["node"], weight="w")
    far = nx.single_source_dijkstra_path_length(whole, first["node"], cutoff=limit_m, weight="w")
    whole_pairs += sum(second["node"] in far for second in people[index + 1 :])
    for second in people[index + 1 :]:
        distance = reach.get(second["node"])
        if distance is not None and distance <= limit_m:
            pairs += 1
            longest = max(longest, distance)
outside_links = []
for option in options:
    for line in option["lines"]:
        a, b = line["line"]
        shape = LineString([to_metres.transform(*a), to_metres.transform(*b)])
        if not widened.buffer(1.0).covers(shape):
            outside_links.append((option["id"], a, b))
proof = {
    "row": "M1.1",
    "boundary_buffer_m": profile.network.boundary_buffer_m,
    "max_trip_km": profile.network.max_trip_km,
    "places_joined": len(joined.joined),
    "places_unjoined": len(joined.unjoined),
    "joined_places_outside_widened_boundary": places_outside,
    "links_outside_widened_boundary": len(outside_links),
    "first_link_outside": outside_links[:1],
    "trips_by_option_at_step_0": trip_counts,
    "pairs_within_limit_by_independent_route": pairs,
    "pairs_within_limit_if_routes_may_leave_the_area": whole_pairs,
    "longest_counted_route_m": round(longest, 1),
}
text = json.dumps(proof, indent=2, sort_keys=True) + "\n"
Path(out).write_text(text)
sys.stdout.write(text)
assert not places_outside and not outside_links
assert set(trip_counts.values()) == {pairs}
assert longest <= limit_m
