from fractions import Fraction

import networkx as nx

from bikeplan.access import sort_key
from bikeplan.fit import disruption_counts, disruption_score
from bikeplan.network import first
from bikeplan.options import link_id
from bikeplan.rating import option_totals, option_trips

COUNTS = ("parking_spaces", "lane_km", "speed_km", "path_km")


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
    return {
        "works": works,
        "no_fix": list_no_fix(table, missing, streets or {}),
        "steps": steps,
    }
