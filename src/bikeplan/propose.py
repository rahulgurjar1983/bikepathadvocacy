import csv
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
from shapely.ops import transform

from bikeplan.access import (
    EdgeTable,
    Reach,
    edge_table,
    last_legs,
    reach,
    safe_reach,
    scene,
    score_access,
)
from bikeplan.fit import FIXES, junction_fixes, segment_fit
from bikeplan.fit import cross_section as fit_cross_section
from bikeplan.network import bike_segments
from bikeplan.stress import edge_aaa, own_lts, raise_for_crossings, score_edges
from bikeplan.width import check_links, fuse

CORRIDOR_FIXES = tuple(fix for fix in FIXES if fix != "quietway")
KINDS = ("corridor", "neighbourhood", "route")


class Planning(NamedTuple):
    edges: dict
    elements: dict


def street_name(data: dict) -> str:
    return str(data.get("name") or f"unnamed {data.get('highway', 'street')}")


def segment_elements(graph, profile, weights) -> tuple[dict, set]:
    elements = {}
    missing = set()
    to_degrees = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    for segment_id, segment in bike_segments(graph).items():
        result = segment_fit(segment, profile, weights)
        if result is None or result["status"] == "no_fit":
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
    return Planning(edges, planning.elements)


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
    counts = reach_counts(placed, results)
    score = exact_score(people, placed, results, weights)
    current = fixed_planning(graph, planning, fixed, proposals.metres_per_point)
    picked: list[dict] = []
    km = 0.0
    while len(picked) < proposals.max_projects and km < proposals.budget_km:
        values = trip_values(people, placed, results, weights)
        found = route_fixes(
            graph, current, placed, results, values, reach_m, detour_max, allowed, routes
        )
        kinds = dict.fromkeys(found, "route")
        ordered = sorted(found.items(), key=lambda pair: project_id(pair[0]))
        for elements in sorted(candidates, key=project_id):
            remaining = elements - fixed
            if remaining in found:
                kinds[remaining] = candidates[elements]
                continue
            value = sum(worth for fix, worth in ordered if fix <= remaining)
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
            if gain < proposals.min_gain:
                continue
            key = (round(-gain / (costs[elements] + 1), 9), project_id(elements))
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
        safe_before = score_access(people, placed, before, weights)["safe_people"]
        safe_after = score_access(people, placed, results, weights)["safe_people"]
        picked.append(
            {
                "id": project_id(elements),
                "kind": kinds[elements],
                "elements": tuple(sorted(elements)),
                "gain": round(gain, 6),
                "cost": costs[elements],
                "score_after": round(score, 6),
                "place": labels[main],
                "people": {kind: safe_after[kind] - safe_before[kind] for kind in weights},
            }
        )
        current = fixed_planning(graph, planning, fixed, proposals.metres_per_point)
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
        "km_by_fix": {fix: round(by_fix[fix], 6) for fix in FIXES if fix in by_fix},
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
                "totals": project_totals(elements),
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
            enriched = {**item, "check_links": planned["check_links"]}
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
        *(f"km_{fix}" for fix in FIXES),
        *(f"people_{kind}" for kind in kinds),
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
    for fix in FIXES:
        row[f"km_{fix}"] = totals["km_by_fix"].get(fix, 0.0)
    for kind in kinds:
        row[f"people_{kind}"] = record["people"][kind]
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
            geometry = element_geometry(graph, segments, element, to_degrees)
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    return features


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
    planning = planning_network(graph, profile, region)
    names = [
        place["name"] or place["type"]
        for place, node in zip(kept, nodes, strict=True)
        if node is not None
    ]
    picked = greedy_picks(
        graph,
        planning,
        placed,
        resident.people,
        weights,
        region.proposals,
        region.access.reach_m,
        region.access.detour_max,
        names,
        big_projects(graph, planning, profile),
        stats,
        last_legs(
            graph,
            score_edges(graph, profile),
            sorted(resident.people),
            region.access.last_leg_m,
        ),
    )
    records = project_records(picked, planning)
    if sheets is not None:
        sheets.extend(project_sheet_records(records, planning))
    out.mkdir(parents=True, exist_ok=True)
    (out / "projects.json").write_text(json.dumps(records, indent=2) + "\n")
    kinds = list(weights)
    with (out / "projects.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields(kinds), lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_row(record, kinds) for record in records)
    collection = {
        "type": "FeatureCollection",
        "features": project_features(graph, planning, records),
    }
    (out / "projects.geojson").write_text(json.dumps(collection))
    return records
