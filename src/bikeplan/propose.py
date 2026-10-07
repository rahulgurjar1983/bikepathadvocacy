import heapq
from collections import defaultdict
from typing import NamedTuple

from shapely.geometry import Point

from bikeplan.access import Reach
from bikeplan.fit import junction_fixes, segment_fit
from bikeplan.network import bike_segments
from bikeplan.stress import edge_aaa, own_lts, raise_for_crossings


class Planning(NamedTuple):
    edges: dict
    elements: dict


def segment_elements(graph, profile, weights) -> tuple[dict, set]:
    elements = {}
    missing = set()
    for segment_id, segment in bike_segments(graph).items():
        result = segment_fit(segment, profile, weights)
        if result is None or result["status"] == "no_fit":
            missing.add(segment_id)
        elif result["status"] == "fix":
            elements[f"segment:{segment_id}"] = {
                "kind": "segment",
                "segment": segment_id,
                "fix": result["fix"],
                "score": result["score"],
                "robust": result["robust"],
                "km": result["km"],
                "length_m": max(data["length_m"] for _, data in segment["edges"]),
            }
    return elements, missing


def junction_elements(graph, profile, weights) -> dict:
    return {
        f"junction:{item['junction']}": {
            "kind": "junction",
            "junction": item["junction"],
            "fix": item["fix"],
            "score": item["disruption"]["refuges"] * weights.refuge
            + item["disruption"]["signals"] * weights.signal,
            "legs": tuple(item["legs"]),
        }
        for item in junction_fixes(graph, profile)
    }


def crossing_needs(key: tuple, data: dict, junctions: dict) -> tuple:
    found = tuple(
        name
        for name in (f"junction:{key[0]}", f"junction:{key[1]}")
        if name in junctions and data["segment_id"] in junctions[name]["legs"]
    )
    return found


def planning_network(graph, profile, region) -> Planning:
    weights = region.proposals.disruption_weights
    metres = region.proposals.metres_per_point
    segments, missing = segment_elements(graph, profile, weights)
    junctions = junction_elements(graph, profile, weights)
    own = {(u, v, k): own_lts(d, profile) for u, v, k, d in graph.edges(keys=True, data=True)}
    final, _ = raise_for_crossings(graph, own, profile)
    edges = {}
    used = set()
    for u, v, k, data in graph.edges(keys=True, data=True):
        key = (u, v, k)
        if not data["bike_ok"]:
            continue
        own_ok = edge_aaa(data, own[key], profile)
        cost = data["length_m"]
        needs: tuple = ()
        if not own_ok:
            name = f"segment:{data['segment_id']}"
            if data["segment_id"] in missing or name not in segments:
                continue
            element = segments[name]
            cost += metres * element["score"] * data["length_m"] / element["length_m"]
            needs = (name,)
        elif not edge_aaa(data, final[key], profile):
            needs = crossing_needs(key, data, junctions)
            if not needs:
                continue
            cost += sum(metres * junctions[name]["score"] / 2 for name in needs)
        edges[key] = {"cost": cost, "needs": needs}
        used.update(needs)
    elements = {name: item for name, item in {**segments, **junctions}.items() if name in used}
    return Planning(edges, elements)


def trip_values(people: dict, placed: list, results: list[Reach], weights: dict) -> dict:
    in_reach: dict = defaultdict(lambda: defaultdict(int))
    for (kind, _), found in zip(placed, results, strict=True):
        for node in found.within:
            in_reach[node][kind] += 1
    total = sum(people.values())
    values = {}
    for index, ((kind, _), found) in enumerate(zip(placed, results, strict=True)):
        for node in found.within:
            if node in found.safe or node not in people:
                continue
            weight = sum(weights[name] for name in in_reach[node])
            if not weight:
                continue
            values[(index, node)] = (
                100 * people[node] * weights[kind] / (total * in_reach[node][kind] * weight)
            )
    return values


def pickable(graph, planning: Planning) -> set:
    boundary = graph.graph["boundary"]
    inside = {
        f"segment:{segment_id}": segment["inside_m"] > 0
        for segment_id, segment in bike_segments(graph).items()
    }
    for name, element in planning.elements.items():
        if element["kind"] == "junction":
            node = graph.nodes[element["junction"]]
            inside[name] = boundary.intersects(Point(node["x"], node["y"]))
    return {name for name in planning.elements if inside.get(name)}


def planned_routes(incoming: dict, place, reach_m: float) -> dict:
    order = {node: number for number, node in enumerate(incoming)}
    best = {place: (0.0, 0.0, frozenset())}
    queue = [(0.0, 0.0, order.get(place, -1), place)]
    while queue:
        cost, length, _, node = heapq.heappop(queue)
        if best[node][:2] != (cost, length):
            continue
        for source, edge_cost, edge_length, needs in incoming.get(node, ()):
            total = length + edge_length
            if total > reach_m:
                continue
            step = cost + edge_cost
            if source in best and best[source][:2] <= (step, total):
                continue
            best[source] = (step, total, best[node][2] | needs)
            heapq.heappush(queue, (step, total, order.get(source, -1), source))
    return best


def route_fixes(
    graph,
    planning: Planning,
    placed: list,
    results: list[Reach],
    values: dict,
    reach_m: float,
    detour_max: float,
) -> dict:
    allowed = pickable(graph, planning)
    incoming: dict = defaultdict(list)
    for (u, v, k), item in sorted(planning.edges.items(), key=lambda pair: repr(pair[0])):
        if set(item["needs"]) <= allowed:
            length = graph[u][v][k]["length_m"]
            incoming[v].append((u, item["cost"], length, frozenset(item["needs"])))
    fixes: dict = defaultdict(float)
    wanted: dict = defaultdict(list)
    for index, node in sorted(values):
        wanted[index].append(node)
    for index, homes in sorted(wanted.items()):
        place = placed[index][1]
        routes = planned_routes(incoming, place, reach_m)
        for home in homes:
            if home not in routes:
                continue
            _, length, elements = routes[home]
            if elements and length <= detour_max * results[index].within[home]:
                fixes[elements] += values[(index, home)]
    return dict(fixes)
