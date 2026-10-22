import json
from pathlib import Path

from pyproj import Transformer
from shapely import prepare
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from bikeplan.access import in_scope_places, places, population_units
from bikeplan.config import Profile, Region, load_profile
from bikeplan.network import build
from bikeplan.options import is_unpaved
from bikeplan.review import LEVELS, facility_class, route_figures
from bikeplan.route import Section, match_route, read_route
from bikeplan.stress import score_edges

REACH_M = (500, 1000)
SCHOOL_M = 100


def people_reach(units: list[dict], lines: list[LineString], boundary) -> dict:
    network = unary_union(lines)
    prepare(boundary)
    total = 0.0
    near = dict.fromkeys(REACH_M, 0.0)
    for unit in units:
        centre = unit["polygon"].centroid
        if not boundary.contains(centre):
            continue
        total += unit["people"]
        distance = network.distance(centre)
        for metres in REACH_M:
            if distance <= metres:
                near[metres] += unit["people"]
    return {
        "people": total,
        **{f"within_{m}_m": near[m] / total if total else None for m in REACH_M},
    }


def schools_near(schools: list[tuple[float, float]], lines: list[LineString]) -> dict:
    network = unary_union(lines)
    close = sum(Point(x, y).distance(network) <= SCHOOL_M for x, y in schools)
    return {"schools": len(schools), f"within_{SCHOOL_M}_m": close}


def graph_measures(graph, profile: Profile, sections: list[Section]) -> dict:
    scores = score_edges(graph, profile)
    route_m = paved_m = unpaved_m = 0.0
    shared = dict.fromkeys(LEVELS, 0.0)
    for section in sections:
        match = match_route(graph, section.points)
        route_m += match.length_m
        for key in match.edges:
            data = graph.edges[key]
            km = data["length_m"] / 1000
            if is_unpaved(data):
                unpaved_m += km
            elif facility_class(data) == "separated":
                paved_m += km
            if facility_class(data) == "shared":
                shared[str(scores[key]["lts"])] += km
    route_km = route_m / 1000
    return {
        "route_km": round(route_km, 4),
        "paved_offroad_km": round(paved_m, 4),
        "paved_offroad_share": round(paved_m / route_km, 4) if route_km else None,
        "unpaved_km": round(unpaved_m, 4),
        "shared_street_km_by_lts": {k: round(v, 4) for k, v in shared.items()},
        "crossings_unsignalised": route_figures(graph, profile, sections)["total"][
            "crossings_unsignalised"
        ],
    }


def route_measures(route, region: Region, snapshot) -> dict:
    profile = load_profile(region.profile, "profiles")
    graph = build(snapshot, region, profile)
    sections = read_route(route)
    crs = graph.graph["crs"]
    to_metres = Transformer.from_crs(4326, crs, always_xy=True)
    lines = [LineString(to_metres.itransform(s.points)) for s in sections]
    boundary = graph.graph["boundary"]
    found = places(snapshot)
    for place in found:
        place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
    schools = [
        (p["x"], p["y"]) for p in in_scope_places(found, boundary, 0) if p["type"] == "school"
    ]
    return {
        **graph_measures(graph, profile, sections),
        "people": people_reach(population_units(snapshot, crs), lines, boundary),
        "schools": schools_near(schools, lines),
    }


def write_route_measures(route, region: Region, snapshot, out) -> Path:
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "measures.json"
    path.write_text(
        json.dumps(route_measures(route, region, snapshot), indent=2, sort_keys=True) + "\n"
    )
    return path
