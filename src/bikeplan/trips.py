import html
import json
from itertools import combinations, pairwise
from pathlib import Path

import networkx as nx

from bikeplan.access import last_legs, reach


def evidence(record, selected):
    needs = set(record.get("needs", ()))
    status = record.get("status", "unknown")
    if needs and needs <= selected:
        status = record.get("after_status", status)
    if status == "confirmed" and not record.get("source"):
        status = "unknown"
    model_needs = set(record.get("model_needs", ()))
    if "model_needs" in record and not model_needs <= selected:
        status = "unknown" if status == "confirmed" else status
    return {
        **record,
        "status": status,
        "later_work": sorted((needs | model_needs) - selected),
        **({"aaa": model_needs <= selected} if "model_needs" in record else {}),
    }


def route_graph(graph, links, movements, strict):
    result = nx.DiGraph()
    keys = sorted((key for key in graph.edges(keys=True) if graph.edges[key]["bike_ok"]), key=str)
    for node in sorted(graph.nodes, key=str):
        result.add_node(("start", node))
        result.add_node(("finish", node))
        result.add_edge(("start", node), ("finish", node), length_m=0.0)
    for key in keys:
        record = links.get(key, {"status": "unknown"})
        if (
            record.get("legal") is False
            or (not strict and graph.edges[key].get("candidate"))
            or (strict and record["status"] != "confirmed")
        ):
            continue
        u, v, _ = key
        state = ("edge", *key)
        result.add_edge(("start", u), state, length_m=graph.edges[key]["length_m"])
        result.add_edge(state, ("finish", v), length_m=0.0)
    for outgoing in keys:
        target = ("edge", *outgoing)
        if target not in result:
            continue
        for incoming in sorted(graph.in_edges(outgoing[0], keys=True), key=str):
            source = ("edge", *incoming)
            record = movements.get((incoming, outgoing), {"status": "unknown"})
            if (
                source not in result
                or record.get("legal") is False
                or (strict and record["status"] != "confirmed")
            ):
                continue
            result.add_edge(source, target, length_m=graph.edges[outgoing]["length_m"])
    return result


def route_record(path, graph, links, movements):
    edges = [tuple(state[1:]) for state in path if state[0] == "edge"]
    return {
        "edges": [list(key) for key in edges],
        "distance_m": sum(graph.edges[key]["length_m"] for key in edges),
        "links": [{"edge": list(key), **links.get(key, {"status": "unknown"})} for key in edges],
        "movements": [
            {
                "incoming": list(incoming),
                "outgoing": list(outgoing),
                **movements.get((incoming, outgoing), {"status": "unknown"}),
            }
            for incoming, outgoing in pairwise(edges)
        ],
    }


def route_groups(witnesses, movements):
    joined = nx.Graph()
    joined.add_nodes_from(range(len(witnesses)))
    joins = []
    edge_sets = [
        {tuple(key) for direction in ("outbound", "return") for key in witness[direction]["edges"]}
        for witness in witnesses
    ]
    for a, b in combinations(range(len(witnesses)), 2):
        common = sorted(edge_sets[a] & edge_sets[b], key=str)
        if common:
            proof = {"shared_edge": list(common[0])}
        else:
            forward = [
                (incoming, outgoing)
                for incoming in sorted(edge_sets[a], key=str)
                for outgoing in sorted(edge_sets[b], key=str)
                if incoming[1] == outgoing[0]
                and movements.get((incoming, outgoing), {}).get("status") == "confirmed"
                and movements.get((incoming, outgoing), {}).get("legal") is not False
            ]
            backward = [
                (incoming, outgoing)
                for incoming in sorted(edge_sets[b], key=str)
                for outgoing in sorted(edge_sets[a], key=str)
                if incoming[1] == outgoing[0]
                and movements.get((incoming, outgoing), {}).get("status") == "confirmed"
                and movements.get((incoming, outgoing), {}).get("legal") is not False
            ]
            if not forward or not backward:
                continue
            proof = {"movements": [[list(i), list(o)] for i, o in (forward[0], backward[0])]}
        joined.add_edge(a, b)
        joins.append({"routes": [a, b], "status": "confirmed", **proof})
    groups = [sorted(group) for group in nx.connected_components(joined)]
    return [{"id": f"group-{n}", "routes": group} for n, group in enumerate(groups)], joins


def first_leg_model(graph, people, destinations, links, reach_m, detour_max, first_leg_m):
    if not first_leg_m:
        return []
    scores = {
        key: {
            "lts": item.get("lts", 4),
            "aaa": item.get("aaa", item["status"] == "confirmed"),
        }
        for key in graph.edges(keys=True)
        for item in [links.get(key, {"status": "unknown"})]
    }
    placed = [item for item in destinations if item.get("model_node") in graph]
    if not placed:
        return []
    legs = last_legs(graph, scores, sorted(people, key=str), first_leg_m)
    results = reach(
        graph,
        [item["model_node"] for item in placed],
        reach_m,
        detour_max,
        {key for key, item in scores.items() if item["aaa"]},
        legs=legs,
    )
    return [
        {"origin": origin, "destination": item["id"]}
        for item, result in zip(placed, results, strict=True)
        for origin in sorted(people, key=str)
        if people[origin] > 0 and origin in result.safe
    ]


def complete_trips(
    graph, people, destinations, links, movements, selected, reach_m, detour_max, first_leg_m=0.0
):
    links = {key: evidence(item, selected) for key, item in links.items()}
    movements = {key: evidence(item, selected) for key, item in movements.items()}
    witnesses, gaps = [], []
    known = []
    for destination in sorted(destinations, key=lambda item: item["id"]):
        entrances = destination.get("entrances", [])
        valid = [
            item
            for item in entrances
            if item.get("status") == "confirmed"
            and item.get("source")
            and item.get("bike_accessible") is True
            and item.get("node") in graph
        ]
        if not valid:
            gaps.append({"destination": destination["id"], "reason": "unknown_entrance_link"})
        known.extend((destination, entrance) for entrance in sorted(valid, key=lambda i: i["id"]))
    if known:
        legal = route_graph(graph, links, movements, False)
        strict = route_graph(graph, links, movements, True)
        for destination, entrance in known:
            node = entrance["node"]
            searches = {}
            for mode, network in (("legal", legal), ("strict", strict)):
                searches[mode, "outbound"] = nx.single_source_dijkstra(
                    network.reverse(copy=False), ("finish", node), weight="length_m"
                )
                searches[mode, "return"] = nx.single_source_dijkstra(
                    network, ("start", node), weight="length_m"
                )
            for origin in sorted(people, key=str):
                if people[origin] <= 0 or origin not in graph:
                    continue
                if ("start", origin) not in searches["legal", "outbound"][0] and (
                    "finish",
                    origin,
                ) not in searches["legal", "return"][0]:
                    continue
                proof = {}
                for direction in ("outbound", "return"):
                    target = ("start", origin) if direction == "outbound" else ("finish", origin)
                    shortest, legal_paths = searches["legal", direction]
                    distances, paths = searches["strict", direction]
                    gap = {
                        "origin": origin,
                        "destination": destination["id"],
                        "entrance": entrance["id"],
                        "direction": direction,
                    }
                    if target not in shortest:
                        gaps.append({**gap, "reason": f"no_{direction}_route"})
                        continue
                    if target not in distances:
                        path = legal_paths[target]
                        path = list(reversed(path)) if direction == "outbound" else path
                        gaps.append(
                            {
                                **gap,
                                "reason": "unconfirmed_route",
                                **route_record(path, graph, links, movements),
                            }
                        )
                        continue
                    distance = distances[target]
                    if distance > reach_m or distance > detour_max * shortest[target]:
                        gaps.append(
                            {
                                **gap,
                                "reason": "reach_limit" if distance > reach_m else "detour_limit",
                                "distance_m": distance,
                                "shortest_m": shortest[target],
                            }
                        )
                        continue
                    path = paths[target]
                    path = list(reversed(path)) if direction == "outbound" else path
                    proof[direction] = {
                        **route_record(path, graph, links, movements),
                        "shortest_m": shortest[target],
                    }
                if len(proof) == 2:
                    needs = {
                        name
                        for route in proof.values()
                        for record in [*route["links"], *route["movements"]]
                        for name in record.get("needs", ())
                    }
                    witnesses.append(
                        {
                            "origin": origin,
                            "destination": destination["id"],
                            "entrance": entrance["id"],
                            "arrival_evidence": entrance,
                            "evidence_status": "confirmed",
                            "required_elements": sorted(needs),
                            **proof,
                        }
                    )
    witnesses.sort(key=lambda item: (str(item["origin"]), item["destination"], item["entrance"]))
    groups, joins = route_groups(witnesses, movements)
    return {
        "strict": witnesses,
        "groups": groups,
        "joins": joins,
        "continuous_network": bool(witnesses) and len(groups) == 1,
        "gaps": gaps,
        "later_work": sorted(
            {name for item in [*links.values(), *movements.values()] for name in item["later_work"]}
        ),
        "first_leg_model": first_leg_model(
            graph,
            people,
            [item for item in destinations if any(item is d for d, _ in known)],
            links,
            reach_m,
            detour_max,
            first_leg_m,
        )
        if known or not first_leg_m
        else None,
        "first_leg_status": "modelled" if known else "unknown_entrance_links",
        "first_leg_limit": (
            "Calm first-leg allowance is a model-score assumption; it does not prove "
            "a return trip or entrance link. This list covers only known-entrance destinations; "
            "the access score can also use centroid snaps."
        ),
        "limit": (
            "Route witnesses prove the model result, not field safety. "
            "Population nodes model origins, not home addresses."
        ),
        "rules": {"reach_m": reach_m, "detour_max": detour_max, "first_leg_m": first_leg_m},
    }


def snapshot_trip_inputs(snapshot, kept, nodes, graph, scores, planning):
    raw = json.loads((Path(snapshot) / "places.json").read_text()).get("trip_evidence", {})
    entrances = raw.get("entrances", [])
    destinations = [
        {
            "id": place["osm_id"],
            "name": place["name"],
            "model_node": node,
            "entrances": [item for item in entrances if item["destination"] == place["osm_id"]],
        }
        for place, node in zip(kept, nodes, strict=True)
    ]
    supplied = {tuple(item["edge"]): item for item in raw.get("links", [])}
    links = {
        key: {
            "status": "assumed" if scores[key]["aaa"] else "unknown",
            "reason": "No confirmed link evidence; stress is a model score.",
            "lts": scores[key]["lts"],
            "aaa": not planning.edges.get(key, {"needs": ["missing"]})["needs"],
            "model_needs": planning.edges.get(key, {"needs": ["missing"]})["needs"],
            **supplied.get(key, {}),
        }
        for key in graph.edges(keys=True)
    }
    movements = {
        (tuple(item["incoming"]), tuple(item["outgoing"])): item
        for item in raw.get("movements", [])
    }
    return destinations, links, movements


def trip_section(frontier):
    rows = []
    for curve in frontier["scenarios"]:
        for package in curve.get("trip_packages", []):
            values = [
                curve["id"],
                package["package"]["rank"],
                len(package["strict"]),
                len(package["groups"]),
                len(package["gaps"]),
                "Joined" if package["continuous_network"] else "No joined network claim",
            ]
            rows.append(
                "<tr>"
                + "".join(f"<td><code>{html.escape(str(v))}</code></td>" for v in values)
                + "</tr>"
            )
    return (
        '<section id="complete-trips"><h2>Complete trips and route groups</h2>'
        "<p>A strict trip needs a known bike entrance, proved links and crossing movements, "
        "and a valid return route within the reach and detour limits. Separate route groups "
        "are not one joined network. Calm first legs are model-score assumptions. "
        "Unknown entrance links and later works stay in the saved gaps. "
        "Route proof does not prove field safety.</p>"
        "<p>Each curve package has its exact work set and route proof in frontier.json. "
        "The old shortlist has its own trip proof in projects.geojson.</p>"
        "<details><summary>Trip proof by package</summary><table><thead><tr>"
        "<th>Scenario</th><th>Rank</th><th>Strict return trips</th><th>Groups</th>"
        "<th>Gaps</th><th>Network claim</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></details></section>"
    )
