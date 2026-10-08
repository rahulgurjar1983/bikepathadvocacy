import json
from itertools import pairwise
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from bikeplan.config import Profile, Region, load_profile
from bikeplan.network import build, first
from bikeplan.route import Section, match_route, read_route
from bikeplan.stress import (
    OFF_ROAD_FACILITIES,
    crossing_lts,
    is_shared_path,
    junction_legs,
    junction_points,
    main_street,
    score_edges,
)

GATE_RADIUS_M = 5.0
NOT_PUBLIC = {
    "private",
    "customers",
    "permit",
    "delivery",
    "agricultural",
    "forestry",
    "military",
    "no",
}
FACILITIES = ("separated", "painted", "shared", "off_network")
LEVELS = ("1", "2", "3", "4")


def edge_line(graph, key) -> LineString:
    u, v, _ = key
    geometry = graph.edges[key].get("geometry")
    if geometry is not None:
        return geometry
    return LineString([(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in (u, v)])


def facility_class(data: dict) -> str:
    if data["bike_facility"] in OFF_ROAD_FACILITIES or is_shared_path(data):
        return "separated"
    return "painted" if data["bike_facility"] == "painted_lane" else "shared"


def access_tags(data: dict) -> list[str]:
    tags = []
    if data.get("opening_hours"):
        tags.append(f"opening_hours={first(data['opening_hours'])}")
    for key in ("access", "bicycle"):
        if first(data.get(key)) in NOT_PUBLIC:
            tags.append(f"{key}={first(data[key])}")
    return tags


def gate_tags(gates: list[dict], tree: STRtree, geometry: LineString) -> list[str]:
    tags = []
    for index in sorted(tree.query(geometry.buffer(GATE_RADIUS_M))):
        gate = gates[index]
        if Point(gate["x"], gate["y"]).distance(geometry) > GATE_RADIUS_M:
            continue
        text = f"barrier={gate['barrier']}"
        tags.append(f"{text} access={gate['access']}" if gate["access"] else text)
    return tags


def crossing_at(graph, node, keys, flags) -> dict | None:
    legs = junction_legs(graph, node)
    main = main_street(legs)
    if main is None:
        return None
    route_legs = [leg for leg in legs if leg["keys"] & set(keys)]
    if all(any(leg is street for street in main) for leg in route_legs):
        return None
    lanes = max(leg["data"]["lanes_total"] for leg in main)
    speed = max(leg["data"]["speed_kmh"] for leg in main)
    signal, refuge = flags[node]["signal"], flags[node]["refuge"]
    names = [first(leg["data"].get("name")) or first(leg["data"].get("highway")) for leg in main]
    return {
        "junction": node,
        "road": next(name for name in names if name),
        "lts": 1 if signal else crossing_lts(speed, lanes, refuge),
        "signal": signal,
        "refuge": refuge,
    }


def section_figures(graph, scores, flags, gates, tree, to_lonlat, section: Section) -> dict:
    match = match_route(graph, section.points)
    crs_line = LineString(
        Transformer.from_crs(4326, graph.graph["crs"], always_xy=True).itransform(section.points)
    )

    def place(x, y):
        lon, lat = to_lonlat.transform(x, y)
        return [round(lon, 6), round(lat, 6)]

    items = []
    km_facility = dict.fromkeys(FACILITIES, 0.0)
    km_lts = dict.fromkeys(LEVELS, 0.0)
    km_aaa = 0.0
    found_flags = []
    for key in match.edges:
        data = graph.edges[key]
        geometry = edge_line(graph, key)
        score = scores[key]
        km = data["length_m"] / 1000
        km_facility[facility_class(data)] += km
        km_lts[str(score["lts"])] += km
        km_aaa += km * score["aaa"]
        items.append(
            {
                "at": crs_line.project(geometry.interpolate(0.5, normalized=True)),
                "length_m": data["length_m"],
                "aaa": score["aaa"],
                "anchor": geometry.coords[0],
            }
        )
        for tag in access_tags(data) + gate_tags(gates, tree, geometry):
            found_flags.append(
                {
                    "tag": tag,
                    "length_m": round(data["length_m"], 2),
                    "lonlat": place(*geometry.interpolate(0.5, normalized=True).coords[0]),
                }
            )
    for start, end in match.off_stretches:
        km_facility["off_network"] += (end - start) / 1000
        items.append(
            {
                "at": (start + end) / 2,
                "length_m": end - start,
                "aaa": False,
                "anchor": crs_line.interpolate(start).coords[0],
            }
        )
    breaks, run = [], []
    for item in [*sorted(items, key=lambda i: i["at"]), {"aaa": True}]:
        if not item["aaa"]:
            run.append(item)
        elif run:
            breaks.append(
                {
                    "lonlat": place(*run[0]["anchor"]),
                    "length_m": round(sum(i["length_m"] for i in run), 2),
                }
            )
            run = []
    crossings = []
    for first_key, second_key in pairwise(match.edges):
        if first_key[1] != second_key[0]:
            continue
        crossing = crossing_at(graph, first_key[1], (first_key, second_key), flags)
        if crossing:
            node = graph.nodes[first_key[1]]
            crossings.append({**crossing, "lonlat": place(node["x"], node["y"])})
    return {
        "name": section.name,
        "route_km": round(match.length_m / 1000, 4),
        "off_network_km": round(match.off_network_m / 1000, 4),
        "matched_share": round(match.matched_share, 4),
        "km_by_facility": {k: round(v, 4) for k, v in km_facility.items()},
        "km_by_lts": {k: round(v, 4) for k, v in km_lts.items()},
        "km_aaa": round(km_aaa, 4),
        "breaks": breaks,
        "crossings": crossings,
        "crossings_unsignalised": sum(not c["signal"] for c in crossings),
        "flags": found_flags,
    }


def add_up(sections: list[dict]) -> dict:
    route_km = sum(s["route_km"] for s in sections)
    off_km = sum(s["off_network_km"] for s in sections)
    return {
        "route_km": round(route_km, 4),
        "off_network_km": round(off_km, 4),
        "matched_share": round(1 - off_km / route_km, 4),
        "km_by_facility": {
            k: round(sum(s["km_by_facility"][k] for s in sections), 4) for k in FACILITIES
        },
        "km_by_lts": {k: round(sum(s["km_by_lts"][k] for s in sections), 4) for k in LEVELS},
        "km_aaa": round(sum(s["km_aaa"] for s in sections), 4),
        "breaks": [b for s in sections for b in s["breaks"]],
        "crossings": [c for s in sections for c in s["crossings"]],
        "crossings_unsignalised": sum(s["crossings_unsignalised"] for s in sections),
        "flags": [f for s in sections for f in s["flags"]],
    }


def route_figures(graph, profile: Profile, sections: list[Section]) -> dict:
    scores = score_edges(graph, profile)
    flags = junction_points(graph)
    gates = graph.graph.get("gates", [])
    tree = STRtree([Point(g["x"], g["y"]) for g in gates])
    to_lonlat = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    found = [section_figures(graph, scores, flags, gates, tree, to_lonlat, s) for s in sections]
    return {"sections": found, "total": add_up(found)}


def write_route_figures(route, region: Region, snapshot, out) -> Path:
    profile = load_profile(region.profile, "profiles")
    figures = route_figures(build(snapshot, region, profile), profile, read_route(route))
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "route_figures.json"
    path.write_text(json.dumps(figures, indent=2, sort_keys=True) + "\n")
    return path
