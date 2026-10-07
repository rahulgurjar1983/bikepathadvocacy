import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from scipy.sparse import coo_array
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from bikeplan.network import boundary_centre, utm_crs

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
