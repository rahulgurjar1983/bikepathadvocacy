import importlib.util
import json
import sys

from bikeplan.config import load_profile
from bikeplan.options import build_options, join_places

spec = importlib.util.spec_from_file_location("option_helpers", "tests/option_helpers.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

NETWORK = load_profile("au-nsw").network
NODES = {0: (0, 0), 1: (100, 0), 2: (200, 0), 3: (300, 0), 4: (0, 100), 5: (300, 100)}
ROADS = [
    (0, 1, 100.0, 2, False, False),
    (1, 2, 100.0, 2, False, False),
    (2, 3, 100.0, 2, False, False),
    (0, 4, 100.0, 1, True, False),
    (4, 5, 300.0, 1, True, False),
    (5, 3, 100.0, 1, True, False),
]
RAIL = {"a": 0, "b": 3, "length_m": 300.0, "label": "railway"}
CASES = {
    "paved": ("asphalt", True, []),
    "grass": ("grass", True, []),
    "candidate": ("asphalt", False, [RAIL]),
}


def run(surface: str, path: bool, corridors: list) -> dict:
    graph, ratings = helpers.street_graph(NODES, ROADS)
    for u, v, _key, data in graph.edges(keys=True, data=True):
        data["segment_id"] = f"s{min(u, v)}{max(u, v)}"
        if {u, v} & {4, 5}:
            data["highway"] = "cycleway" if path else "residential"
            data["surface"] = surface if {u, v} == {4, 5} else "asphalt"
    found = [
        helpers.place("node/1", "school", 0, 0),
        helpers.place("node/2", "station", 300, 0),
    ]
    joined = join_places(graph, found, [], NETWORK)
    return {
        item["id"]: {
            "links": [list(link) for link in item["links"]],
            "km": item["km"],
            "safe_trips": item["totals"]["safe_trips"],
        }
        for item in build_options(graph, joined, ratings, NETWORK, corridors)
    }


with open(sys.argv[1], "w") as handle:
    json.dump({name: run(*case) for name, case in CASES.items()}, handle, indent=1, sort_keys=True)
    handle.write("\n")
