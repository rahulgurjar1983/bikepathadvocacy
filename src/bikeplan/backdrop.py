import json
import math
from itertools import pairwise
from pathlib import Path

from shapely import STRtree
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, shape
from shapely.ops import polygonize, unary_union

from bikeplan.snapshot import buffered_box

AREA_TAGS = (
    ("water", "natural", {"water"}),
    ("water", "waterway", {"riverbank"}),
    ("park", "leisure", {"park", "nature_reserve"}),
    ("park", "landuse", {"recreation_ground"}),
    ("air", "aeroway", {"aerodrome"}),
)
RAIL = {"rail", "light_rail"}
SIDE_STEP = 1e-6


def read_elements(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text()).get("elements", [])


def points_of(geometry: list[dict]) -> list[tuple[float, float]]:
    return [(point["lon"], point["lat"]) for point in geometry]


def rounded(polygon: Polygon) -> list:
    rings = [polygon.exterior, *polygon.interiors]
    return [[[round(x, 5), round(y, 5)] for x, y in ring.coords] for ring in rings]


def polygon_list(geometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon) or hasattr(geometry, "geoms"):
        return [part for item in geometry.geoms for part in polygon_list(item)]
    return []


def area_shape(element: dict):
    if element["type"] == "way":
        points = points_of(element.get("geometry", []))
        if len(points) < 4 or points[0] != points[-1]:
            return None
        return Polygon(points).buffer(0)
    members = element.get("members", [])

    def rings(role: str):
        lines = [
            LineString(points_of(member["geometry"]))
            for member in members
            if member.get("role") == role and len(member.get("geometry", [])) > 1
        ]
        return unary_union(list(polygonize(unary_union(lines)))) if lines else Polygon()

    return rings("outer").difference(rings("inner"))


def clipped_polygons(shapes: list, window: Polygon) -> list:
    merged = unary_union([item for item in shapes if item is not None and not item.is_empty])
    return [rounded(part) for part in polygon_list(merged.intersection(window)) if part.area > 0]


def sea_shape(coasts: list[list[tuple[float, float]]], window: Polygon):
    if not coasts:
        return None
    cut = [LineString(coast).intersection(window) for coast in coasts]
    pieces = list(polygonize(unary_union([window.boundary, *cut])))
    tree = STRtree(pieces)
    sea = set()
    for coast in coasts:
        for (x1, y1), (x2, y2) in pairwise(coast):
            scale = math.cos(math.radians((y1 + y2) / 2))
            dx, dy = (x2 - x1) * scale, y2 - y1
            length = math.hypot(dx, dy)
            if not length:
                continue
            probe = Point(
                (x1 + x2) / 2 + dy / length * SIDE_STEP / scale,
                (y1 + y2) / 2 - dx / length * SIDE_STEP,
            )
            sea.update(int(index) for index in tree.query(probe, predicate="within"))
    return unary_union([pieces[index] for index in sorted(sea)]) if sea else None


def backdrop_layers(snapshot: str | Path, boundary: dict, buffer_m: float) -> dict:
    folder = Path(snapshot)
    south, west, north, east = buffered_box(boundary, buffer_m)
    window = box(west, south, east, north)
    geometry = boundary["geometry"] if boundary["type"] == "Feature" else boundary
    land = shape(geometry)
    shapes: dict[str, list] = {"water": [], "park": [], "air": []}
    rail = []
    coasts = []
    for element in read_elements(folder / "backdrop.json"):
        tags = element.get("tags", {})
        if tags.get("natural") == "coastline":
            if element["type"] == "way" and len(element.get("geometry", [])) > 1:
                coasts.append(points_of(element["geometry"]))
            continue
        if element["type"] == "way" and tags.get("railway") in RAIL:
            line = LineString(points_of(element["geometry"])).intersection(window)
            rail.extend(
                [[round(x, 5), round(y, 5)] for x, y in part.coords]
                for part in getattr(line, "geoms", [line])
                if isinstance(part, LineString) and not part.is_empty
            )
            continue
        for layer, key, values in AREA_TAGS:
            if tags.get(key) in values:
                shapes[layer].append(area_shape(element))
    shapes["water"].append(sea_shape(coasts, window))
    layers = {name: clipped_polygons(found, window) for name, found in shapes.items()}
    outside = window.difference(land)
    layers["rail"] = rail
    layers["outside"] = [rounded(part) for part in polygon_list(outside) if part.area > 0]
    return layers
