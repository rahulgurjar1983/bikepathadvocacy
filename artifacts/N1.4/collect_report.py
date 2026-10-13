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
from bikeplan.network_report import choose, network_report
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
to_lonlat = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
found = places(SNAPSHOT)
for place in found:
    place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
found = in_scope_places(found, graph.graph["boundary"], region.analysis_buffer_m)
joined = join_places(graph, found, [], profile.network)
options = build_options(graph, joined, ratings, profile.network)
table = link_table(graph, ratings)
fixes = link_fixes(graph, table, fits, profile, weights)
streets = link_streets(graph)


def point(node):
    data = graph.nodes[node]
    lon, lat = to_lonlat.transform(data["x"], data["y"])
    return [round(lon, 5), round(lat, 5)]


report = []
for item in options:
    ladder = build_ladder(table, item["links"], joined.joined, fixes, weights, streets)
    owner = {link: index for index, work in enumerate(ladder["works"]) for link in work["links"]}
    report.append(
        {
            "id": item["id"],
            "name": item["name"],
            "same_as": item["same_as"],
            "km": item["km"],
            "steps": ladder["steps"],
            "works": ladder["works"],
            "no_fix": ladder["no_fix"],
            "lines": [
                {
                    "work": owner.get(link),
                    "ok": table[link]["all_ages"],
                    "line": [point(link[0]), point(link[1])],
                }
                for link in item["links"]
            ],
        }
    )
marks = [
    {
        "lon": point(place["node"])[0],
        "lat": point(place["node"])[1],
        "type": place["type"],
        "name": place["name"],
    }
    for place in joined.joined
]
head, body = network_report(report, profile.network.recommend_share, marks)
Path(OUT).write_text(
    f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    f"<title>Network options in {region.name}</title>{head}</head><body>"
    f"<h1>Network options in {region.name}</h1>{body}</body></html>\n"
)
choice = choose(report, profile.network.recommend_share)
print(choice["pick"], choice["step"], choice["streets"][:5], len(choice["streets"]))
print("seconds", round(time.time() - start, 1))
