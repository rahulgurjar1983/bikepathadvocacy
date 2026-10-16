from fractions import Fraction

import networkx as nx

from bikeplan.access import sort_key
from bikeplan.fit import disruption_counts, disruption_score
from bikeplan.network import first
from bikeplan.options import link_id
from bikeplan.rating import option_totals, option_trips

COUNTS = ("parking_spaces", "lane_km", "speed_km", "path_km")
FIX_WORDS = {
    "quietway": "a quiet street",
    "cycleway_in_spare": "a cycleway",
    "cycleway_parking_one_side": "a cycleway",
    "cycleway_parking_both_sides": "a cycleway",
    "road_diet": "a road diet",
    "verge_path": "a verge path",
}


def street_name(data: dict) -> str:
    name = first(data.get("name"))
    if name:
        return str(name)
    return f"unnamed {first(data.get('highway')) or 'road'} road"


def link_streets(graph) -> dict:
    names: dict = {}
    for u, v, k, data in graph.edges(keys=True, data=True):
        if data["bike_ok"] and u != v:
            names.setdefault(link_id(u, v, k), set()).add(street_name(data))
    return {key: min(found) for key, found in sorted(names.items())}


def link_roads(graph, functions: tuple, owner: str) -> dict:
    found: dict = {}
    for u, v, k, data in graph.edges(keys=True, data=True):
        if not data["bike_ok"] or u == v:
            continue
        road = found.setdefault(link_id(u, v, k), {"type": None, "owner": None})
        road["type"] = road["type"] or str(first(data.get("highway")) or "road")
        if data.get("road_function") in functions:
            road["owner"] = owner
    return dict(sorted(found.items()))


def plain_reason(item: dict) -> str | None:
    what = FIX_WORDS[item["fix"]]
    reason = item["reason"]
    if item["rejected"]:
        return f"would not make the street all ages as {what}"
    if item["fits"]:
        return None
    if reason.startswith("ADT"):
        return f"too busy for {what}"
    if reason.startswith("needs at most"):
        return f"too many lanes for {what}"
    if reason.startswith("needs 2 lanes"):
        return f"too few lanes for {what}"
    if "not a quiet street class" in reason:
        return f"the wrong kind of road for {what}"
    if reason.startswith("needs"):
        return f"too narrow for {what}"
    if "unknown" in reason:
        return f"width unknown for {what}"
    return None


def plain_reasons(fit: dict) -> list[str]:
    found: list[str] = []
    for item in fit["candidates"]:
        text = plain_reason(item)
        if text and text not in found:
            found.append(text)
    return found


def fit_reasons(fit: dict | None) -> list[str]:
    if fit is None:
        return ["no traffic data to design a fix"]
    if fit["status"] == "aaa":
        return ["no design in the tool changes its stress rating"]
    if fit["status"] == "no_fit":
        return plain_reasons(fit) or ["no design fits"]
    return []


def link_reasons(graph, table: dict, fits: dict) -> dict:
    found: dict = {}
    for key, link in table.items():
        if link["all_ages"]:
            continue
        a, b, k = key
        texts: list[str] = []
        for edge in ((a, b, k), (b, a, k)):
            if graph.has_edge(*edge):
                texts += fit_reasons(fits.get(graph.edges[edge]["segment_id"]))
        if texts:
            found[key] = list(dict.fromkeys(texts))
    return found


def link_fixes(graph, table: dict, fits: dict, profile, weights) -> dict:
    found: dict = {}
    for key, link in table.items():
        if link["all_ages"] or link["no_fix"]:
            continue
        a, b, k = key
        best = None
        for edge in ((a, b, k), (b, a, k)):
            if not graph.has_edge(*edge):
                continue
            data = graph.edges[edge]
            fit = fits.get(data["segment_id"])
            if not data["bike_ok"] or not fit or fit["status"] != "fix":
                continue
            counts = disruption_counts(
                fit["fix"],
                {**data, "adt": data.get("adt") or 0.0, "length_m": link["length_m"]},
                profile,
            )
            record = {"street": street_name(data), "fix": fit["fix"]} | {
                name: counts[name] for name in COUNTS
            }
            if best is None or disruption_score(record, weights) > disruption_score(best, weights):
                best = record
        if best is not None:
            found[key] = best
    return found


def group_works(table: dict, fixes: dict, fixable: list, weights) -> list:
    groups: dict = {}
    for key in fixable:
        groups.setdefault((fixes[key]["street"], fixes[key]["fix"]), []).append(key)
    works = []
    for (street, fix), keys in groups.items():
        joined = nx.Graph()
        for a, b, _ in keys:
            joined.add_edge(a, b)
        parts = {
            node: index
            for index, part in enumerate(nx.connected_components(joined))
            for node in part
        }
        by_part: dict = {}
        for key in keys:
            by_part.setdefault(parts[key[0]], []).append(key)
        for links in by_part.values():
            links.sort()
            work = {"street": street, "fix": fix, "links": links}
            work["km"] = sum(table[link]["length_m"] for link in links) / 1000
            for name in COUNTS:
                work[name] = sum(fixes[link][name] for link in links)
            work["score"] = disruption_score(work, weights)
            works.append(work)
    works.sort(key=lambda work: work["links"][0])
    return works


def list_no_fix(table: dict, missing: list, streets: dict) -> list:
    by_street: dict = {}
    for key in missing:
        by_street.setdefault(streets.get(key, "unnamed road"), []).append(key)
    return [
        {
            "street": street,
            "links": sorted(keys),
            "km": sum(table[key]["length_m"] for key in keys) / 1000,
        }
        for street, keys in sorted(by_street.items())
    ]


def list_blockers(
    table: dict,
    missing: list,
    streets: dict,
    trips: list,
    roads: dict,
    reasons: dict,
) -> list:
    held = set(missing)
    stopped: dict = {}
    for _, _, path in trips:
        if path is None:
            continue
        stoppers = {streets.get(link, "unnamed road") for link in path if link in held}
        if len(stoppers) == 1:
            street = stoppers.pop()
            stopped[street] = stopped.get(street, 0) + 1
    found = []
    for gap in list_no_fix(table, missing, streets):
        types: dict = {}
        why: list = []
        for link in gap["links"]:
            kind = roads.get(link, {}).get("type") or "road"
            types[kind] = types.get(kind, 0) + table[link]["length_m"]
            why += [text for text in reasons.get(link, []) if text not in why]
        found.append(
            gap
            | {
                "road_type": min(types, key=lambda kind: (-types[kind], kind)),
                "trips": stopped.get(gap["street"], 0),
                "reasons": why,
                "owner": next(
                    (
                        roads[link]["owner"]
                        for link in gap["links"]
                        if roads.get(link, {}).get("owner")
                    ),
                    None,
                ),
            }
        )
    found.sort(key=lambda item: (-item["trips"], item["street"]))
    return found


def trip_needs(table: dict, trips: list, fixes: dict, owner: dict) -> list:
    needs = []
    for one, two, path in trips:
        if path is None or any(not table[link]["all_ages"] and link not in fixes for link in path):
            continue
        need = frozenset(owner[link] for link in path if not table[link]["all_ages"])
        pair = tuple(sorted((sort_key({"osm_id": one["id"]}), sort_key({"osm_id": two["id"]}))))
        needs.append((need, pair))
    return needs


def next_step(needs: list, fixed: set, works: list) -> frozenset | None:
    groups: dict = {}
    for need, pair in needs:
        left = need - fixed
        if left:
            count, lowest = groups.get(left, (0, pair))
            groups[left] = (count + 1, min(lowest, pair))
    best = None
    for added, (_, pair) in groups.items():
        gain = sum(count for left, (count, _) in groups.items() if left <= added)
        cost = sum(works[index]["score"] for index in added)
        rank = (-Fraction(gain) / (Fraction(cost) + 1), pair)
        if best is None or rank < best[0]:
            best = (rank, added)
    return best[1] if best else None


def build_ladder(
    table: dict,
    links: list,
    joined: list,
    fixes: dict,
    weights,
    streets: dict | None = None,
    max_trip_m: float | None = None,
    roads: dict | None = None,
    reasons: dict | None = None,
) -> dict:
    missing = [key for key in links if not table[key]["all_ages"] and key not in fixes]
    fixable = [key for key in links if not table[key]["all_ages"] and key in fixes]
    works = group_works(table, fixes, fixable, weights)
    owner = {link: index for index, work in enumerate(works) for link in work["links"]}
    trips = option_trips(table, links, joined, max_trip_m)
    needs = trip_needs(table, trips, fixes, owner)
    fixed: set = set()
    steps = []
    added: frozenset = frozenset()
    while True:
        mended = frozenset(link for index in fixed for link in works[index]["links"])
        running = {name: sum(works[index][name] for index in fixed) for name in COUNTS}
        running["score"] = sum(works[index]["score"] for index in fixed)
        steps.append(
            {
                "step": len(steps),
                "works": sorted(added),
                "totals": option_totals(table, links, joined, mended, trips),
                "disruption": running,
            }
        )
        added = next_step(needs, fixed, works)
        if added is None:
            break
        fixed |= added
    ceiling = option_totals(table, links, joined, frozenset(links), trips)
    return {
        "works": works,
        "no_fix": list_no_fix(table, missing, streets or {}),
        "blockers": list_blockers(table, missing, streets or {}, trips, roads or {}, reasons or {}),
        "ceiling": ceiling["score"],
        "steps": steps,
    }
