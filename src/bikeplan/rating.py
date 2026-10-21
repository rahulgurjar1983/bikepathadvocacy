from itertools import pairwise

import networkx as nx

UNSOURCED = {None, "default", "inferred", "assumed"}
LEVELS = (1, 2, 3, 4)


def assumed_inputs(data: dict, score: dict) -> bool:
    if score["aaa"]:
        return score["all_ages_status"] != "confirmed"
    return any(data.get(field) in UNSOURCED for field in ("speed_source", "adt_source"))


def model_ratings(graph, scores: dict, fits: dict) -> dict:
    ratings = {}
    for u, v, k, data in graph.edges(keys=True, data=True):
        if not data["bike_ok"]:
            continue
        fit = fits[data["segment_id"]]
        status = fit["status"] if fit else "aaa"
        score = scores[(u, v, k)]
        ratings[(u, v, k)] = {
            "lts": score["lts"],
            "all_ages": bool(score["aaa"]),
            "assumed": assumed_inputs(data, score),
            "separated": status == "fix" and fit["fix"] != "quietway",
            "no_fix": status == "no_fit",
        }
    return ratings


def link_graph(table: dict, links: list) -> nx.Graph:
    graph = nx.Graph()
    for key in sorted(links):
        a, b, _ = key
        length = table[key]["length_m"]
        if graph.has_edge(a, b) and graph[a][b]["weight"] <= length:
            continue
        graph.add_edge(a, b, weight=length, link=key)
    return graph


def trip_links(graph: nx.Graph, first: int, second: int) -> list | None:
    if first == second:
        return []
    if first not in graph or second not in graph:
        return None
    try:
        path = nx.dijkstra_path(graph, first, second, weight="weight")
    except nx.NetworkXNoPath:
        return None
    return [graph[a][b]["link"] for a, b in pairwise(path)]


def trip_reach(table: dict, people: list, max_trip_m: float) -> dict:
    graph = link_graph(table, list(table))
    reach = {}
    for item in people:
        node = item["node"]
        if node not in reach:
            reach[node] = (
                nx.single_source_dijkstra_path_length(
                    graph, node, cutoff=max_trip_m, weight="weight"
                )
                if node in graph
                else {node: 0.0}
            )
    return reach


def within_trip_limit(table: dict, people: list, max_trip_m: float | None) -> set | None:
    if max_trip_m is None:
        return None
    reach = trip_reach(table, people, max_trip_m)
    return {
        (first["id"], second["id"])
        for index, first in enumerate(people)
        for second in people[index + 1 :]
        if second["node"] in reach[first["node"]]
    }


def longest_trip_m(table: dict, people: list, max_trip_m: float) -> float:
    reach = trip_reach(table, people, max_trip_m)
    return max(
        (
            reach[first["node"]][second["node"]]
            for index, first in enumerate(people)
            for second in people[index + 1 :]
            if second["node"] in reach[first["node"]]
        ),
        default=0.0,
    )


def option_trips(table: dict, links: list, joined: list, max_trip_m: float | None = None) -> list:
    graph = link_graph(table, links)
    people = sorted(joined, key=lambda item: item["id"])
    near = within_trip_limit(table, people, max_trip_m)
    return [
        (first, second, trip_links(graph, first["node"], second["node"]))
        for index, first in enumerate(people)
        for second in people[index + 1 :]
        if near is None or (first["id"], second["id"]) in near
    ]


def option_totals(
    table: dict,
    links: list,
    joined: list,
    fixed=frozenset(),
    trips: list | None = None,
    max_trip_m: float | None = None,
) -> dict:
    people = sorted(joined, key=lambda item: item["id"])
    types = sorted({item["type"] for item in people})
    places_safe = dict.fromkeys(types, 0)
    served: set = set()
    partners: dict = {item["id"]: [] for item in people}
    safe = 0
    found = option_trips(table, links, joined, max_trip_m) if trips is None else trips
    trip_count = len(found)
    for first, second, path in found:
        if path is not None and all(link in fixed or table[link]["all_ages"] for link in path):
            safe += 1
            served |= {first["id"], second["id"]}
            partners[first["id"]].append(second["id"])
            partners[second["id"]].append(first["id"])
    for item in people:
        places_safe[item["type"]] += item["id"] in served
    km_by_level = dict.fromkeys(LEVELS, 0.0)
    km_all_ages = assumed_km = total_km = 0.0
    for link in links:
        found = table[link]
        km = found["length_m"] / 1000
        mended = link in fixed
        km_by_level[1 if mended else found["level"]] += km
        km_all_ages += km if mended or found["all_ages"] else 0.0
        assumed_km += km if found["assumed"] else 0.0
        total_km += km
    return {
        "trips": trip_count,
        "safe_trips": safe,
        "score": 100 * safe / trip_count if trip_count else 0.0,
        "km_by_level": km_by_level,
        "km_all_ages": km_all_ages,
        "places_safe": places_safe,
        "served": sorted(served),
        "partners": {key: sorted(value) for key, value in partners.items()},
        "assumed_share": assumed_km / total_km if total_km else 0.0,
    }
