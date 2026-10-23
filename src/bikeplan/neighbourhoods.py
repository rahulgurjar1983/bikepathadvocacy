from collections import defaultdict

from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform

from bikeplan.council import load_wards
from bikeplan.parking import parking_totals

TOLERANCE_M = 0.01
OVERLAP_NOTE = (
    "Areas may overlap, so a resident can appear in more than one area. "
    "The region figure is a union, not the sum of the areas."
)
METHOD = (
    "Each link is clipped to the council boundary and its length is split by area geometry; "
    "an overlap goes to the first area by ID. Whole-number parking records follow the area "
    "holding the most of that link, ties to the first area by ID. Crossings, residents and "
    "school sites are located by point. Anything outside every area stays unallocated."
)


def link_geometry(graph, item):
    keys = sorted(item["directed_edges"], key=str)
    key = next((k for k in keys if not graph.edges[tuple(k)].get("reversed")), keys[0])
    u, v, _ = key
    data = graph.edges[tuple(key)]
    line = data.get("geometry") or LineString(
        [(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in (u, v)]
    )
    return graph.graph["boundary"].intersection(line)


def node_point(graph, node):
    data = graph.nodes.get(node) if node is not None else None
    if not data or data.get("x") is None or data.get("y") is None:
        return None
    return Point(data["x"], data["y"])


def first_area(areas, point):
    return next(iter(first_area_all(areas, point)), None)


def allocate_works(areas, graph, catalog, selected):
    pieces = defaultdict(dict)
    unallocated = []
    owner = {}
    for key in selected:
        item = catalog[key]
        if item["kind"] == "crossing":
            end = item["endpoints"][0]
            point = None if end["x"] is None else Point(end["x"], end["y"])
            home = first_area(areas, point)
            if home is None:
                unallocated.append(
                    {
                        "id": key,
                        "length_m": 0.0,
                        "reason": "This crossing lies outside every sourced area",
                    }
                )
            else:
                pieces[home][key] = 0.0
                owner[key] = home
            continue
        remaining = link_geometry(graph, item)
        for area in areas:
            part = remaining.intersection(area["shape"])
            if part.length > TOLERANCE_M:
                pieces[area["id"]][key] = part.length
                remaining = remaining.difference(area["shape"])
        placed = {a: p[key] for a, p in pieces.items() if key in p}
        if not placed:
            unallocated.append(
                {
                    "id": key,
                    "length_m": item["length_m"],
                    "reason": "No part of this work lies inside a sourced area",
                }
            )
        else:
            owner[key] = min(placed, key=lambda a: (-placed[a], a))
            leftover = item["length_m"] - sum(placed.values())
            if leftover > TOLERANCE_M:
                unallocated.append(
                    {
                        "id": key,
                        "length_m": leftover,
                        "reason": "Part of this work lies outside every sourced area",
                    }
                )
    return pieces, unallocated, owner


def route_roles(catalog, selected, witnesses):
    by_edge = {
        tuple(edge): key for key in selected for edge in catalog[key].get("directed_edges", [])
    }
    roles = {key: set() for key in selected}
    for witness in witnesses:
        for direction in ("outbound", "return"):
            for edge in witness[direction]["edges"]:
                key = by_edge.get(tuple(edge))
                if key is not None:
                    roles[key].add(witness["destination"])
    return {key: sorted(value) for key, value in roles.items()}


def resident_keys(residents, label):
    strict = residents["strict"]
    if strict.get("membership") is None:
        return None
    return {(i["unit"], i["node"]): i["people"] for i in strict["membership"].get(label, [])}


def resident_block(graph, areas, residents):
    after = resident_keys(residents, "after")
    gained = resident_keys(residents, "newly_gained")
    if after is None:
        return None
    homes = {key: first_area_all(areas, node_point(graph, key[1])) for key in {*after, *gained}}
    return after, gained or {}, homes


def first_area_all(areas, point):
    return [a["id"] for a in areas if point is not None and a["shape"].covers(point)]


def people(keys, homes, area=None):
    if area is None:
        return sum(value for key, value in keys.items() if not homes.get(key))
    return sum(value for key, value in keys.items() if area in homes.get(key, []))


def neighbourhood_report(areas, graph, catalog, works, residents, schools, witnesses=()):
    areas = sorted(areas, key=lambda a: a["id"])
    selected = sorted(works["element_ids"])
    pieces, unallocated, owner = allocate_works(areas, graph, catalog, selected)
    roles = route_roles(catalog, selected, witnesses)
    block = resident_block(graph, areas, residents)
    located = {}
    for site in schools["sites"]:
        nodes = [n for n in site.get("model_nodes", []) if n is not None]
        located[site["id"]] = first_area_all(areas, node_point(graph, nodes[0])) if nodes else []
    served = schools["served"]
    rows, links = [], {}
    for area in areas:
        mine = sorted(k for k, a in owner.items() if a == area["id"])
        parking = parking_totals(catalog, mine)
        in_area = sorted(s for s, found in located.items() if area["id"] in found)
        school = {
            "served_after": [s for s in in_area if s in served["after"]],
            "newly_served": [s for s in in_area if s in served["new"]],
            "not_served": [s for s in in_area if s not in served["after"]],
        }
        resident = (
            {
                "after": people(block[0], block[2], area["id"]),
                "newly_gained": people(block[1], block[2], area["id"]),
            }
            if block
            else {"after": None, "newly_gained": None}
        )
        piece = pieces.get(area["id"], {})
        linked = sorted(piece)
        links[area["id"]] = linked
        removed = parking["removed"]["known_subtotal"]
        impact = removed > 0 or any(
            catalog[k].get("turn_changes") or catalog[k].get("access_changes") for k in linked
        )
        benefit = bool(school["newly_served"]) or bool(resident["newly_gained"])
        rows.append(
            {
                "id": area["id"],
                "name": area["name"],
                "works": {
                    "length_m": sum(piece.values()),
                    "pieces": dict(sorted(piece.items())),
                    "parking_element_ids": mine,
                    "routes": {k: roles[k] for k in linked},
                },
                "parking_spaces": parking,
                "schools": school,
                "residents": resident,
                "access_effects": [
                    k
                    for k in linked
                    if catalog[k].get("turn_changes") or catalog[k].get("access_changes")
                ],
                "survey_needs": sorted(
                    {n for k in linked for n in catalog[k].get("survey_needs", [])}
                ),
                "pattern": "benefit_and_impact"
                if benefit and impact
                else "benefit_only"
                if benefit
                else "impact_only"
                if impact
                else "none",
            }
        )
    return {
        "areas": rows,
        "links": links,
        "unallocated": {
            "works": sorted(unallocated, key=lambda item: item["id"]),
            "parking_spaces": parking_totals(catalog, sorted(set(selected) - set(owner))),
            "residents": {
                "after": people(block[0], block[2]) if block else None,
                "newly_gained": people(block[1], block[2]) if block else None,
            },
            "schools": sorted(s for s, found in located.items() if not found),
        },
        "region": {
            "works_length_m": sum(
                catalog[k]["length_m"] for k in selected if "length_m" in catalog[k]
            ),
            "residents": {
                "after": sum(block[0].values()) if block else None,
                "newly_gained": sum(block[1].values()) if block else None,
                "located_after": sum(block[0].values()) - people(block[0], block[2])
                if block
                else None,
                "located_newly_gained": sum(block[1].values()) - people(block[1], block[2])
                if block
                else None,
                "overlap_note": OVERLAP_NOTE,
            },
            "schools": {
                "served_after": len(served["after"]),
                "newly_served": len(served["new"]),
            },
        },
        "area_sources": [{"id": a["id"], "name": a["name"]} for a in areas],
        "method": METHOD,
        "evidence_status": "modelled",
    }


def verify_neighbourhoods(result, catalog, works):
    selected = sorted(works["element_ids"])
    owners = [k for row in result["areas"] for k in row["works"]["parking_element_ids"]]
    loose = sorted(set(selected) - set(owners))
    if len(owners) != len(set(owners)) or set(owners) - set(selected):
        raise ValueError("A work is allocated to more than one area or is not in the package")
    for row in result["areas"]:
        if abs(row["works"]["length_m"] - sum(row["works"]["pieces"].values())) > TOLERANCE_M:
            raise ValueError("Area work length differs from its pieces")
        if row["parking_spaces"] != parking_totals(catalog, row["works"]["parking_element_ids"]):
            raise ValueError("Area parking totals differ")
    if result["unallocated"]["parking_spaces"] != parking_totals(catalog, loose):
        raise ValueError("Unallocated parking totals differ")
    if not set(loose) <= {item["id"] for item in result["unallocated"]["works"]}:
        raise ValueError("Unallocated works differ")
    for key in selected:
        item = catalog[key]
        if item["kind"] != "link":
            continue
        placed = sum(row["works"]["pieces"].get(key, 0) for row in result["areas"])
        rest = sum(u["length_m"] for u in result["unallocated"]["works"] if u["id"] == key)
        if abs(placed + rest - item["length_m"]) > TOLERANCE_M:
            raise ValueError("A work is not allocated once across areas and the unallocated list")
    region = result["region"]["residents"]
    if region["newly_gained"] is not None:
        rest = result["unallocated"]["residents"]
        areas = [row["residents"]["newly_gained"] for row in result["areas"]]
        if region["newly_gained"] != region["located_newly_gained"] + rest["newly_gained"]:
            raise ValueError("Region residents differ from located and unallocated residents")
        if not max(areas, default=0) <= region["located_newly_gained"] <= sum(areas):
            raise ValueError("Located residents differ from the area unions")


def slug(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def area_inputs(region_id, crs, metadata):
    project = Transformer.from_crs(4326, crs, always_xy=True).transform
    rows = ((metadata or {}).get("contents") or {}).get("areas") or []
    if rows:
        found = [
            {"id": r["id"], "name": r["name"], "shape": transform(project, shape(r["geometry"]))}
            for r in rows
        ]
        sources = [{"id": r["id"], "source": r["source"], "date": r["date"]} for r in rows]
        kind = "proposal_inputs"
    else:
        wards = load_wards(region_id)
        if wards is None:
            return [], None
        found = [
            {"id": f"ward:{slug(a.name)}", "name": a.name, "shape": transform(project, a.shape)}
            for a in wards.areas
        ]
        sources = [{"id": f"ward:{slug(a.name)}", **wards.source} for a in wards.areas]
        kind = "council_wards"
    return sorted(found, key=lambda a: a["id"]), {
        "kind": kind,
        "areas": sorted(sources, key=lambda a: a["id"]),
    }


def package_areas(areas, source, graph, catalog, package):
    report = neighbourhood_report(
        areas,
        graph,
        catalog,
        package["works"],
        package["resident_outcomes"],
        package["school_coverage"],
        package["strict"],
    )
    by_id = {item["id"]: item for item in source["areas"]}
    report["area_sources"] = [
        {**item, **by_id[item["id"]], "boundary_kind": source["kind"]}
        for item in report["area_sources"]
    ]
    return report
