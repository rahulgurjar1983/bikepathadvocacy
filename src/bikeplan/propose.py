import csv
import hashlib
import heapq
import json
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import shapely
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point, mapping
from shapely.ops import transform

from bikeplan.access import Reach, reach, scene, score_access
from bikeplan.fit import FIXES, junction_fixes, segment_fit
from bikeplan.network import bike_segments
from bikeplan.stress import edge_aaa, own_lts, raise_for_crossings


class Planning(NamedTuple):
    edges: dict
    elements: dict


def street_name(data: dict) -> str:
    return str(data.get("name") or f"unnamed {data.get('highway', 'street')}")


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
                "street": street_name(segment["edges"][0][1]),
                "width_source": result["width_source"],
                "counts": next(
                    item["disruption"]
                    for item in result["candidates"]
                    if item["fix"] == result["fix"]
                ),
            }
    return elements, missing


def junction_elements(graph, profile, weights) -> dict:
    streets = {
        segment_id: street_name(segment["edges"][0][1])
        for segment_id, segment in bike_segments(graph).items()
    }
    return {
        f"junction:{item['junction']}": {
            "kind": "junction",
            "junction": item["junction"],
            "fix": item["fix"],
            "score": item["disruption"]["refuges"] * weights.refuge
            + item["disruption"]["signals"] * weights.signal,
            "legs": tuple(item["legs"]),
            "street": ", ".join(sorted({streets[leg] for leg in item["legs"]})),
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
) -> tuple[list[Reach], list[int]]:
    heads = {key[1] for key in old ^ new}
    redone = [
        index for index, found in enumerate(results) if any(node in found.within for node in heads)
    ]
    if not redone:
        return results, redone
    fresh = reach(graph, [sources[index] for index in redone], reach_m, detour_max, new)
    updated = list(results)
    for index, found in zip(redone, fresh, strict=True):
        updated[index] = found
    return updated, redone


def newly_safe(people: dict, before: list[Reach], after: list[Reach]) -> list[float]:
    return [
        sum(people.get(node, 0) for node in now.safe - was.safe)
        for was, now in zip(before, after, strict=True)
    ]


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
) -> list[dict]:
    sources = [node for _, node in placed]
    labels = names if names is not None else [str(node) for node in sources]
    fixed: set = set()
    aaa = {key for key, item in planning.edges.items() if not item["needs"]}

    def aaa_after(extra: set) -> set:
        done = fixed | extra
        return aaa | {key for key, item in planning.edges.items() if set(item["needs"]) <= done}

    now = aaa_after(set())
    results = reach(graph, sources, reach_m, detour_max, now)
    score = exact_score(people, placed, results, weights)
    current = fixed_planning(graph, planning, fixed, proposals.metres_per_point)
    picked: list[dict] = []
    km = 0.0
    while len(picked) < proposals.max_projects and km < proposals.budget_km:
        values = trip_values(people, placed, results, weights)
        found = route_fixes(graph, current, placed, results, values, reach_m, detour_max)
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
            trial, _ = update_reach(
                graph, sources, results, reach_m, detour_max, now, aaa_after(set(elements))
            )
            gain = exact_score(people, placed, trial, weights) - score
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
        results, _ = update_reach(
            graph, sources, results, reach_m, detour_max, now, aaa_after(set())
        )
        now = aaa_after(set())
        gained = newly_safe(people, before, results)
        main = max(range(len(gained)), key=lambda index: (gained[index], -index))
        safe_before = score_access(people, placed, before, weights)["safe_people"]
        safe_after = score_access(people, placed, results, weights)["safe_people"]
        picked.append(
            {
                "id": project_id(elements),
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
    return {
        "id": name,
        "street": element["street"],
        "length_m": 0.0 if junction else round(element["length_m"], 1),
        "fix": element["fix"],
        "robust": "robust" if junction else element["robust"],
        "width_source": None if junction else element["width_source"],
        "km": 0.0 if junction else round(element["km"], 6),
        "parking_spaces": counts.get("parking_spaces", 0),
        "lane_km": counts.get("lane_km", 0.0),
        "speed_km": counts.get("speed_km", 0.0),
        "signals": int(junction and element["fix"] == "signals"),
        "refuges": int(junction and element["fix"] == "refuge"),
    }


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
                "name": f"{pick['place']}: {', '.join(streets)}",
                "elements": elements,
                "totals": project_totals(elements),
                "gain": pick["gain"],
                "score_after": pick["score_after"],
                "people": pick["people"],
            }
        )
    return records


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


def element_geometry(graph, name: str, element: dict, to_degrees):
    if element["kind"] == "junction":
        node = graph.nodes[element["junction"]]
        shape = Point(node["x"], node["y"])
    else:
        lines = {}
        for (u, v, _), data in bike_segments(graph)[element["segment"]]["edges"]:
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
    features = []
    for record in records:
        for item in record["elements"]:
            properties = {
                "project": record["id"],
                "rank": record["rank"],
                **{key: item[key] for key in ("id", "street", "fix", "robust", "width_source")},
            }
            geometry = element_geometry(
                graph, item["id"], planning.elements[item["id"]], to_degrees
            )
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    return features


def write_propose(graph, region, profile, snapshot: str | Path, out: str | Path) -> list[dict]:
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
    )
    records = project_records(picked, planning)
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
