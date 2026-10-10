import csv
import dataclasses
import hashlib
import heapq
import json
from collections import defaultdict
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

import networkx as nx
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point, mapping
from shapely.ops import substring, transform, unary_union

from bikeplan.access import (
    EdgeTable,
    Reach,
    edge_table,
    last_legs,
    people_gains,
    reach,
    safe_reach,
    scene,
    score_access,
)
from bikeplan.config import Scenario
from bikeplan.fit import FIXES, fixed_edge, junction_fixes, segment_fit
from bikeplan.fit import cross_section as fit_cross_section
from bikeplan.network import bike_segments
from bikeplan.stress import edge_aaa, own_lts, raise_for_crossings, score_edges
from bikeplan.trips import complete_trips, resident_outcomes, snapshot_trip_inputs
from bikeplan.width import check_links, fuse
from bikeplan.works import works_catalog, works_package

CORRIDOR_FIXES = tuple(fix for fix in FIXES if fix != "quietway")
KINDS = ("corridor", "neighbourhood", "route")
PROJECT_FIXES = (*FIXES, "new_path")
DEFAULT_SCENARIOS = (
    Scenario("light", "Parking and lanes count half", {"parking_space": 0.5, "lane_km": 0.5}),
    Scenario("shipped", "Weights as set", {}),
    Scenario("heavy", "Parking and lanes count four times", {"parking_space": 4.0, "lane_km": 4.0}),
)
SNAP_M = 60.0
SIDE_M = 20.0
OPEN_SHARE = 0.3
MIN_PATH_M = 200.0
MAX_PATH_M = 3000.0
LINE_LABELS = {
    ("railway", "rail"): "railway",
    ("highway", "motorway"): "motorway",
    ("waterway", "river"): "river",
    ("waterway", "canal"): "canal",
    ("leisure", "golf_course"): "golf course",
}
OPEN_LAND = {
    "landuse": {"grass", "meadow", "farmland", "greenfield", "recreation_ground", "village_green"},
    "natural": {"grassland", "scrub", "heath"},
    "leisure": {"park", "golf_course", "common"},
}


class Corridors(NamedTuple):
    lines: list
    open_land: object


class Planning(NamedTuple):
    edges: dict
    elements: dict
    survey_options: tuple = ()


def street_name(data: dict) -> str:
    return str(data.get("name") or f"unnamed {data.get('highway', 'street')}")


def segment_elements(
    graph, profile, weights, surveys=None, confirmed_only=True
) -> tuple[dict, set]:
    elements = {}
    missing = set()
    to_degrees = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    for segment_id, segment in bike_segments(graph).items():
        result = segment_fit(segment, profile, weights, confirmed_only)
        if result is not None and result["survey_options"] and surveys is not None:
            (u, v, _), data = segment["edges"][0]
            line = data.get("geometry") or LineString(
                [(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in (u, v)]
            )
            surveys.append(
                {
                    "id": f"survey:{segment_id}",
                    "segment": segment_id,
                    "street": street_name(data),
                    "fit_status": "needs_survey",
                    "geometry": mapping(transform(to_degrees.transform, line)),
                    "options": result["survey_options"],
                    "carriageway": result["carriageway"],
                    "road_reserve": result["road_reserve"],
                    "usable_verge": result["usable_verge"],
                }
            )
        if (
            result is None
            or result["status"] == "no_fit"
            or (confirmed_only and not result["confirmed"])
        ):
            missing.add(segment_id)
        elif result["status"] == "fix":
            (u, v, _), first_edge = segment["edges"][0]
            line = first_edge.get("geometry") or LineString(
                [(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in (u, v)]
            )
            point = line.interpolate(0.5, normalized=True)
            lon, lat = to_degrees.transform(point.x, point.y)
            chosen = next(item for item in result["candidates"] if item["fix"] == result["fix"])
            elements[f"segment:{segment_id}"] = {
                "confirmed": chosen["confirmed"],
                "model_margin": chosen["model_margin"],
                "source_confidence": chosen["source_confidence"],
                "carriageway": result["carriageway"],
                "road_reserve": result["road_reserve"],
                "usable_verge": result["usable_verge"],
                "aaa_after": chosen["accepted"],
                "margin_m": chosen["margin_m"],
                "kind": "segment",
                "segment": segment_id,
                "fix": result["fix"],
                "score": result["score"],
                "robust": result["robust"],
                "km": result["km"],
                "length_m": max(data["length_m"] for _, data in segment["edges"]),
                "street": street_name(segment["edges"][0][1]),
                "width_source": result["width_source"],
                "width_confidence": result["width_confidence"],
                "before": result["before"],
                "after": result["after"],
                "check_links": check_links(lat, lon),
                "counts": next(
                    item["disruption"]
                    for item in result["candidates"]
                    if item["fix"] == result["fix"]
                ),
            }
    return elements, missing


def junction_elements(graph, profile, weights) -> dict:
    to_degrees = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    segments = bike_segments(graph)
    streets = {
        segment_id: street_name(segment["edges"][0][1])
        for segment_id, segment in bike_segments(graph).items()
    }
    result = {}
    for item in junction_fixes(graph, profile):
        node = graph.nodes[item["junction"]]
        lon, lat = to_degrees.transform(node["x"], node["y"])
        sections = []
        for leg in sorted(item["legs"]):
            segment = segments[leg]
            fit = segment_fit(segment, profile, weights)
            if fit is None:
                first_edge = segment["edges"][0][1]
                fused = fuse(first_edge, profile)
                before = fit_cross_section({**first_edge, **fused}, profile)
                after = before
                width_source = fused["width_source"]
                width_confidence = fused["width_confidence"]
            else:
                before = fit["before"]
                after = fit["after"]
                width_source = fit["width_source"]
                width_confidence = fit["width_confidence"]
            sections.append(
                {
                    "id": f"segment:{leg}",
                    "street": streets[leg],
                    "before": before,
                    "after": after,
                    "width_source": width_source,
                    "width_confidence": width_confidence,
                }
            )
        result[f"junction:{item['junction']}"] = {
            "kind": "junction",
            "junction": item["junction"],
            "fix": item["fix"],
            "score": item["disruption"]["refuges"] * weights.refuge
            + item["disruption"]["signals"] * weights.signal,
            "legs": tuple(item["legs"]),
            "sections": sections,
            "street": ", ".join(sorted({streets[leg] for leg in item["legs"]})),
            "check_links": check_links(lat, lon),
        }
    return result


def crossing_needs(key: tuple, data: dict, junctions: dict) -> tuple:
    found = tuple(
        name
        for name in (f"junction:{key[0]}", f"junction:{key[1]}")
        if name in junctions and data["segment_id"] in junctions[name]["legs"]
    )
    return found


def planning_network(graph, profile, region, confirmed_only=True) -> Planning:
    weights = region.proposals.disruption_weights
    metres = region.proposals.metres_per_point
    surveys = []
    segments, missing = segment_elements(graph, profile, weights, surveys, confirmed_only)
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
    return Planning(edges, elements, tuple(surveys))


def confirmed_planning(graph, profile, planning: Planning) -> Planning:
    changed = graph.copy()
    for u, v, k, data in changed.edges(keys=True, data=True):
        item = planning.elements.get(f"segment:{data['segment_id']}")
        if item is None or item["fix"] == "verge_path":
            continue
        fixed = fixed_edge(data, item["fix"], profile)
        if item["fix"] == "quietway":
            fixed["speed_source"] = "assumed"
        else:
            fixed["bicycle"] = "designated"
            fixed["bike_lane_width_m"] = profile.widths_m.one_way_cycleway.min.value
        changed.edges[u, v, k].update(fixed)
    evidence = graph.graph.get("safety_evidence", {})
    movements = []
    for record in evidence.get("movements", []):
        if record.get("stage") == "proposed":
            node = record["incoming"][1]
            element = planning.elements.get(f"junction:{node}")
            if element is None or element["fix"] != record.get("fix"):
                continue
            record = {**record, "stage": "existing"}
        movements.append(record)
    changed.graph["safety_evidence"] = {**evidence, "movements": movements}
    scores = score_edges(changed, profile)
    edges = {key: item for key, item in planning.edges.items() if scores[key]["confirmed_aaa"]}
    used = {name for item in edges.values() for name in item["needs"]}
    return Planning(
        edges,
        {name: item for name, item in planning.elements.items() if name in used},
        planning.survey_options,
    )


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
    allowed: set | None = None,
    routes: dict | None = None,
) -> dict:
    allowed = pickable(graph, planning) if allowed is None else allowed
    routes = {} if routes is None else routes
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
        if index not in routes:
            routes[index] = planned_routes(incoming, place, reach_m)
        for home in homes:
            if home not in routes[index]:
                continue
            _, length, elements = routes[index][home]
            if elements and length <= detour_max * results[index].within[home]:
                fixes[elements] += values[(index, home)]
    return dict(fixes)


def read_corridors(snapshot: str | Path, crs) -> Corridors | None:
    path = Path(snapshot) / "corridors.json"
    if not path.is_file():
        return None
    to_metres = Transformer.from_crs(4326, crs, always_xy=True)
    lines = []
    land = []
    for item in json.loads(path.read_text())["elements"]:
        points = [to_metres.transform(p["lon"], p["lat"]) for p in item.get("geometry", ())]
        if len(points) < 2:
            continue
        tags = item["tags"]
        for pair, label in LINE_LABELS.items():
            if tags.get(pair[0]) == pair[1]:
                lines.append((label, LineString(points)))
        closed = len(points) >= 4 and points[0] == points[-1]
        if closed and any(tags.get(key) in values for key, values in OPEN_LAND.items()):
            land.append(shapely.Polygon(points).buffer(0))
    return Corridors(lines, unary_union(land))


def path_element(graph, geometry, label: str, name: str, segment: str) -> dict:
    to_degrees = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    middle = geometry.interpolate(0.5, normalized=True)
    lon, lat = to_degrees.transform(middle.x, middle.y)
    return {
        "kind": "segment",
        "segment": segment,
        "fix": "new_path",
        "aaa_after": True,
        "margin_m": None,
        "score": 0.0,
        "robust": "robust",
        "km": geometry.length / 1000,
        "length_m": geometry.length,
        "street": f"new path beside {label}",
        "width_source": None,
        "width_confidence": None,
        "before": [],
        "after": [],
        "check_links": check_links(lat, lon),
        "counts": {"parking_spaces": 0, "lane_km": 0.0, "speed_km": 0.0},
    }


def add_corridor_paths(graph, planning: Planning, corridors: Corridors, metres: float) -> tuple:
    graph = graph.copy()
    edges = dict(planning.edges)
    elements = dict(planning.elements)
    names = []
    nodes = sorted(
        {n for u, v, d in graph.edges(data=True) if d["bike_ok"] for n in (u, v)}, key=repr
    )
    points = {node: Point(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in nodes}
    for label, line in corridors.lines:
        near = sorted(
            (line.project(points[node]), repr(node), node)
            for node in nodes
            if line.distance(points[node]) <= SNAP_M
        )
        anchor = near[0] if near else None
        for item in near[1:]:
            gap = item[0] - anchor[0]
            first, last = anchor[2], item[2]
            if gap < MIN_PATH_M:
                continue
            behind, anchor = anchor, item
            if gap > MAX_PATH_M:
                continue
            side = substring(line, behind[0], item[0]).buffer(SIDE_M)
            if side.intersection(corridors.open_land).area < OPEN_SHARE * side.area:
                continue
            geometry = LineString(
                [points[first], *substring(line, behind[0], item[0]).coords, points[last]]
            )
            segment = "corridor-" + project_id([label, repr(first), repr(last)])
            name = f"segment:{segment}"
            if name in elements:
                continue
            elements[name] = path_element(graph, geometry, label, name, segment)
            names.append(name)
            for start, end, shape in ((first, last, geometry), (last, first, geometry.reverse())):
                graph.add_edge(
                    start,
                    end,
                    "new",
                    highway="cycleway",
                    bike_ok=True,
                    candidate=True,
                    segment_id=segment,
                    length_m=shape.length,
                    geometry=shape,
                )
                cost = shape.length + metres * elements[name]["score"]
                edges[(start, end, "new")] = {"cost": cost, "needs": (name,)}
    return graph, Planning(edges, elements, planning.survey_options), names


def segment_nodes(segment: dict) -> set:
    return {node for (u, v, _), _ in segment["edges"] for node in (u, v)}


def cell_projects(graph, profile, allowed: set) -> tuple[dict, dict]:
    local = {}
    barrier = set()
    for segment_id, segment in bike_segments(graph).items():
        if own_lts(segment["edges"][0][1], profile) < 3:
            local[segment_id] = segment_nodes(segment)
        else:
            barrier |= segment_nodes(segment)
    links = nx.Graph()
    for segment_id, nodes in local.items():
        links.add_node(("segment", segment_id))
        links.add_edges_from((("segment", segment_id), ("node", node)) for node in nodes - barrier)
    found = {}
    cell_of: dict = defaultdict(set)
    for number, component in enumerate(sorted(nx.connected_components(links), key=repr)):
        members = sorted(item[1] for item in component if item[0] == "segment")
        nodes = set().union(*(local[member] for member in members))
        for node in nodes:
            cell_of[node].add(number)
        elements = {f"segment:{member}" for member in members}
        elements |= {f"junction:{node}" for node in nodes}
        elements &= allowed
        if elements:
            found[frozenset(elements)] = "neighbourhood"
    return found, cell_of


def corridor_projects(graph, planning: Planning, allowed: set, cell_of: dict) -> dict:
    runs = nx.Graph()
    at_node: dict = defaultdict(list)
    nodes_of = {}
    for segment_id, segment in bike_segments(graph).items():
        name = f"segment:{segment_id}"
        element = planning.elements.get(name)
        if name in allowed and element and element["fix"] in CORRIDOR_FIXES:
            nodes_of[name] = segment_nodes(segment)
            runs.add_node(name)
            for node in nodes_of[name]:
                at_node[node].append(name)
    for names in at_node.values():
        for first, second in pairwise(names):
            if planning.elements[first]["street"] == planning.elements[second]["street"]:
                runs.add_edge(first, second)
    found = {}
    for run in nx.connected_components(runs):
        cells = set().union(*(cell_of[node] for name in run for node in nodes_of[name]))
        if len(cells) >= 2:
            found[frozenset(run)] = "corridor"
    return found


def big_projects(graph, planning: Planning, profile, allowed: set | None = None) -> dict:
    allowed = pickable(graph, planning) if allowed is None else allowed
    found, cell_of = cell_projects(graph, profile, allowed)
    return {**found, **corridor_projects(graph, planning, allowed, cell_of)}


def project_id(names) -> str:
    return hashlib.sha256("".join(sorted(names)).encode()).hexdigest()[:16]


def edge_share(name: str, element: dict, length: float, metres: float) -> float:
    if element["kind"] == "junction":
        return metres * element["score"] / 2
    return metres * element["score"] * length / element["length_m"]


def fixed_planning(graph, planning: Planning, fixed: set, metres: float) -> Planning:
    edges = {}
    for key, item in planning.edges.items():
        done = [name for name in item["needs"] if name in fixed]
        if not done:
            edges[key] = item
            continue
        length = graph[key[0]][key[1]][key[2]]["length_m"]
        saved = sum(edge_share(name, planning.elements[name], length, metres) for name in done)
        needs = tuple(name for name in item["needs"] if name not in fixed)
        edges[key] = {"cost": item["cost"] - saved, "needs": needs}
    return Planning(edges, planning.elements, planning.survey_options)


def exact_score(people: dict, placed: list, results: list[Reach], weights: dict) -> float:
    homes = score_access(people, placed, results, weights)["homes"]
    total = sum(people.values())
    return 100 * sum(item["people"] * item["score"] for item in homes.values()) / total


def update_reach(
    graph,
    sources: list,
    results: list[Reach],
    reach_m: float,
    detour_max: float,
    old: set,
    new: set,
    table: EdgeTable | None = None,
    legs=None,
) -> tuple[list[Reach], list[int]]:
    heads = {key[1] for key in old ^ new}
    redone = [
        index for index, found in enumerate(results) if any(node in found.within for node in heads)
    ]
    if not redone:
        return results, redone
    fresh = safe_reach(
        table or edge_table(graph),
        [results[index].within for index in redone],
        [sources[index] for index in redone],
        reach_m,
        detour_max,
        new,
        legs,
    )
    updated = list(results)
    for index, found in zip(redone, fresh, strict=True):
        updated[index] = found
    return updated, redone


def newly_safe(people: dict, before: list[Reach], after: list[Reach]) -> list[float]:
    return [
        sum(people.get(node, 0) for node in now.safe - was.safe)
        for was, now in zip(before, after, strict=True)
    ]


def reach_counts(placed: list, results: list[Reach]) -> dict:
    counts: dict = defaultdict(lambda: defaultdict(int))
    for (kind, _), found in zip(placed, results, strict=True):
        for node in found.within:
            counts[node][kind] += 1
    return counts


def gain_between(
    people: dict,
    placed: list,
    weights: dict,
    counts: dict,
    before: list[Reach],
    after: list[Reach],
    redone: list[int],
) -> float:
    gain = 0.0
    for index in redone:
        kind = placed[index][0]
        for node in sorted(before[index].safe ^ after[index].safe):
            if node not in people:
                continue
            weight = sum(weights[name] for name in counts[node])
            if not weight:
                continue
            sign = 1 if node in after[index].safe else -1
            gain += sign * people[node] * weights[kind] / (counts[node][kind] * weight)
    return 100 * gain / sum(people.values())


def greedy_picks(
    graph,
    planning: Planning,
    placed: list,
    people: dict,
    weights: dict,
    proposals,
    reach_m: float,
    detour_max: float,
    names: list | None = None,
    candidates: dict | None = None,
    stats: dict | None = None,
    legs=None,
) -> list[dict]:
    candidates = {} if candidates is None else candidates
    sources = [node for _, node in placed]
    labels = names if names is not None else [str(node) for node in sources]
    fixed: set = set()
    aaa = {key for key, item in planning.edges.items() if not item["needs"]}
    table = edge_table(graph)
    allowed = pickable(graph, planning)
    routes: dict = {}

    def aaa_after(extra: set) -> set:
        done = fixed | extra
        return aaa | {key for key, item in planning.edges.items() if set(item["needs"]) <= done}

    now = aaa_after(set())
    results = reach(graph, sources, reach_m, detour_max, now, table, legs)
    baseline_results = results
    counts = reach_counts(placed, results)
    score = exact_score(people, placed, results, weights)
    current = fixed_planning(graph, planning, fixed, proposals.metres_per_point)
    picked: list[dict] = []
    safe_now = score_access(people, placed, results, weights)["safe_people"]
    km = 0.0
    termination = "no_gain"
    while len(picked) < proposals.max_projects and km < proposals.budget_km:
        values = trip_values(people, placed, results, weights)
        found = route_fixes(
            graph, current, placed, results, values, reach_m, detour_max, allowed, routes
        )
        kinds = dict.fromkeys(found, "route")
        ordered = sorted(found.items(), key=lambda pair: project_id(pair[0]))
        by_first: dict = defaultdict(list)
        for position, (fix, worth) in enumerate(ordered):
            by_first[min(fix)].append((position, fix, worth))
        for elements in sorted(candidates, key=project_id):
            remaining = elements - fixed
            if remaining in found:
                kinds[remaining] = candidates[elements]
                continue
            inside = sorted(
                (position, worth)
                for name in remaining
                for position, fix, worth in by_first.get(name, ())
                if fix <= remaining
            )
            value = sum(worth for _, worth in inside)
            if remaining and value > 0:
                found[remaining] = value
                kinds[remaining] = candidates[elements]
        if stats is not None and not picked:
            stats["candidates"] = len(found)
        costs = {
            elements: sum(planning.elements[name]["score"] for name in sorted(elements - fixed))
            for elements in found
        }
        ranked = sorted(
            found,
            key=lambda elements: (-found[elements] / (costs[elements] + 1), project_id(elements)),
        )[: proposals.candidate_pool]
        if not ranked:
            termination = "candidate_pool_exhausted"
            break
        best = None
        for elements in ranked:
            trial, redone = update_reach(
                graph,
                sources,
                results,
                reach_m,
                detour_max,
                now,
                aaa_after(set(elements)),
                table,
                legs,
            )
            gain = gain_between(people, placed, weights, counts, results, trial, redone)
            if gain <= 0 or gain < proposals.min_gain:
                continue
            key = (-gain / (costs[elements] + 1), project_id(elements))
            if best is None or key < best[0]:
                best = (key, elements, gain)
        if best is None or best[2] < proposals.min_gain:
            break
        _, elements, gain = best
        fixed |= elements
        score += gain
        km += sum(planning.elements[name].get("km", 0.0) for name in sorted(elements))
        before = results
        results, redone = update_reach(
            graph, sources, results, reach_m, detour_max, now, aaa_after(set()), table, legs
        )
        now = aaa_after(set())
        changed = {key[1] for key, item in planning.edges.items() if elements & set(item["needs"])}
        for index in list(routes):
            if any(node in results[index].within for node in changed):
                del routes[index]
        gained = newly_safe(people, before, results)
        main = max(range(len(gained)), key=lambda index: (gained[index], -index))
        safe_before = safe_now
        safe_after = safe_now = score_access(people, placed, results, weights)["safe_people"]
        picked.append(
            {
                "id": project_id(elements),
                "kind": kinds[elements],
                "elements": tuple(sorted(elements)),
                "gain": gain,
                "cost": costs[elements],
                "score_after": score,
                "place": labels[main],
                "access_gains": people_gains(people, placed, before, results, list(weights)),
                "package_access_gains": people_gains(
                    people, placed, baseline_results, results, list(weights)
                ),
                "people": {kind: safe_after[kind] - safe_before[kind] for kind in weights},
            }
        )
        current = fixed_planning(graph, planning, fixed, proposals.metres_per_point)
    else:
        termination = "project_cap" if len(picked) >= proposals.max_projects else "budget_km"
    if stats is not None:
        stats["termination_reason"] = termination
    return picked


def element_record(name: str, element: dict) -> dict:
    junction = element["kind"] == "junction"
    counts = {} if junction else element["counts"]
    result = {
        "id": name,
        "street": element["street"],
        "length_m": 0.0 if junction else round(element["length_m"], 1),
        "fix": element["fix"],
        "aaa_after": True if junction else element["aaa_after"],
        "margin_m": None if junction else element["margin_m"],
        "robust": "robust" if junction else element["robust"],
        "width_source": None if junction else element["width_source"],
        "km": 0.0 if junction else round(element["km"], 6),
        "parking_spaces": counts.get("parking_spaces", 0),
        "lane_km": counts.get("lane_km", 0.0),
        "speed_km": counts.get("speed_km", 0.0),
        "signals": int(junction and element["fix"] == "signals"),
        "refuges": int(junction and element["fix"] == "refuge"),
    }
    return result


def project_totals(elements: list[dict]) -> dict:
    by_fix: dict = defaultdict(float)
    for item in elements:
        if item["km"]:
            by_fix[item["fix"]] += item["km"]
    return {
        "km_by_fix": {fix: round(by_fix[fix], 6) for fix in PROJECT_FIXES if fix in by_fix},
        "parking_spaces": sum(item["parking_spaces"] for item in elements),
        "lane_km": round(sum(item["lane_km"] for item in elements), 6),
        "speed_km": round(sum(item["speed_km"] for item in elements), 6),
        "signals": sum(item["signals"] for item in elements),
        "refuges": sum(item["refuges"] for item in elements),
    }


def project_records(picked: list[dict], planning: Planning) -> list[dict]:
    records = []
    for rank, pick in enumerate(picked, start=1):
        elements = [element_record(name, planning.elements[name]) for name in pick["elements"]]
        streets = sorted({item["street"] for item in elements})
        records.append(
            {
                "rank": rank,
                "id": pick["id"],
                "kind": pick["kind"],
                "name": f"{pick['place']}: {', '.join(streets)}",
                "elements": elements,
                "totals": {
                    **project_totals(elements),
                    **{
                        key: pick[key]
                        for key in ("access_gains", "package_access_gains")
                        if key in pick
                    },
                },
                "gain": pick["gain"],
                "score_after": pick["score_after"],
                "people": pick["people"],
            }
        )
    return records


def project_sheet_records(records: list[dict], planning: Planning) -> list[dict]:
    sheets = []
    for record in records:
        elements = []
        for item in record["elements"]:
            planned = planning.elements[item["id"]]
            enriched = {
                **item,
                "check_links": planned["check_links"],
                **{
                    key: planned.get(key)
                    for key in (
                        "confirmed",
                        "model_margin",
                        "source_confidence",
                        "carriageway",
                        "road_reserve",
                        "usable_verge",
                    )
                },
            }
            if planned["kind"] == "junction":
                sections = planned["sections"]
                enriched["sections"] = sections
                if sections:
                    enriched["width_source"] = sections[0]["width_source"]
                    enriched["width_confidence"] = sections[0]["width_confidence"]
                else:
                    enriched["width_confidence"] = None
            else:
                enriched.update(
                    {
                        "before": planned["before"],
                        "after": planned["after"],
                        "width_confidence": planned["width_confidence"],
                    }
                )
            elements.append(enriched)
        sheets.append({**record, "elements": elements})
    return sheets


def csv_fields(kinds: list) -> list[str]:
    return [
        "rank",
        "id",
        "name",
        "elements",
        "gain",
        "score_after",
        "parking_spaces",
        "lane_km",
        "speed_km",
        "signals",
        "refuges",
        *(f"km_{fix}" for fix in PROJECT_FIXES),
        *(f"people_{kind}" for kind in kinds),
        "unique_people",
        "gains_by_type",
        *(f"unique_people_{kind}" for kind in kinds),
    ]


def csv_row(record: dict, kinds: list) -> dict:
    totals = record["totals"]
    row = {
        "rank": record["rank"],
        "id": record["id"],
        "name": record["name"],
        "elements": len(record["elements"]),
        "gain": record["gain"],
        "score_after": record["score_after"],
        "parking_spaces": totals["parking_spaces"],
        "lane_km": totals["lane_km"],
        "speed_km": totals["speed_km"],
        "signals": totals["signals"],
        "refuges": totals["refuges"],
    }
    for fix in PROJECT_FIXES:
        row[f"km_{fix}"] = totals["km_by_fix"].get(fix, 0.0)
    for kind in kinds:
        row[f"people_{kind}"] = record["people"][kind]
    measures = totals.get("access_gains", {})
    row["unique_people"] = measures.get("unique_people")
    row["gains_by_type"] = measures.get("gains_by_type")
    for kind in kinds:
        row[f"unique_people_{kind}"] = measures.get("unique_people_by_type", {}).get(kind)
    return row


def element_geometry(graph, segments: dict, element: dict, to_degrees):
    if element["kind"] == "junction":
        node = graph.nodes[element["junction"]]
        shape = Point(node["x"], node["y"])
    else:
        lines = {}
        for (u, v, _), data in segments[element["segment"]]["edges"]:
            line = data.get("geometry") or LineString(
                [
                    (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                    (graph.nodes[v]["x"], graph.nodes[v]["y"]),
                ]
            )
            lines.setdefault(frozenset((u, v)), line)
        shape = MultiLineString([lines[key] for key in sorted(lines, key=sorted)])
    return mapping(shapely.set_precision(transform(to_degrees.transform, shape), 1e-6))


def project_features(graph, planning: Planning, records: list[dict]) -> list[dict]:
    to_degrees = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    segments = bike_segments(graph)
    features = []
    for record in records:
        for item in record["elements"]:
            properties = {
                "project": record["id"],
                "rank": record["rank"],
                **{key: item[key] for key in ("id", "street", "fix", "robust", "width_source")},
            }
            element = planning.elements[item["id"]]
            properties |= {
                key: element.get(key)
                for key in (
                    "confirmed",
                    "model_margin",
                    "source_confidence",
                    "carriageway",
                    "road_reserve",
                    "usable_verge",
                )
            }
            geometry = element_geometry(graph, segments, element, to_degrees)
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    return features


def solve(
    graph,
    region,
    profile,
    placed: list,
    people: dict,
    weights: dict,
    names: list | None = None,
    legs=None,
    corridors: Corridors | None = None,
    stats: dict | None = None,
    confirmed: bool = False,
):
    planning = planning_network(graph, profile, region)
    made: list = []
    if corridors is not None:
        corridor_graph, corridor_planning, made = add_corridor_paths(
            graph, planning, corridors, region.proposals.metres_per_point
        )
        if not confirmed:
            graph, planning = corridor_graph, corridor_planning
    if confirmed:
        planning = confirmed_planning(graph, profile, planning)
    big = big_projects(graph, planning, profile)
    if stats is not None:
        stats["corridor_candidates"] = len(made)
    picked = greedy_picks(
        graph,
        planning,
        placed,
        people,
        weights,
        region.proposals,
        region.access.reach_m,
        region.access.detour_max,
        names,
        big,
        stats,
        legs,
    )
    return graph, planning, picked


def scenarios_for(proposals) -> list[Scenario]:
    return list(proposals.scenarios or DEFAULT_SCENARIOS)


def scaled_region(region, scenario: Scenario, frontier: bool = True):
    weights = region.proposals.disruption_weights
    scaled = dataclasses.replace(
        weights, **{name: getattr(weights, name) * scale for name, scale in scenario.scales.items()}
    )
    changes = {"disruption_weights": scaled}
    if frontier:
        changes.update(
            max_projects=region.proposals.frontier_max_projects,
            budget_km=float("inf"),
            min_gain=0.0,
        )
    return dataclasses.replace(region, proposals=dataclasses.replace(region.proposals, **changes))


def recommended_stop(picks: list[dict], ratio: float) -> int | None:
    stop = None
    best = 0.0
    for item in picks:
        per_point = item["gain"] / (item["cost"] + 1)
        best = max(best, per_point)
        if per_point >= ratio * best:
            stop = item["rank"]
    return stop


def curve_picks(picked: list[dict], planning: Planning) -> list[dict]:
    records = project_records(picked, planning)
    parking = lane = speed = signals = refuges = 0
    disruption = 0.0
    by_fix: dict = defaultdict(float)
    people: dict = defaultdict(int)
    found = []
    for record, pick in zip(records, picked, strict=True):
        totals = record["totals"]
        parking += totals["parking_spaces"]
        lane += totals["lane_km"]
        speed += totals["speed_km"]
        signals += totals["signals"]
        refuges += totals["refuges"]
        disruption += pick["cost"]
        for fix, km in totals["km_by_fix"].items():
            by_fix[fix] += km
        for kind, count in record["people"].items():
            people[kind] += count
        found.append(
            {
                "rank": record["rank"],
                "id": record["id"],
                "kind": record["kind"],
                "name": record["name"],
                "gain": record["gain"],
                "cost": pick["cost"],
                "disruption": round(disruption, 6),
                "parking_spaces": parking,
                "lane_km": round(lane, 6),
                "speed_km": round(speed, 6),
                "signals": signals,
                "refuges": refuges,
                "km_by_fix": {fix: round(by_fix[fix], 6) for fix in PROJECT_FIXES if fix in by_fix},
                "score": record["score_after"],
                "people": dict(people),
                **totals.get("package_access_gains", {}),
            }
        )
    return found


def scenario_curve(
    graph,
    region,
    profile,
    scenario: Scenario,
    placed: list,
    people: dict,
    weights: dict,
    reach_m: float,
    detour_max: float,
    names: list | None = None,
    legs=None,
    corridors: Corridors | None = None,
    trip_inputs=None,
    population=None,
    confirmed: bool = False,
) -> dict:
    scaled = scaled_region(region, scenario)
    scaled = dataclasses.replace(
        scaled, access=dataclasses.replace(scaled.access, reach_m=reach_m, detour_max=detour_max)
    )
    stats = {}
    solved, planning, picked = solve(
        graph, scaled, profile, placed, people, weights, names, legs, corridors, stats, confirmed
    )
    picks = curve_picks(picked, planning)
    stop = recommended_stop(picks, region.proposals.recommend_ratio)
    shapes = project_features(solved, planning, project_records(picked, planning))
    packages = []
    if trip_inputs is not None:
        destinations, links, movements = trip_inputs
        links = {
            key: {
                **links.get(key, {"status": "unknown"}),
                "model_needs": planning.edges.get(key, {"needs": ["missing"]})["needs"],
            }
            for key in solved.edges(keys=True)
        }
        fixed = set()
        projects = []
        for rank in range(len(picked) + 1):
            if rank:
                fixed.update(picked[rank - 1]["elements"])
                projects.append(picked[rank - 1]["id"])
            packages.append(
                {
                    "package": {"scenario": scenario.id, "rank": rank},
                    "project_ids": list(projects),
                    "element_ids": sorted(fixed),
                    **complete_trips(
                        solved,
                        people,
                        destinations,
                        links,
                        movements,
                        fixed,
                        reach_m,
                        detour_max,
                        region.access.last_leg_m,
                    ),
                }
            )
    if population is not None and packages:
        for package in packages:
            package["resident_outcomes"] = resident_outcomes(
                packages[0], package, population, destinations
            )
    catalog = works_catalog(
        solved,
        planning.elements,
        [
            key
            for package in packages
            for witness in package["strict"]
            for direction in ("outbound", "return")
            for key in witness[direction]["edges"]
        ],
    )
    for package in packages:
        retained = [
            key
            for witness in package["strict"]
            for direction in ("outbound", "return")
            for key in witness[direction]["edges"]
        ]
        package["works"] = works_package(catalog, package["element_ids"], retained, package["gaps"])
    return {
        "works_catalog": catalog,
        "shapes": shapes,
        "id": scenario.id,
        "label": scenario.label,
        "safety_scenario": "confirmed" if confirmed else "model assumptions",
        "scales": scenario.scales,
        "recommended_stop": stop,
        "recommend_ratio": region.proposals.recommend_ratio,
        "termination_reason": stats["termination_reason"],
        "evaluated_projects": len(picks),
        "truncated": stats["termination_reason"] == "project_cap",
        "cap_reached": stats["termination_reason"] == "project_cap",
        "picks": picks,
        "trip_packages": packages,
    }


def survey_layer(planning: Planning) -> dict:
    groups = {}
    for item in planning.survey_options:
        options = item["options"]
        properties = {
            "street": item["street"],
            "fit_status": "needs_survey",
            "fixes": sorted({option["fix"] for option in options}),
            "survey_checks": sorted(
                {check for option in options for check in option["survey_checks"]}
            ),
            "source_confidence": sorted({option["source_confidence"] for option in options}),
            "model_margin": sorted({option["model_margin"] or "unknown" for option in options}),
        }
        key = json.dumps(properties, sort_keys=True)
        group = groups.setdefault(key, {"properties": properties, "segments": [], "lines": []})
        group["segments"].append(str(item["segment"]))
        geometry = item["geometry"]
        lines = (
            [geometry["coordinates"]]
            if geometry["type"] == "LineString"
            else geometry["coordinates"]
        )
        group["lines"].extend(lines)
    features = []
    for key, group in sorted(groups.items()):
        geometry = shapely.line_merge(MultiLineString(group["lines"]))
        features.append(
            {
                "type": "Feature",
                "id": "survey:" + project_id([key]),
                "properties": group["properties"] | {"segments": sorted(group["segments"])},
                "geometry": mapping(geometry),
            }
        )
    return {"type": "FeatureCollection", "features": features}


def write_propose(
    graph,
    region,
    profile,
    snapshot: str | Path,
    out: str | Path,
    sheets: list | None = None,
    stats: dict | None = None,
) -> list[dict]:
    out = Path(out)
    kept, nodes, _, placed, resident, weights = scene(graph, region, snapshot)
    scores = score_edges(graph, profile)
    legs = last_legs(graph, scores, sorted(resident.people), region.access.last_leg_m)
    corridors = read_corridors(snapshot, graph.graph["crs"])
    names = [
        place["name"] or place["type"]
        for place, node in zip(kept, nodes, strict=True)
        if node is not None
    ]
    shipped_graph = graph
    graph, planning, picked = solve(
        graph,
        region,
        profile,
        placed,
        resident.people,
        weights,
        names,
        legs,
        corridors,
        stats,
        True,
    )
    records = project_records(picked, planning)
    trip_inputs = snapshot_trip_inputs(snapshot, kept, nodes, graph, scores, planning)
    destinations, links, movements = trip_inputs
    shortlist_trips = complete_trips(
        graph,
        resident.people,
        destinations,
        links,
        movements,
        {name for pick in picked for name in pick["elements"]},
        region.access.reach_m,
        region.access.detour_max,
        region.access.last_leg_m,
    )
    baseline_trips = complete_trips(
        graph,
        resident.people,
        destinations,
        links,
        movements,
        set(),
        region.access.reach_m,
        region.access.detour_max,
        region.access.last_leg_m,
    )
    shortlist_trips["resident_outcomes"] = resident_outcomes(
        baseline_trips, shortlist_trips, resident.population, destinations
    )
    catalog = works_catalog(
        graph,
        planning.elements,
        [
            key
            for witness in shortlist_trips["strict"]
            for direction in ("outbound", "return")
            for key in witness[direction]["edges"]
        ],
    )
    shortlist_trips["works_catalog"] = catalog
    shortlist_trips["works"] = works_package(
        catalog,
        {name for pick in picked for name in pick["elements"]},
        [
            key
            for witness in shortlist_trips["strict"]
            for direction in ("outbound", "return")
            for key in witness[direction]["edges"]
        ],
        shortlist_trips["gaps"],
    )
    surveys = survey_layer(planning)
    if stats is not None:
        stats["survey_options"] = surveys
    if sheets is not None:
        sheets.extend(project_sheet_records(records, planning))
    out.mkdir(parents=True, exist_ok=True)
    (out / "survey_options.geojson").write_text(json.dumps(surveys, indent=2) + "\n")
    (out / "projects.json").write_text(json.dumps(records, indent=2) + "\n")
    kinds = list(weights)
    with (out / "projects.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields(kinds), lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_row(record, kinds) for record in records)
    collection = {
        "type": "FeatureCollection",
        "features": project_features(graph, planning, records),
        "trip_proof": {
            "package": "minimum-gain-shortlist",
            "population_sources": resident.population,
            **shortlist_trips,
        },
    }
    (out / "projects.geojson").write_text(json.dumps(collection))
    curves = [
        scenario_curve(
            shipped_graph,
            region,
            profile,
            scenario,
            placed,
            resident.people,
            weights,
            region.access.reach_m,
            region.access.detour_max,
            names,
            legs,
            corridors,
            trip_inputs,
            resident.population,
            confirmed=True,
        )
        for scenario in scenarios_for(region.proposals)
    ]
    shapes: dict = {}
    for curve in curves:
        for item in curve.pop("shapes"):
            properties = {key: value for key, value in item["properties"].items() if key != "rank"}
            shapes.setdefault(
                (properties["project"], properties["id"]), {**item, "properties": properties}
            )
    frontier = {
        "scenarios": curves,
        "trip_sources": {
            "destinations": destinations,
            "population": resident.population,
            "evidence": json.loads((Path(snapshot) / "places.json").read_text()).get(
                "trip_evidence", {}
            ),
            "missing_link_status": "unknown",
            "missing_movement_status": "unknown",
        },
        "shapes": {
            "type": "FeatureCollection",
            "features": [shapes[key] for key in sorted(shapes)],
        },
    }
    (out / "frontier.json").write_text(json.dumps(frontier, indent=2) + "\n")
    return records
