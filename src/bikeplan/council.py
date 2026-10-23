import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
import yaml
from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform

from bikeplan.config import Network
from bikeplan.corridors import NONE_INSIDE, edge_shape, link_all_ages, verdict_of
from bikeplan.options import link_id
from bikeplan.paths_today import suburb_points

REFERENCES = Path(__file__).resolve().parents[2] / "references"
PLAN_FIELDS = (
    "title",
    "document",
    "publisher",
    "url",
    "sha256",
    "read_on",
    "id_field",
    "name_field",
)
WARD_FIELDS = (
    "title",
    "publisher",
    "read_on",
    "sha256_of_download",
    "licence",
    "credit",
    "name_field",
)
STAGE_STEPS = (0, 1, -1)
PLACE_KEYS = {"school": "schools", "station": "stations", "town_centre": "centres"}
TOP_STREETS = 3


class CouncilError(Exception):
    pass


@dataclass(frozen=True)
class PlanRoute:
    id: str
    name: str
    shape: object


@dataclass(frozen=True)
class Plan:
    source: dict
    routes: list


@dataclass(frozen=True)
class Area:
    name: str
    shape: object


@dataclass(frozen=True)
class Wards:
    source: dict
    areas: list


@dataclass(frozen=True)
class Route:
    id: str
    name: str
    shape: object


def read_pair(region_id: str, kind: str, fields: tuple, folder: Path):
    data = folder / f"{region_id}-{kind}.geojson"
    if not data.is_file():
        return None
    side = folder / f"{region_id}-{kind}.yaml"
    try:
        raw = yaml.safe_load(side.read_text())
        features = json.loads(data.read_text())["features"]
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        raise CouncilError(f"{data}: cannot read: {error}") from error
    if not isinstance(raw, dict):
        raise CouncilError(f"{side}: must be a mapping")
    for name in fields:
        if not raw.get(name):
            raise CouncilError(f"{side}: missing {name}")
    return {name: str(raw[name]) for name in fields}, raw, features


def load_plan(region_id: str, folder: str | Path = REFERENCES) -> Plan | None:
    found = read_pair(region_id, "council-plan", PLAN_FIELDS, Path(folder))
    if found is None:
        return None
    source, raw, features = found
    routes = [
        PlanRoute(
            str(item["properties"][raw["id_field"]]),
            str(item["properties"][raw["name_field"]]),
            shape(item["geometry"]),
        )
        for item in features
    ]
    if raw.get("published"):
        source["published"] = str(raw["published"])
    return Plan(source, routes)


def load_wards(region_id: str, folder: str | Path = REFERENCES) -> Wards | None:
    found = read_pair(region_id, "wards", WARD_FIELDS, Path(folder))
    if found is None:
        return None
    source, raw, features = found
    areas = [
        Area(str(item["properties"][raw["name_field"]]), shape(item["geometry"]))
        for item in features
    ]
    return Wards(source, sorted(areas, key=lambda area: area.name))


def to_metres(crs):
    return Transformer.from_crs(4326, crs, always_xy=True).transform


def plan_routes(plan: Plan, crs, boundary) -> list[Route]:
    project = to_metres(crs)
    return [
        Route(item.id, item.name, transform(project, item.shape).intersection(boundary))
        for item in plan.routes
    ]


def link_key(graph, link: tuple):
    a, b, k = link
    return next((key for key in ((a, b, k), (b, a, k)) if graph.has_edge(*key)), None)


def link_shape(graph, link: tuple):
    key = link_key(graph, link)
    return None if key is None else edge_shape(graph, key[0], key[1], graph.edges[key])


def plan_links(graph, routes: list, network: Network) -> set:
    union = shapely.union_all([route.shape for route in routes])
    if union.is_empty:
        return set()
    keys = [
        (u, v, k)
        for u, v, k, data in graph.edges(keys=True, data=True)
        if data["bike_ok"] and u != v
    ]
    shapes = np.array(
        [edge_shape(graph, u, v, graph.edges[u, v, k]) for u, v, k in keys], dtype=object
    )
    hits = shapely.STRtree(shapes).query(
        union, predicate="dwithin", distance=network.corridor_match_m
    )
    return {link_id(*keys[index]) for index in hits}


def pick_shape(option: dict):
    return shapely.union_all(
        [LineString(zip(flat[0::2], flat[1::2], strict=True)) for flat in option["links"]]
    )


def mended_links(option: dict, steps) -> set:
    return {
        link
        for step in steps
        for index in step["works"]
        for link in option["works"][index]["links"]
    }


def covered_length(route, links: set, graph, match: float) -> float:
    shapes = [found for found in (link_shape(graph, link) for link in links) if found is not None]
    if not shapes:
        return 0.0
    return route.intersection(shapely.union_all(shapes).buffer(match)).length / 1000


def council_fit(
    graph, routes: list, ratings: dict, option: dict, choice: dict, network: Network
) -> dict:
    match = network.corridor_match_m
    pick = pick_shape(option).buffer(match)
    near = plan_links(graph, routes, network)
    today = {link for link in near if link_all_ages(ratings, link_key(graph, link))}
    steps = option["steps"]
    first = today | (mended_links(option, steps[1 : choice["step"] + 1]) & near)
    full = today | (mended_links(option, steps[1:]) & near)
    rows = []
    for route in routes:
        inside = route.shape.length
        close = route.shape.intersection(pick).length
        rows.append(
            {
                "id": route.id,
                "name": route.name,
                "km": inside / 1000,
                "near_km": close / 1000,
                "share": close / inside if inside else 0.0,
                "all_ages_km": covered_length(route.shape, today, graph, match),
                "first_km": covered_length(route.shape, first, graph, match),
                "full_km": covered_length(route.shape, full, graph, match),
                "verdict": verdict_of(close, inside, network) if inside else NONE_INSIDE,
            }
        )
    total = sum(row["km"] for row in rows)
    close = sum(row["near_km"] for row in rows)
    plan = shapely.union_all([route.shape for route in routes]).buffer(match)
    return {
        "routes": rows,
        "km": total,
        "near_km": close,
        "share": close / total if total else 0.0,
        "off_km": pick_shape(option).difference(plan).length / 1000,
        "counts": {
            name: sum(row["verdict"] == name for row in rows)
            for name in ("covered", "partly", "missed")
        },
    }


def shape_lines(shape) -> list:
    parts = getattr(shape, "geoms", [shape])
    return [
        [[round(x, 5), round(y, 5)] for x, y in part.coords]
        for part in parts
        if part.geom_type == "LineString" and not part.is_empty
    ]


def council_report(
    graph, plan: Plan, ratings: dict, option: dict, choice: dict, network: Network
) -> dict:
    routes = plan_routes(plan, graph.graph["crs"], graph.graph["boundary"])
    found = council_fit(graph, routes, ratings, option, choice, network)
    to_lonlat = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True).transform
    for row, route in zip(found["routes"], routes, strict=True):
        row["lines"] = shape_lines(transform(to_lonlat, route.shape))
    return {"source": plan.source, **found}


def compact_council(found: dict) -> dict:
    return found | {
        "routes": [{k: v for k, v in row.items() if k != "lines"} for row in found["routes"]]
    }


def ward_fit(graph, areas: list, option: dict, places: list, suburbs: list) -> list[dict]:
    pick = pick_shape(option)
    works = option["works"]
    shapes = [
        [
            found
            for found in (link_shape(graph, link) for link in item["links"])
            if found is not None
        ]
        for item in works
    ]
    steps = option["steps"]
    stages = []
    if all("served" in step.get("totals", {}) for step in steps):
        stages = [
            set(steps[min(index, len(steps) - 1)]["totals"]["served"])
            for index in STAGE_STEPS
            if steps
        ]
    rows = []
    for name, area in areas:
        parts = {}
        for index, found in enumerate(shapes):
            total = sum(line.length for line in found)
            inside = sum(line.intersection(area).length for line in found)
            if total and inside:
                parts[index] = inside / total
        streets: dict = {}
        for index, fraction in parts.items():
            item = works[index]
            street = item["street"]
            if not item.get("spot") and street and not street.lower().startswith("unnamed"):
                streets[street] = streets.get(street, 0.0) + item["km"] * fraction
        top = sorted(streets, key=lambda street: (-streets[street], street))[:TOP_STREETS]
        counts = dict.fromkeys(PLACE_KEYS.values(), 0)
        safe = {key: [0] * len(stages) for key in PLACE_KEYS.values()}
        for kind, point, *ident in places:
            if kind in PLACE_KEYS and area.contains(point):
                counts[PLACE_KEYS[kind]] += 1
                for number, served in enumerate(stages):
                    safe[PLACE_KEYS[kind]][number] += bool(ident) and ident[0] in served
        rows.append(
            {
                "name": name,
                "plan_km": pick.intersection(area).length / 1000,
                "works_km": sum(
                    works[index]["km"] * fraction
                    for index, fraction in parts.items()
                    if not works[index].get("spot")
                ),
                "park": sum(
                    works[index]["parking_spaces"] * fraction for index, fraction in parts.items()
                ),
                **counts,
                **({"safe": safe} if stages else {}),
                "top": top,
                "parts": parts,
                "subs": sorted({sub for sub, point in suburbs if area.contains(point)}),
            }
        )
    owner = {}
    for index, item in enumerate(works):
        if not item.get("spot") or not shapes[index]:
            continue
        line = shapely.union_all(shapes[index])
        owner[index] = min(
            range(len(rows)),
            key=lambda number: (
                -rows[number]["parts"].get(index, 0.0),
                areas[number][1].distance(line),
                number,
            ),
        )
    for number, row in enumerate(rows):
        row["spots"] = sorted(index for index, found in owner.items() if found == number)
    return rows


def polygons(area) -> list:
    return [
        [
            [[round(x, 5), round(y, 5)] for x, y in ring.coords]
            for ring in (part.exterior, *part.interiors)
        ]
        for part in getattr(area, "geoms", [area])
    ]


def ward_report(graph, wards: Wards, option: dict, marks: list, snapshot) -> dict:
    project = to_metres(graph.graph["crs"])
    areas = [(item.name, transform(project, item.shape)) for item in wards.areas]
    places = [
        (mark["type"], Point(*project(mark["lon"], mark["lat"])), mark.get("id")) for mark in marks
    ]
    suburbs = suburb_points(
        Path(snapshot), Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
    )
    rows = ward_fit(graph, areas, option, places, suburbs)
    for row, item in zip(rows, wards.areas, strict=True):
        row["poly"] = polygons(item.shape)
        point = item.shape.representative_point()
        row["at"] = [round(point.x, 5), round(point.y, 5)]
    return {"source": wards.source, "areas": rows}


def compact_wards(found: dict) -> dict:
    keep = ("name", "plan_km", "works_km", "park", "schools", "stations", "centres", "top")
    return {
        "source": found["source"],
        "areas": [
            {key: row[key] for key in keep + (("safe",) if "safe" in row else ())}
            | {"spots": len(row["spots"])}
            for row in found["areas"]
        ],
    }
