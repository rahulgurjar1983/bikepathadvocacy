import random

import networkx as nx

NODES = {
    0: (0, 0),
    1: (100, 0),
    2: (200, 0),
    3: (300, 0),
    4: (0, 100),
    5: (150, 100),
    6: (300, 100),
    7: (150, -50),
    20: (2000, 0),
    21: (2100, 0),
}
PATH_ROADS = [
    (0, 1, 100.0, 4, True, False),
    (1, 2, 100.0, 4, True, False),
    (2, 3, 100.0, 4, True, False),
    (0, 4, 100.0, 1, False, False),
    (4, 5, 150.0, 1, False, False),
    (5, 6, 150.0, 1, False, False),
    (6, 3, 100.0, 1, False, False),
    (0, 7, 140.0, 3, False, False),
    (7, 3, 140.0, 3, False, False),
    (20, 21, 100.0, 1, False, False),
]
SQUARE_NODES = {0: (0, 0), 1: (100, 0), 2: (100, 100), 3: (0, 100)}
SQUARE_ROADS = [
    (0, 1, 100.0, 1, False, False),
    (1, 2, 100.0, 1, False, False),
    (2, 3, 100.0, 1, False, False),
    (3, 0, 100.0, 1, False, False),
    (0, 2, 150.0, 1, False, False),
    (1, 3, 150.0, 1, False, False),
]


def street_graph(nodes, roads, seed=None):
    rng = random.Random(seed)
    order = sorted(nodes)
    roads = list(roads)
    if seed is not None:
        rng.shuffle(order)
        rng.shuffle(roads)
    graph = nx.MultiDiGraph()
    for node in order:
        graph.add_node(node, x=float(nodes[node][0]), y=float(nodes[node][1]))
    ratings = {}
    for a, b, length, level, separated, no_fix in roads:
        for u, v in ((a, b), (b, a)):
            graph.add_edge(u, v, 0, bike_ok=True, length_m=length, highway="residential")
            ratings[(u, v, 0)] = {"lts": level, "separated": separated, "no_fix": no_fix}
    return graph, ratings


def place(osm_id, kind, x, y, name=""):
    return {"osm_id": osm_id, "type": kind, "name": name or osm_id, "x": float(x), "y": float(y)}


def pinned_places(nodes, ids, seed=None):
    found = [
        place(f"node/{i}", "school", *nodes[n]) for i, n in zip(ids, sorted(nodes), strict=True)
    ]
    if seed is not None:
        random.Random(seed).shuffle(found)
    return found
