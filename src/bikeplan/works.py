import hashlib
import html
import json
from collections import defaultdict

import networkx as nx

from bikeplan.network import inside_length, parking_on_side
from bikeplan.parking import parking_record, parking_totals

DESIGNS = (
    "protected_cycleway",
    "shared_path",
    "quiet_street",
    "path_use_unknown",
    "design_unknown",
)
SURVEYS = ("walking_width", "trees", "bus_stops", "utilities", "drainage", "driveways")


def stable_id(prefix, values):
    return prefix + hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]


def endpoint(graph, node, road_name):
    data = graph.nodes[node]
    names = sorted(
        {
            d["name"]
            for _, _, d in graph.edges(node, data=True)
            if isinstance(d.get("name"), str) and d["name"] != road_name
        }
    )
    name = data.get("name") or (" / ".join(names) if names else None)
    return {
        "id": str(node),
        "name": name,
        "name_gap": name is None,
        "x": data.get("x"),
        "y": data.get("y"),
    }


def design_type(element):
    kinds = {s["kind"] for s in element.get("after", [])}
    if element["fix"] == "quietway":
        return "quiet_street"
    if "shared_path" in kinds:
        return "shared_path"
    if "cycleway" in kinds and "separator" in kinds:
        if element["fix"] not in ("verge_path", "new_path"):
            return "protected_cycleway"
        if "footpath" in kinds:
            return "protected_cycleway"
    return "path_use_unknown" if element["fix"] in ("verge_path", "new_path") else "design_unknown"


def plan(element, data):
    before, after = element.get("before", []), element.get("after", [])
    widths = [
        [s["width_m"] for s in strips if s["kind"] == "through"] for strips in (before, after)
    ]
    known = bool(before or after)
    parking = {side: parking_on_side(data, side) for side in ("left", "right")}
    before_sides = [side for side, state in parking.items() if state == "yes"]
    unknown = [side for side, state in parking.items() if state == "unknown"]
    removed = {"cycleway_parking_one_side": 1, "cycleway_parking_both_sides": 2}.get(
        element["fix"], 0
    )
    after_sides = before_sides[removed:] if not unknown else None
    walking = [
        [s["width_m"] for s in strips if s["kind"] == "footpath"] for strips in (before, after)
    ]
    return {
        "lanes": {
            "before_count": len(widths[0]) if known else None,
            "after_count": len(widths[1]) if known else None,
            "before_widths_m": widths[0] if known else None,
            "after_widths_m": widths[1] if known else None,
            "removed": max(0, len(widths[0]) - len(widths[1])) if known else None,
            "narrowed": any(a < b for a, b in zip(widths[1], widths[0], strict=False))
            if known
            else None,
            "evidence_status": "modelled" if known else "unknown",
            "source": element.get("width_source"),
        },
        "parking": {
            "before_sides": before_sides if not unknown else None,
            "after_sides": after_sides,
            "removed_side_count": removed,
            "unknown_sides": unknown,
            "side_rule": (
                "Left then right in the saved edge direction; unknown sides need a survey."
            ),
        },
        "walking": {
            "before_m": walking[0] or None,
            "after_m": walking[1] or None,
            "reason": "No walking width evidence." if not all(walking) else None,
        },
        "before": before,
        "after": after,
        "turn_changes": element.get("turn_changes"),
        "access_changes": element.get("access_changes"),
        "survey_needs": [key for key in SURVEYS if key not in element.get("site_checks", {})],
    }


def works_catalog(graph, elements, retained=()):
    elements = dict(elements)
    for key in retained:
        data = graph.edges[tuple(key)]
        name = f"segment:{data['segment_id']}"
        elements.setdefault(
            name,
            {
                "kind": "segment",
                "segment": data["segment_id"],
                "fix": "existing",
                "before": [],
                "after": [],
            },
        )
    segments = defaultdict(list)
    for u, v, k, data in graph.edges(keys=True, data=True):
        if data.get("bike_ok"):
            segments[str(data["segment_id"])].append(((u, v, k), data))
    catalog = {}
    for name, element in sorted(elements.items()):
        if element["kind"] == "junction":
            node = element["junction"]
            catalog[name] = {
                "id": name,
                "kind": "crossing",
                "fix": element["fix"],
                "name": element.get("street"),
                "endpoints": [endpoint(graph, node, None)],
                "turn_changes": element.get("turn_changes"),
                "access_changes": element.get("access_changes"),
                "parking_spaces": parking_record(
                    element,
                    element.get(
                        "parking_evidence", graph.graph.get("parking_evidence", {}).get(name)
                    ),
                ),
            }
            continue
        edges = sorted(segments.get(str(element["segment"]), []), key=lambda item: str(item[0]))
        if not edges:
            raise ValueError(f"Work has no graph edges: {name}")
        (u, v, _), data = next((item for item in edges if not item[1].get("reversed")), edges[0])
        road_name = data.get("name") if not data.get("candidate") else None
        if not isinstance(road_name, str):
            road_name = None
        road_id = (
            stable_id("road:", [road_name, data.get("ref")])
            if road_name
            else stable_id("road:", [data.get("osm_way", element["segment"])])
        )
        catalog[name] = {
            "id": name,
            "kind": "link",
            "name": road_name,
            "name_gap": road_name is None,
            "road_id": road_id,
            "fix": element["fix"],
            "design": design_type(element),
            "length_m": inside_length(graph, u, v, data),
            "endpoints": [endpoint(graph, n, road_name) for n in (u, v)],
            "directed_edges": [list(key) for key, _ in edges],
            "evidence_status": "modelled",
            "width_source": element.get("width_source"),
            "width_confidence": element.get("width_confidence"),
            **plan(element, data),
            "parking_spaces": parking_record(
                element,
                element.get("parking_evidence", graph.graph.get("parking_evidence", {}).get(name)),
            ),
        }
    return catalog


def works_package(catalog, selected, retained=(), gaps=()):
    selected = sorted(set(selected))
    links = [catalog[key] for key in selected if catalog[key]["kind"] == "link"]
    grouped = defaultdict(list)
    for item in links:
        signature = json.dumps(
            {
                key: item[key]
                for key in (
                    "road_id",
                    "design",
                    "before",
                    "after",
                    "parking",
                    "walking",
                    "turn_changes",
                    "access_changes",
                )
            },
            sort_keys=True,
        )
        grouped[signature].append(item)
    sections = []
    for items in grouped.values():
        network = nx.Graph()
        at_node = defaultdict(list)
        for item in items:
            network.add_node(item["id"])
            for end in item["endpoints"]:
                at_node[end["id"]].append(item["id"])
        for ids in at_node.values():
            nx.add_path(network, ids)
        by_id = {item["id"]: item for item in items}
        for group in nx.connected_components(network):
            records = [by_id[key] for key in sorted(group)]
            ends = defaultdict(list)
            for item in records:
                for end in item["endpoints"]:
                    ends[end["id"]].append(end)
            endpoints = (
                [records[0]["endpoints"][0]]
                if all(len(e) == 2 for e in ends.values())
                else [e[0] for _, e in sorted(ends.items()) if len(e) != 2]
            )
            sections.append(
                {
                    "id": stable_id("works:", sorted(group)),
                    "road_id": records[0]["road_id"],
                    "element_ids": sorted(group),
                    "length_m": sum(i["length_m"] for i in records),
                    "endpoints": endpoints,
                    "parking_spaces": parking_totals(catalog, group),
                }
            )
    retained = {tuple(key) for key in retained}
    retained_items = [
        item
        for item in catalog.values()
        if item["kind"] == "link"
        and item["id"] not in selected
        and any(tuple(key) in retained for key in item["directed_edges"])
    ]
    return {
        "element_ids": selected,
        "parking_spaces": parking_totals(catalog, selected),
        "sections": sorted(sections, key=lambda item: item["id"]),
        "unique_roads": len({item["road_id"] for item in links}),
        "distinct_sections": len(sections),
        "unnamed_roads": len({item["road_id"] for item in links if item["name_gap"]}),
        "km_by_design": {
            kind: sum(item["length_m"] for item in links if item["design"] == kind) / 1000
            for kind in DESIGNS
        },
        "crossing_upgrades": [key for key in selected if catalog[key]["kind"] == "crossing"],
        "existing_links_retained": {
            "element_ids": sorted(item["id"] for item in retained_items),
            "length_m": sum(item["length_m"] for item in retained_items),
            "scope": "Links in complete proved return trips, excluding new works.",
        },
        "remaining_gaps": list(gaps),
        "evidence_status": "modelled",
        "road_rule": (
            "Exact source road name and reference; unnamed ways use source way ID. "
            "A road name is not a surveyed road register."
        ),
    }


def cells(section, catalog):
    item = catalog[section["element_ids"][0]]

    def show(value):
        return json.dumps(value, sort_keys=True) if value is not None else "Unknown"

    return [
        section["id"],
        item["name"] or "Name unknown",
        "; ".join(
            (e["name"] or "Name unknown") + " (" + e["id"] + ")" for e in section["endpoints"]
        ),
        str(round(section["length_m"], 3)),
        item["design"],
        show(item["lanes"]),
        show(item["parking"])
        + "; "
        + show(section["parking_spaces"])
        + "; "
        + show({key: catalog[key]["parking_spaces"] for key in section["element_ids"]}),
        show(item["walking"]),
        show(item["turn_changes"]),
        show(item["access_changes"]),
        ", ".join(item["survey_needs"]),
    ]


def crossing_cells(item):
    ends = "; ".join(
        (e["name"] or "Name unknown") + " (" + e["id"] + ")" for e in item["endpoints"]
    )
    return [
        item["id"],
        item["name"] or "Name unknown",
        ends,
        "0",
        item["fix"],
        "Unknown",
        json.dumps(item["parking_spaces"], sort_keys=True),
        "Unknown",
        json.dumps(item["turn_changes"]) if item["turn_changes"] is not None else "Unknown",
        json.dumps(item["access_changes"]) if item["access_changes"] is not None else "Unknown",
        ", ".join(SURVEYS),
    ]


def works_section(frontier):
    curve = next(c for c in frontier["scenarios"] if c["id"] == frontier["default"])
    if not curve.get("trip_packages") or "works" not in curve["trip_packages"][0]:
        return ""
    package = curve["trip_packages"][curve["recommended_stop"] or 0]
    works = package["works"]
    rows = [cells(s, curve["works_catalog"]) for s in works["sections"]] + [
        crossing_cells(curve["works_catalog"][key]) for key in works["crossing_upgrades"]
    ]

    def summary(record):
        return {
            key: record[key]
            for key in (
                "unique_roads",
                "distinct_sections",
                "unnamed_roads",
                "km_by_design",
                "existing_links_retained",
                "crossing_upgrades",
            )
        } | {
            "gap_records": len(record["remaining_gaps"]),
            "parking_spaces": record["parking_spaces"],
        }

    payload = {
        c["id"]: {
            "packages": [
                {
                    "summary": summary(p["works"]),
                    "rows": [s["id"] for s in p["works"]["sections"]]
                    + p["works"]["crossing_upgrades"],
                }
                for p in c["trip_packages"]
            ],
            "rows": {
                s["id"]: cells(s, c["works_catalog"])
                for p in c["trip_packages"]
                for s in p["works"]["sections"]
            }
            | {
                key: crossing_cells(c["works_catalog"][key])
                for p in c["trip_packages"]
                for key in p["works"]["crossing_upgrades"]
            },
        }
        for c in frontier["scenarios"]
    }
    table = "".join(
        "<tr>"
        + "".join("<td><code>" + html.escape(value) + "</code></td>" for value in row)
        + "</tr>"
        for row in rows
    )
    return (
        '<section id="physical-works"><h2>What the selected package builds</h2>'
        '<p id="works-package"><code>'
        + html.escape(curve["id"])
        + ":"
        + str(package["package"]["rank"])
        + "</code></p>"
        "<p>I count each physical link once. Roads use source names and references; "
        "unnamed ways use IDs and show <code>Name unknown</code>. Disjoint works stay separate. "
        "Lane widths and parking sides are model plans, not field measurements. "
        "Walking space, trees, bus stops, utilities, drainage and driveways need checks. "
        "A verge label alone does not prove shared use or space for people walking.</p>"
        '<p><a href="#F14">Road count and works totals</a>: <code id="works-summary">'
        + html.escape(json.dumps(summary(works), sort_keys=True))
        + "</code></p>"
        "<table><thead><tr>"
        + "".join(
            "<th>" + title + "</th>"
            for title in (
                "Works ID",
                "Road",
                "Endpoints",
                "Metres",
                "Design",
                "Lanes before/after",
                "Spaces before, removed, added, after and net",
                "Walking before/after",
                "Turns",
                "Access",
                "Survey needs",
            )
        )
        + '</tr></thead><tbody id="works-rows">'
        + table
        + "</tbody></table>"
        '<p><a href="#F23">Parking spaces removed in the known subset</a>. '
        "A net gain elsewhere does not hide local loss. Special uses may overlap and do not "
        "add spaces to the vehicle total. Bike parking stays separate. Missing inventory "
        "leaves capacity unknown; occupancy and spillover need their own source.</p>"
        "<p>Unknown turns and access effects need a survey. Existing links and gaps "
        "refer to proved trips; empty proof is not a claim of no route gaps. "
        "Full plans and their source limits are in <code>frontier.json</code>.</p></section>"
        '<script id="works-data" type="application/json">'
        + json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")
        + "</script>"
    )


def works_figures(frontier, text):
    curve = next(c for c in frontier["scenarios"] if c["id"] == frontier["default"])
    if not curve.get("trip_packages") or "works" not in curve["trip_packages"][0]:
        return []
    return [
        parking_figure(curve, text),
        {
            "id": "F14",
            "spec": "spec 16",
            "label": "Unique roads with new works",
            "value": curve["trip_packages"][curve["recommended_stop"] or 0]["works"][
                "unique_roads"
            ],
            "unit": "roads",
            "inputs": [
                {"name": "frontier.json", "sha256": hashlib.sha256(text.encode()).hexdigest()}
            ],
            "sources": [
                {
                    "name": "OpenStreetMap contributors",
                    "licence": "ODbL 1.0",
                    "request": "network.osm.gz in the snapshot folder",
                }
            ],
            "method": (
                "I union road IDs for selected links. The saved plans show distinct sections, "
                "design lengths, retained links, crossings and gaps for each package. "
                "Each link counts once across projects and reverse edges. "
                "Unknown names use source way IDs."
            ),
            "recipe": (
                "import json;d=json.load(open('frontier.json'));"
                "c=next(c for c in d['scenarios'] if c['id']==d['default']);"
                "p=c['trip_packages'][c['recommended_stop'] or 0];"
                "print(p['works']['unique_roads'])"
            ),
        },
    ]


def parking_figure(curve, text):
    works = curve["trip_packages"][curve["recommended_stop"] or 0]["works"]
    return {
        "id": "F23",
        "spec": "spec 16",
        "label": "Parking spaces removed in the known subset",
        "value": works["parking_spaces"]["removed"]["known_subtotal"],
        "unit": "vehicle spaces",
        "inputs": [{"name": "frontier.json", "sha256": hashlib.sha256(text.encode()).hexdigest()}],
        "sources": [
            {
                "name": "Saved fit estimates or sourced bay inventory",
                "licence": "See snapshot sources",
                "request": "Works catalog parking records",
            }
        ],
        "method": (
            "I sum removed vehicle spaces once per selected physical link with a known loss. "
            "Unknown locations stay listed; a known subtotal is not complete inventory. "
            "Local losses remain beside additions and net change."
        ),
        "recipe": (
            "import json;d=json.load(open('frontier.json'));"
            "c=next(c for c in d['scenarios'] if c['id']==d['default']);"
            "w=c['trip_packages'][c['recommended_stop'] or 0]['works'];"
            "print(sum(c['works_catalog'][k]['parking_spaces']['removed'] "
            "for k in set(w['element_ids']) if "
            "c['works_catalog'][k]['parking_spaces']['removed'] is not None))"
        ),
    }
