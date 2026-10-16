from itertools import pairwise
from typing import NamedTuple

import networkx as nx
import numpy as np
import shapely
from networkx.algorithms.approximation import steiner_tree
from shapely.geometry import LineString, Point

from bikeplan.access import SNAP_M, bike_nodes, snap_points, sort_key
from bikeplan.config import Network
from bikeplan.rating import option_totals

NAMES = {
    "calm": "Calm streets",
    "shortest": "Shortest",
    "separated": "Main roads with separation",
    "mesh": "Mesh",
}
NO_BIKE_NODE = f"no bike-legal node within {SNAP_M:g} m"
ISLAND = "no bike route to the main network"


class Joined(NamedTuple):
    joined: list
    unjoined: list
    counts: dict
    audit: dict | None = None
    outside: list | None = None


def entrance_node(place: dict, entrances: list[dict], legal: set):
    valid = [
        item
        for item in entrances
        if item.get("destination") == place["osm_id"]
        and item.get("status") == "confirmed"
        and item.get("source")
        and item.get("bike_accessible") is True
        and item.get("node") in legal
    ]
    return min(valid, key=lambda item: item["id"])["node"] if valid else None


def area_graph(graph, network: Network):
    boundary = graph.graph.get("boundary")
    if boundary is None:
        return graph
    area = boundary.buffer(network.boundary_buffer_m)
    keys = list(graph.edges(keys=True))
    shapes = [
        graph.edges[key].get("geometry")
        or LineString([(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in key[:2]])
        for key in keys
    ]
    shapely.prepare(area)
    inside = shapely.covers(area, np.array(shapes, dtype=object))
    return graph.edge_subgraph(key for key, kept in zip(keys, inside, strict=True) if kept)


def inside_boundary(graph, found: list[dict]) -> list[dict]:
    boundary = graph.graph.get("boundary")
    if boundary is None:
        return found
    shapely.prepare(boundary)
    return [place for place in found if boundary.covers(Point(place["x"], place["y"]))]


def components(graph) -> dict:
    undirected = nx.Graph()
    undirected.add_edges_from((u, v) for u, v, data in graph.edges(data=True) if data["bike_ok"])
    return {
        node: index
        for index, group in enumerate(nx.connected_components(undirected))
        for node in group
    }


def outside_route(full, group: dict, main: int, part: int) -> list | None:
    undirected = nx.Graph()
    for u, v, k, data in full.edges(keys=True, data=True):
        if not data["bike_ok"] or u == v:
            continue
        found = undirected.get_edge_data(u, v)
        if found is None or (data["length_m"], k) < (found["weight"], found["key"]):
            undirected.add_edge(u, v, weight=data["length_m"], key=k)
    start, end = ("outside", "main"), ("outside", "part")
    for node, index in group.items():
        if index in (main, part) and node in undirected:
            undirected.add_edge(start if index == main else end, node, weight=0.0, key=0)
    if start not in undirected or end not in undirected:
        return None
    try:
        _, path = nx.single_source_dijkstra(undirected, start, end, weight="weight")
    except nx.NetworkXNoPath:
        return None
    return [link_id(u, v, undirected[u][v]["key"]) for u, v in pairwise(path[1:-1])]


def join_places(graph, found: list[dict], entrances: list[dict], network: Network) -> Joined:
    wanted = sorted(
        (place for place in inside_boundary(graph, found) if place["type"] in network.place_types),
        key=sort_key,
    )
    full = graph
    graph = area_graph(graph, network)
    legal = set(bike_nodes(graph)[0])
    nearest, _ = snap_points([(place["x"], place["y"]) for place in wanted], graph)
    joined, unjoined = [], []
    for place, near in zip(wanted, nearest, strict=True):
        node = entrance_node(place, entrances, legal)
        via = "entrance"
        if node is None:
            node, via = near, "nearest"
        base = {"id": place["osm_id"], "type": place["type"], "name": place["name"]}
        if node is None:
            unjoined.append(base | {"reason": NO_BIKE_NODE})
        else:
            joined.append(base | {"node": node, "via": via})
    group = components(graph)
    size: dict = {}
    lowest: dict = {}
    for node, index in group.items():
        size[index] = size.get(index, 0) + 1
        lowest[index] = min(lowest.get(index, node), node)
    holding = {group[item["node"]] for item in joined}
    main = min(holding, key=lambda index: (-size[index], lowest[index])) if holding else None
    outside: set = set()
    reached = {main}
    for part in sorted(holding - {main}, key=lambda index: lowest[index]):
        route = outside_route(full, group, main, part)
        if route is not None:
            outside.update(route)
            reached.add(part)
    unjoined += [
        {key: item[key] for key in ("id", "type", "name")} | {"reason": ISLAND}
        for item in joined
        if group[item["node"]] not in reached
    ]
    joined = [item for item in joined if group[item["node"]] in reached]
    unjoined.sort(key=lambda item: sort_key({"osm_id": item["id"]}))
    counts = {
        kind: {
            "joined": sum(item["type"] == kind for item in joined),
            "unjoined": sum(item["type"] == kind for item in unjoined),
        }
        for kind in network.place_types
    }
    inside = {link_id(u, v, k) for u, v, k in graph.edges(keys=True)}
    return Joined(joined, unjoined, counts, None, sorted(outside - inside))


def link_id(u, v, k) -> tuple:
    a, b = sorted((u, v))
    return a, b, k


def link_table(graph, ratings: dict, network: Network | None = None, outside=()) -> dict:
    table: dict = {}
    far = set(outside)
    full = graph
    if network is not None:
        graph = area_graph(graph, network)
    edges = list(graph.edges(keys=True, data=True))
    if far:
        edges += [
            (u, v, k, data)
            for u, v, k, data in full.edges(keys=True, data=True)
            if link_id(u, v, k) in far
        ]
    for u, v, k, data in edges:
        if not data["bike_ok"] or u == v:
            continue
        rating = ratings[(u, v, k)]
        found = table.setdefault(
            link_id(u, v, k),
            {
                "length_m": data["length_m"],
                "level": rating["lts"],
                "separated": rating["separated"],
                "no_fix": rating["no_fix"],
                "all_ages": rating.get("all_ages", rating["lts"] == 1),
                "assumed": rating.get("assumed", False),
                **({"outside": True} if link_id(u, v, k) in far else {}),
            },
        )
        found["length_m"] = min(found["length_m"], data["length_m"])
        found["level"] = max(found["level"], rating["lts"])
        found["separated"] = found["separated"] and rating["separated"]
        found["no_fix"] = found["no_fix"] or rating["no_fix"]
        found["all_ages"] = found["all_ages"] and rating.get("all_ages", rating["lts"] == 1)
        found["assumed"] = found["assumed"] or rating.get("assumed", False)
    return dict(sorted(table.items()))


def link_weight(option: str, link: dict, network: Network) -> float:
    length = link["length_m"]
    if option == "shortest" or (option == "separated" and link["separated"]):
        return length
    factor = network.stress_factor[link["level"] - 1]
    return length * factor * (network.no_fix_factor if link["no_fix"] else 1.0)


def weighted(table: dict, option: str, network: Network) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(sorted({node for key in table for node in key[:2]}))
    for key, link in table.items():
        weight = link_weight(option, link, network)
        a, b, _ = key
        if graph.has_edge(a, b) and graph[a][b]["weight"] <= weight:
            continue
        graph.add_edge(a, b, weight=weight, link=key)
    return graph


def tree_links(table: dict, option: str, terminals: list, network: Network) -> list:
    if len(terminals) < 2:
        return []
    graph = weighted(table, option, network)
    graph = graph.subgraph(nx.node_connected_component(graph, terminals[0])).copy()
    tree = steiner_tree(graph, terminals, weight="weight", method="mehlhorn")
    return sorted(data["link"] for _, _, data in tree.edges(data=True))


def path_links(graph: nx.Graph, path: list) -> list:
    return [graph[a][b]["link"] for a, b in pairwise(path)]


def mesh_links(graph, table: dict, joined: list, network: Network) -> list:
    length_graph = weighted(table, "shortest", network)
    people = sorted(joined, key=lambda item: sort_key({"osm_id": item["id"]}))
    pairs = []
    for index, first in enumerate(people):
        lengths = nx.single_source_dijkstra_path_length(
            length_graph, first["node"], weight="weight"
        )
        pairs += [
            (lengths[second["node"]], first, second)
            for second in people[index + 1 :]
            if second["node"] != first["node"]
        ]
    pairs.sort(
        key=lambda item: (
            item[0],
            sort_key({"osm_id": item[1]["id"]}),
            sort_key({"osm_id": item[2]["id"]}),
        )
    )
    accepted = np.empty(len(pairs), dtype=object)
    count, links = 0, set()
    for _, first, second in pairs:
        line = LineString(
            [
                (graph.nodes[item["node"]]["x"], graph.nodes[item["node"]]["y"])
                for item in (first, second)
            ]
        )
        seen = accepted[:count]
        if count and (shapely.intersects(line, seen) & ~shapely.touches(line, seen)).any():
            continue
        accepted[count] = line
        count += 1
        path = nx.dijkstra_path(length_graph, first["node"], second["node"], weight="weight")
        links.update(path_links(length_graph, path))
    return sorted(links)


def build_options(graph, joined: Joined, ratings: dict, network: Network) -> list[dict]:
    table = link_table(graph, ratings, network, joined.outside or ())
    terminals = sorted({item["node"] for item in joined.joined})
    found = [
        (name, tree_links(table, name, terminals, network))
        for name in ("calm", "shortest", "separated")
    ]
    found.append(("mesh", mesh_links(graph, table, joined.joined, network)))
    options = []
    for name, links in found:
        same = next((item["id"] for item in options if item["links"] == links), None)
        options.append(
            {
                "id": name,
                "name": NAMES[name],
                "links": links,
                "km": sum(table[link]["length_m"] for link in links) / 1000,
                "same_as": same,
                "outside": [link for link in links if table[link].get("outside")],
                "totals": option_totals(
                    table, links, joined.joined, max_trip_m=network.max_trip_km * 1000
                ),
            }
        )
    return options
