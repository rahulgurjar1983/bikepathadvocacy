import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import numpy as np
import shapely
from pyproj import Transformer
from scipy.sparse import coo_array
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon

from bikeplan.network import boundary_centre, utm_crs
from bikeplan.snapshot import gpkg_rings

DUPLICATE_RADIUS_M = 50.0
SHOP_JOIN_M = 150.0
CENTRE_MIN_SHOPS = 10
STATION_TAGS = (
    ("railway", "station"),
    ("railway", "halt"),
    ("public_transport", "station"),
    ("amenity", "ferry_terminal"),
    ("railway", "tram_stop"),
)
AMENITY_TYPES = {
    "school": "school",
    "college": "college",
    "university": "university",
    "nursing_home": "aged_care",
    "library": "library",
}
SNAP_M = 300.0
HOME_HIGHWAYS = {"residential", "living_street", "unclassified"}
AGED_CARE_KINDS = {"nursing_home", "assisted_living"}


def place_type(tags: dict) -> str | None:
    if tags.get("amenity") in AMENITY_TYPES:
        return AMENITY_TYPES[tags["amenity"]]
    if tags.get("amenity") == "social_facility" and (
        tags.get("social_facility") in AGED_CARE_KINDS
        or tags.get("social_facility:for") == "senior"
    ):
        return "aged_care"
    if any(tags.get(key) == value for key, value in STATION_TAGS):
        return "station"
    return None


def element_point(element: dict) -> tuple[float, float] | None:
    source = element if "lon" in element else element.get("center")
    if not source:
        return None
    return source["lon"], source["lat"]


def sort_key(place: dict) -> tuple[int, str]:
    kind, number = place["osm_id"].split("/")
    return int(number), kind


def read_places(elements: list[dict]) -> tuple[list[dict], list[dict]]:
    found, shops, seen = [], [], set()
    for element in elements:
        point = element_point(element)
        osm_id = f"{element['type']}/{element['id']}"
        if point is None or osm_id in seen:
            continue
        seen.add(osm_id)
        tags = element.get("tags", {})
        place = {
            "type": place_type(tags),
            "name": tags.get("name", ""),
            "osm_id": osm_id,
            "lon": point[0],
            "lat": point[1],
        }
        if place["type"]:
            found.append(place)
        if "shop" in tags:
            shops.append(place)
    return sorted(found, key=sort_key), sorted(shops, key=sort_key)


def project(places: list[dict], transformer: Transformer) -> np.ndarray:
    lons = [place["lon"] for place in places]
    lats = [place["lat"] for place in places]
    return np.column_stack(transformer.transform(lons, lats))


def drop_near_duplicates(found: list[dict], transformer: Transformer) -> list[dict]:
    kept: list[dict] = []
    points: list[np.ndarray] = []
    for place, point in zip(found, project(found, transformer) if found else [], strict=True):
        near = any(
            other["type"] == place["type"]
            and np.hypot(*(point - other_point)) <= DUPLICATE_RADIUS_M
            for other, other_point in zip(kept, points, strict=True)
        )
        if not near:
            kept.append(place)
            points.append(point)
    return kept


def town_centres(shops: list[dict], transformer: Transformer) -> list[dict]:
    if len(shops) < CENTRE_MIN_SHOPS:
        return []
    points = project(shops, transformer)
    pairs = cKDTree(points).query_pairs(np.nextafter(SHOP_JOIN_M, 0), output_type="ndarray")
    links = coo_array(
        (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(shops), len(shops))
    )
    _, labels = connected_components(links, directed=False)
    clusters = [np.flatnonzero(labels == label) for label in np.unique(labels)]
    clusters = [members for members in clusters if len(members) >= CENTRE_MIN_SHOPS]
    clusters.sort(key=lambda members: min(sort_key(shops[index]) for index in members))
    centres = []
    for number, members in enumerate(clusters, 1):
        mean = points[members].mean(axis=0)
        nearest = members[np.argmin(np.hypot(*(points[members] - mean).T))]
        centres.append({**shops[nearest], "type": "town_centre", "name": f"Town centre {number}"})
    return centres


def places(snapshot: str | Path) -> list[dict]:
    folder = Path(snapshot)
    elements = json.loads((folder / "places.json").read_text())["elements"]
    longitude, latitude = boundary_centre(folder / "boundary.geojson")
    transformer = Transformer.from_crs(4326, utm_crs(longitude, latitude), always_xy=True)
    found, shops = read_places(elements)
    return drop_near_duplicates(found, transformer) + town_centres(shops, transformer)


class Homes(NamedTuple):
    people: dict
    unsnapped: float


def highways(data: dict) -> set:
    value = data["highway"]
    return set(value) if isinstance(value, list) else {value}


def bike_nodes(graph) -> tuple[list, list]:
    legal, residential = set(), set()
    for u, v, data in graph.edges(data=True):
        if data["bike_ok"]:
            legal.update((u, v))
            if highways(data) & HOME_HIGHWAYS:
                residential.update((u, v))
    return sorted(legal), residential


def node_tree(graph) -> tuple[list, cKDTree]:
    legal, _ = bike_nodes(graph)
    points = [(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in legal]
    return legal, cKDTree(points)


def snap_points(points: list, graph) -> tuple[list, list]:
    legal, tree = node_tree(graph)
    if not legal or not points:
        return [None] * len(points), list(range(len(points)))
    distances, indices = tree.query(points, distance_upper_bound=SNAP_M)
    nodes = [
        legal[index] if np.isfinite(d) else None
        for d, index in zip(distances, indices, strict=True)
    ]
    return nodes, [number for number, node in enumerate(nodes) if node is None]


def homes(units: list[dict], graph, boundary) -> Homes:
    legal, residential = bike_nodes(graph)
    xs = np.array([graph.nodes[node]["x"] for node in legal])
    ys = np.array([graph.nodes[node]["y"] for node in legal])
    people: dict = defaultdict(float)
    unsnapped = 0.0
    for unit in units:
        centre = unit["polygon"].centroid
        if not boundary.contains(centre):
            continue
        inside = [
            node
            for node, hit in zip(legal, shapely.contains_xy(unit["polygon"], xs, ys), strict=True)
            if hit
        ]
        targets = [node for node in inside if node in residential] or inside
        if not targets:
            nodes, _ = snap_points([(centre.x, centre.y)], graph)
            targets = [node for node in nodes if node is not None]
        if not targets:
            unsnapped += unit["people"]
            continue
        for node in targets:
            people[node] += unit["people"] / len(targets)
    return Homes(dict(people), unsnapped)


def in_scope_places(found: list[dict], boundary, buffer_m: float) -> list[dict]:
    return [
        place for place in found if boundary.distance(Point(place["x"], place["y"])) <= buffer_m
    ]


def population_units(snapshot: str | Path, crs) -> list[dict]:
    transformer = Transformer.from_crs(3857, crs, always_xy=True)
    database = sqlite3.connect(f"file:{Path(snapshot) / 'population.gpkg'}?mode=ro", uri=True)
    try:
        rows = database.execute("select geom, population from population order by h3").fetchall()
    finally:
        database.close()
    units = []
    for blob, count in rows:
        rings = [
            list(zip(*transformer.transform(*zip(*ring, strict=True)), strict=True))
            for ring in gpkg_rings(blob)
        ]
        units.append({"polygon": Polygon(rings[0], rings[1:]), "people": count})
    return units
