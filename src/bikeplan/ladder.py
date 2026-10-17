from fractions import Fraction

import networkx as nx

from bikeplan.access import sort_key
from bikeplan.fit import disruption_counts, disruption_score
from bikeplan.network import first
from bikeplan.options import is_unpaved, link_id
from bikeplan.rating import option_totals, option_trips
from bikeplan.stress import FOOT_PATHS, OFF_ROAD_FACILITIES, path_min_width

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


def is_path(data: dict) -> bool:
    return (
        data.get("bike_facility") in OFF_ROAD_FACILITIES or first(data.get("highway")) in FOOT_PATHS
    )


def path_reasons(data: dict, score: dict | None, profile) -> list[str]:
    found: list[str] = []
    width = data.get("width_tag_m")
    if width is not None and width < path_min_width(profile):
        found.append(f"narrower than {path_min_width(profile):g} m")
    if is_unpaved(data):
        found.append("unpaved surface")
    if score is not None and score["lts"] > 1:
        found.append("crosses a busy road")
    return found


def link_reasons(graph, table: dict, fits: dict, scores: dict | None = None, profile=None) -> dict:
    found: dict = {}
    for key, link in table.items():
        if link["all_ages"]:
            continue
        a, b, k = key
        texts: list[str] = []
        for edge in ((a, b, k), (b, a, k)):
            if not graph.has_edge(*edge):
                continue
            data = graph.edges[edge]
            if scores is not None and is_path(data):
                texts += path_reasons(data, scores.get(edge), profile)
            else:
                texts += fit_reasons(fits.get(data["segment_id"]))
        if texts:
            found[key] = list(dict.fromkeys(texts))
    return found


def new_path_fix(link: dict, street: str, weights) -> dict:
    counts = {"parking_spaces": 0, "lane_km": 0.0, "speed_km": 0.0}
    counts["path_km"] = link["length_m"] / 1000
    return (
        {"street": street, "fix": "new_path"}
        | counts
        | {"least": disruption_score(counts, weights)}
    )


def link_fixes(graph, table: dict, fits: dict, profile, weights) -> dict:
    found: dict = {}
    for key, link in table.items():
        if link["all_ages"] or link["no_fix"]:
            continue
        if link.get("new_path"):
            found[key] = new_path_fix(link, f"new path beside {link['label']}", weights)
            continue
        a, b, k = key
        best = None
        for edge in ((a, b, k), (b, a, k)):
            if not graph.has_edge(*edge):
                continue
            data = graph.edges[edge]
            if link.get("unpaved") and data["bike_ok"]:
                best = new_path_fix(link, street_name(data), weights)
                break
            fit = fits.get(data["segment_id"])
            if not data["bike_ok"] or not fit or fit["status"] != "fix":
                continue
            sized = {**data, "adt": data.get("adt") or 0.0, "length_m": link["length_m"]}
            options = [
                (item["fix"], disruption_counts(item["fix"], sized, profile))
                for item in fit.get("candidates", [])
                if item["accepted"]
            ] or [(fit["fix"], disruption_counts(fit["fix"], sized, profile))]
            free = [
                option
                for option in options
                if option[0] != "quietway"
                and not option[1]["parking_spaces"]
                and not option[1]["lane_km"]
            ]
            pool = free if free and profile.fit.prefer_separation.value else options
            fix, counts = min(
                pool,
                key=lambda option: (
                    disruption_score(option[1], weights),
                    option[0] != fit["fix"],
                ),
            )
            record = {"street": street_name(data), "fix": fix} | {
                name: counts[name] for name in COUNTS
            }
            record["least"] = min(disruption_score(option[1], weights) for option in options)
            if best is None or disruption_score(record, weights) > disruption_score(best, weights):
                best = record
        if best is not None:
            found[key] = best
    return found


def group_works(table: dict, fixes: dict, fixable: list, weights) -> list:
    groups: dict = {}
    for key in fixable:
        far = bool(table[key].get("outside"))
        groups.setdefault((fixes[key]["street"], fixes[key]["fix"], far), []).append(key)
    works = []
    for (street, fix, far), keys in groups.items():
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
            if far:
                work["outside"] = True
            work["km"] = sum(table[link]["length_m"] for link in links) / 1000
            for name in COUNTS:
                work[name] = sum(fixes[link][name] for link in links)
            work["score"] = disruption_score(work, weights)
            if all("least" in fixes[link] for link in links):
                work["least"] = sum(fixes[link]["least"] for link in links)
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
