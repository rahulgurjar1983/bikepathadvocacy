import json
import math
from itertools import pairwise
from pathlib import Path

from bikeplan.parking import FIELDS, verify_parking
from bikeplan.proposal_inputs import delivery_record

TOLERANCE = 1e-6
MODES = ("strict", "first_leg_model")


def same(left, right) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=TOLERANCE, abs_tol=TOLERANCE)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right, strict=True))
    return left == right


def differ(label: str, found, expected) -> list[str]:
    return [] if same(found, expected) else [f"{label} is {found!r}, the data gives {expected!r}"]


def edge_ends(edges):
    return [(edge[0], edge[1]) for edge in edges]


def route_problems(label, witness, detour_max):
    problems = []
    entrance = witness["arrival_evidence"].get("node")
    if witness["evidence_status"] != "confirmed":
        problems.append(f"{label} is not confirmed")
    for direction, start, finish in (
        ("outbound", witness["origin"], entrance),
        ("return", entrance, witness["origin"]),
    ):
        route = witness[direction]
        edges = route["edges"]
        name = f"{label} {direction}"
        ends = edge_ends(edges)
        if edges and (ends[0][0] != start or ends[-1][1] != finish):
            problems.append(f"{name} does not run from node {start} to node {finish}")
        if any(a[1] != b[0] for a, b in pairwise(ends)):
            problems.append(f"{name} edges do not join")
        if len(route["links"]) != len(edges) or [r["edge"] for r in route["links"]] != edges:
            problems.append(f"{name} link records do not match its edges")
        if any(r.get("status") != "confirmed" or r.get("legal") is False for r in route["links"]):
            problems.append(f"{name} uses a link that is not confirmed")
        pairs = list(pairwise(edges))
        moves = route["movements"]
        if [(m["incoming"], m["outgoing"]) for m in moves] != pairs:
            problems.append(f"{name} movement records do not match its edges")
        if any(m.get("status") != "confirmed" or m.get("legal") is False for m in moves):
            problems.append(f"{name} uses a movement that is not confirmed")
        if route["distance_m"] < route["shortest_m"] - 1e-6:
            problems.append(f"{name} is shorter than the shortest route")
        if route["distance_m"] > route["shortest_m"] * detour_max + 1e-6:
            problems.append(f"{name} is longer than the detour limit")
    return problems


def packages_routes(label, package):
    detour = package["rules"]["detour_max"] if "rules" in package else math.inf
    return [
        line
        for index, witness in enumerate(package["strict"])
        for line in route_problems(f"{label} route {index}", witness, detour)
    ]


def works_problems(label, catalog, package):
    works = package["works"]
    ids = sorted(set(package["element_ids"]))
    problems = differ(f"{label} works element_ids", works["element_ids"], ids)
    missing = [key for key in ids if key not in catalog]
    if missing:
        return [*problems, f"{label} works name {missing[0]}, which is not in the catalog"]
    links = [catalog[key] for key in ids if catalog[key]["kind"] == "link"]
    problems += differ(
        f"{label} works unique_roads", works["unique_roads"], len({i["road_id"] for i in links})
    )
    problems += differ(
        f"{label} works unnamed_roads",
        works["unnamed_roads"],
        len({i["road_id"] for i in links if i["name_gap"]}),
    )
    for kind, value in works["km_by_design"].items():
        problems += differ(
            f"{label} works km_by_design {kind}",
            value,
            sum(i["length_m"] for i in links if i["design"] == kind) / 1000,
        )
    designs = {i["design"] for i in links}
    problems += [
        f"{label} works km_by_design lacks {kind}"
        for kind in sorted(designs - works["km_by_design"].keys())
    ]
    problems += differ(
        f"{label} works crossing_upgrades",
        works["crossing_upgrades"],
        [key for key in ids if catalog[key]["kind"] == "crossing"],
    )
    sectioned = sorted(key for item in works["sections"] for key in item["element_ids"])
    problems += differ(f"{label} works sections cover", sectioned, sorted(i["id"] for i in links))
    problems += differ(
        f"{label} works distinct_sections", works["distinct_sections"], len(works["sections"])
    )
    for item in works["sections"]:
        problems += differ(
            f"{label} works section {item['id']} length_m",
            item["length_m"],
            sum(catalog[key]["length_m"] for key in item["element_ids"]),
        )
    return problems


def parking_problems(label, catalog, package):
    works = package["works"]
    ids = sorted(set(works["element_ids"]))
    if any(key not in catalog for key in ids):
        return []
    problems = []
    for key in ids:
        row = catalog[key]["parking_spaces"]
        if all(row[field] is not None for field in FIELDS):
            if row["before"] - row["removed"] + row["added"] != row["after"]:
                problems.append(
                    f"{label} parking on {key}: before, removed, added and after differ"
                )
            if row["added"] - row["removed"] != row["net"]:
                problems.append(f"{label} parking on {key}: net differs")
    for field in FIELDS:
        known = [key for key in ids if catalog[key]["parking_spaces"][field] is not None]
        subtotal = sum(catalog[key]["parking_spaces"][field] for key in known)
        saved = works["parking_spaces"][field]
        gap = len(known) < len(ids)
        problems += differ(
            f"{label} parking {field} known_subtotal", saved["known_subtotal"], subtotal
        )
        problems += differ(
            f"{label} parking {field} value", saved["value"], None if gap else subtotal
        )
        problems += differ(
            f"{label} parking {field} missing_element_ids",
            saved["missing_element_ids"],
            sorted(set(ids) - set(known)),
        )
    try:
        verify_parking(catalog, works)
    except (ValueError, KeyError) as error:
        problems.append(f"{label} parking: {error}")
    return problems


def shares_of(frontier):
    shares = frontier["trip_sources"]["population"]["shares"]
    return [item for item in shares if item["people"] > 0]


def resident_problems(label, frontier, baseline, package):
    shares = shares_of(frontier)
    types = {
        item["id"]: item.get("type", "unknown") for item in frontier["trip_sources"]["destinations"]
    }
    saved = package["resident_outcomes"]["strict"]
    if saved["unique_residents"]["after"] is None:
        return []
    pairs = {
        "before": {(w["origin"], w["destination"]) for w in baseline["strict"]},
        "after": {(w["origin"], w["destination"]) for w in package["strict"]},
    }
    pairs["newly_gained"] = pairs["after"] - pairs["before"]

    def members(found):
        nodes = {node for node, _ in found}
        return [item for item in shares if item["node"] in nodes]

    problems = []
    for name, found in pairs.items():
        rows = members(found)
        problems += differ(
            f"{label} residents {name}",
            saved["unique_residents"][name],
            sum(i["people"] for i in rows),
        )
        keys = sorted((i["unit"], i["node"]) for i in saved["membership"][name])
        problems += differ(
            f"{label} resident membership {name}",
            keys,
            sorted((i["unit"], i["node"]) for i in rows),
        )
        problems += differ(
            f"{label} resident membership {name} people",
            sorted(i["people"] for i in saved["membership"][name]),
            sorted(i["people"] for i in rows),
        )
        for kind in sorted(set(types.values())):
            of_type = {pair for pair in found if types.get(pair[1], "unknown") == kind}
            problems += differ(
                f"{label} residents by type {kind} {name}",
                saved["by_place_type"].get(kind, {}).get(name),
                sum(i["people"] for i in members(of_type)),
            )
    problems += differ(
        f"{label} gains_counted_by_type",
        saved["gains_counted_by_type"],
        sum(item["newly_gained"] for item in saved["by_place_type"].values()),
    )
    return problems


def school_problems(label, frontier, baseline, package):
    coverage = package.get("school_coverage")
    if coverage is None:
        return []
    people = {}
    for item in frontier["trip_sources"]["population"]["shares"]:
        people[item["node"]] = people.get(item["node"], 0) + item["people"]
    problems = []
    for site in coverage["sites"]:
        found = {}
        for name, source in (("before", baseline), ("after", package)):
            found[name] = sorted(
                {
                    w["origin"]
                    for w in source["strict"]
                    if w["destination"] in site["destination_ids"]
                    and w["evidence_status"] == "confirmed"
                    and people.get(w["origin"], 0) > 0
                },
                key=str,
            )
        found["new"] = sorted(set(found["after"]) - set(found["before"]), key=str)
        text = f"{label} school {site['id']}"
        for name, origins in found.items():
            problems += differ(f"{text} origins {name}", site["origins"][name], origins)
            problems += differ(
                f"{text} resident_reach {name}",
                site["resident_reach"][name],
                sum(people[n] for n in origins),
            )
        problems += differ(
            f"{text} status", site["status"], "confirmed" if found["after"] else "unproved"
        )
    rows = coverage["sites"]
    served = {name: [s["id"] for s in rows if s["origins"][name]] for name in ("before", "after")}
    served["new"] = sorted(set(served["after"]) - set(served["before"]))
    problems += differ(f"{label} school sites served", coverage["served"], served)
    problems += differ(f"{label} school sites counted", coverage["total_known_sites"], len(rows))
    return problems


def cost_problems(label, frontier, catalog, package):
    saved = package.get("delivery")
    if saved is None:
        return []
    metadata = frontier["proposal_metadata"]
    try:
        again = delivery_record(metadata, package["element_ids"], catalog, package["project_ids"])
    except Exception as error:
        return [f"{label} delivery cannot be rebuilt from the saved metadata: {error}"]
    problems = []
    for name in ("costs", "budget", "stages", "stage_status", "dependencies"):
        problems += differ(f"{label} delivery {name}", saved[name], again[name])
    return problems


def acyclic(stages):
    waiting = {item["id"]: set(item["depends_on"]) for item in stages}
    if any(parent not in waiting for parents in waiting.values() for parent in parents):
        return "a stage depends on an unknown stage"
    while waiting:
        ready = [name for name, parents in waiting.items() if not parents]
        if not ready:
            return "stage dependencies form a cycle"
        for name in ready:
            del waiting[name]
        for parents in waiting.values():
            parents.difference_update(ready)
    return None


def delivery_stage_problems(label, package):
    stages = package.get("delivery", {}).get("stages") or []
    if not stages or not all("depends_on" in item for item in stages):
        return []
    found = acyclic(stages)
    return [f"{label} delivery: {found}"] if found else []


def stage_problems(frontier):
    plan = frontier.get("option_sets", {}).get("stage_plan")
    if not plan or not plan["stages"]:
        return []
    stages = plan["stages"]
    found = acyclic(stages)
    if found:
        return [f"stage plan: {found}"]
    shares = {}
    for item in frontier["trip_sources"]["population"]["shares"]:
        shares[item["node"]] = shares.get(item["node"], 0) + item["people"]
    by_id = {item["id"]: item for item in stages}
    problems = []
    for item in stages:
        text = f"stage plan {item['id']}"
        parents = [by_id[name] for name in item["depends_on"]]
        for parent in parents:
            if not set(parent["elements"]) <= set(item["elements"]):
                problems.append(f"{text} lacks the works of {parent['id']}")
            mine = {(t["origin"], t["destination"]) for t in item["gained_trips"]}
            theirs = {(t["origin"], t["destination"]) for t in parent["gained_trips"]}
            if mine & theirs:
                problems.append(f"{text} counts trips already gained by {parent['id']}")
        origins = {trip["origin"] for trip in item["gained_trips"]}
        problems += differ(
            f"{text} people_gained", item["people_gained"], sum(shares[o] for o in origins)
        )
        problems += differ(
            f"{text} standalone_access_claim",
            item["standalone_access_claim"],
            bool(item["gained_trips"]),
        )
    expected = [
        {"stage": item["id"], "reason": "route_stage_adds_no_complete_trip"}
        for item in stages
        if item["purpose"] == "route" and not item["gained_trips"]
    ]
    problems += differ("stage plan problems", plan["problems"], expected)
    problems += differ("stage plan valid", plan["valid"], not expected)
    return problems


def selected_problems(frontier, proposal):
    selected = proposal["selected"]
    identity = selected["identity"]
    curves = {curve["id"]: curve for curve in frontier["scenarios"]}
    curve = curves.get(identity["scenario"])
    if curve is None or identity["rank"] >= len(curve["trip_packages"]):
        return ["proposal.json selects a package that frontier.json does not hold"]
    package = curve["trip_packages"][identity["rank"]]
    problems = differ("proposal.json works", selected["works"], package["works"])
    problems += differ(
        "proposal.json strict_complete_trips",
        selected["outcomes"]["strict_complete_trips"],
        len(package["strict"]),
    )
    if "delivery" in package:
        problems += differ("proposal.json costs", selected["costs"], package["delivery"]["costs"])
        problems += differ(
            "proposal.json stages", selected["stages"], package["delivery"]["stages"]
        )
    for mode in MODES:
        if mode in package["resident_outcomes"]:
            saved = {
                k: v for k, v in package["resident_outcomes"][mode].items() if k != "membership"
            }
            problems += differ(
                f"proposal.json residents {mode}",
                selected["outcomes"]["resident_outcomes"][mode],
                saved,
            )
    return problems


def community_problems(directory: str | Path) -> list[str]:
    folder = Path(directory)
    problems = [
        f"{name} is missing, so the community results cannot be checked"
        for name in ("frontier.json", "proposal.json")
        if not (folder / name).is_file()
    ]
    if problems:
        return problems
    frontier = json.loads((folder / "frontier.json").read_text())
    proposal = json.loads((folder / "proposal.json").read_text())
    for curve in frontier["scenarios"]:
        catalog = curve["works_catalog"]
        packages = curve["trip_packages"]
        for package in packages:
            identity = package["package"]
            label = f"{identity['scenario']}:{identity['rank']}"
            problems += packages_routes(label, package)
            problems += works_problems(label, catalog, package)
            problems += parking_problems(label, catalog, package)
            problems += school_problems(label, frontier, packages[0], package)
            if "resident_outcomes" in package and MODES[0] in package["resident_outcomes"]:
                problems += resident_problems(label, frontier, packages[0], package)
            problems += cost_problems(label, frontier, catalog, package)
            problems += delivery_stage_problems(label, package)
    problems += stage_problems(frontier)
    problems += selected_problems(frontier, proposal)
    return problems
