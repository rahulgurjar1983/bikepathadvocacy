import gzip
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, transform, unary_union

from bikeplan.network import boundary_centre, boundary_polygon, utm_crs

PATH_HIGHWAYS = ("path", "footway", "pedestrian", "bridleway", "track")
BIKE_YES = ("designated", "yes", "permissive")
CYCLEWAY_KEYS = ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")
TOUCH_M = 3
PICK_M = 15
STREET_M = 200
SUBURBS = ("suburb", "locality")
LEAD = {"path": "Path", "lane": "Lane"}


def way_kind(tags: dict) -> str | None:
    sides = {tags.get(key) for key in CYCLEWAY_KEYS}
    highway = tags.get("highway")
    if highway == "cycleway" or "track" in sides:
        return "path"
    if highway in PATH_HIGHWAYS and tags.get("bicycle") in BIKE_YES:
        return "path"
    if sides & {"lane", "share_busway"}:
        return "lane"
    return None


def read_ways(snapshot: Path, to_utm: Transformer) -> tuple[list[dict], list[dict]]:
    points: dict = {}
    ways = []
    with gzip.open(snapshot / "network.osm.gz") as handle:
        for _, element in ET.iterparse(handle):
            if element.tag == "node":
                points[element.get("id")] = (float(element.get("lon")), float(element.get("lat")))
            elif element.tag == "way":
                tags = {tag.get("k"): tag.get("v") for tag in element.iter("tag")}
                refs = [ref.get("ref") for ref in element.iter("nd")]
                if "highway" in tags and all(ref in points for ref in refs) and len(refs) > 1:
                    line = LineString([points[ref] for ref in refs])
                    ways.append(
                        {
                            "id": int(element.get("id")),
                            "name": tags.get("name", ""),
                            "kind": way_kind(tags),
                            "line": transform(to_utm.transform, line),
                        }
                    )
            if element.tag in ("node", "way"):
                element.clear()
    ways.sort(key=lambda way: way["id"])
    streets = [way for way in ways if way["name"] and way["kind"] is None]
    return ways, streets


def suburb_points(snapshot: Path, to_utm: Transformer) -> list[tuple[str, Point]]:
    path = snapshot / "places.json"
    if not path.is_file():
        return []
    found = []
    for element in json.loads(path.read_text()).get("elements", []):
        tags = element.get("tags", {})
        point = element if "lat" in element else element.get("center")
        if tags.get("place") in SUBURBS and tags.get("name") and point:
            found.append((tags["name"], Point(*to_utm.transform(point["lon"], point["lat"]))))
    return sorted(found, key=lambda item: (item[0], item[1].x, item[1].y))


def clip(ways: list[dict], boundary) -> list[dict]:
    pieces = []
    for way in ways:
        inside = way["line"].intersection(boundary)
        for part in getattr(inside, "geoms", [inside]):
            if isinstance(part, LineString) and not part.is_empty and part.length > 0:
                pieces.append({**way, "line": part})
    return pieces


def groups(pieces: list[dict]) -> list[list[dict]]:
    parent = list(range(len(pieces)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    tree = STRtree([piece["line"] for piece in pieces])
    for index, piece in enumerate(pieces):
        for other in tree.query(piece["line"], predicate="dwithin", distance=TOUCH_M):
            parent[find(int(other))] = find(index)
    merged: dict = {}
    for index, piece in enumerate(pieces):
        merged.setdefault(find(index), []).append(piece)
    return list(merged.values())


def nearest_name(geometry, candidates: list[tuple[str, object]], reach: float) -> str | None:
    best = None
    for name, shape in candidates:
        distance = geometry.distance(shape)
        if distance <= reach and (best is None or (distance, name) < best):
            best = (distance, name)
    return best[1] if best else None


def merged_lines(pieces: list[dict]):
    lines = sorted((piece["line"] for piece in pieces), key=lambda line: list(line.coords))
    joined = linemerge(lines)
    return list(getattr(joined, "geoms", [joined]))


def far_ends(lines: list) -> tuple:
    ends = np.array([point for line in lines for point in (line.coords[0], line.coords[-1])])
    gaps = np.hypot(*(ends[:, None, :] - ends[None, :, :]).transpose(2, 0, 1))
    first, second = np.unravel_index(int(np.argmax(gaps)), gaps.shape)
    return tuple(sorted((tuple(ends[first]), tuple(ends[second]))))


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def build_items(
    kind, pieces, boundary_streets, suburbs, pick, to_lonlat, area: str, taken: set
) -> list[dict]:
    named: dict = {}
    for piece in pieces:
        if piece["name"]:
            named.setdefault(piece["name"], []).append(piece)
    by_name = {name: list(found) for name, found in named.items()}
    km_of = {name: sum(p["line"].length for p in found) for name, found in named.items()}
    shapes = {name: unary_union([p["line"] for p in found]) for name, found in named.items()}
    unnamed = [piece for piece in pieces if not piece["name"]]
    for group in groups(unnamed) if unnamed else []:
        shape = unary_union([piece["line"] for piece in group])
        touched = {name: km_of[name] for name in named if shapes[name].distance(shape) <= TOUCH_M}
        if touched:
            name = min(touched, key=lambda found: (-touched[found], found))
            by_name[name].extend(group)
            continue
        longest = max(group, key=lambda piece: (piece["line"].length, piece["id"]))
        middle = longest["line"].interpolate(0.5, normalized=True)
        street = nearest_name(
            middle,
            [(way["name"], way["line"]) for way in boundary_streets],
            STREET_M,
        )
        if street:
            name = f"{LEAD[kind]} by {street}"
        else:
            suburb = nearest_name(middle, suburbs, float("inf"))
            name = f"{LEAD[kind]} in {suburb or area}"
        by_name.setdefault(name, []).extend(group)
    items = []
    for name, found in by_name.items():
        lines = merged_lines(found)
        whole = unary_union(lines)
        metres = whole.length
        longest = max(found, key=lambda piece: (piece["line"].length, piece["id"]))
        middle = longest["line"].interpolate(0.5, normalized=True)
        on_pick = whole.intersection(pick).length if pick is not None else 0.0
        first, second = far_ends(lines)

        def lat_lon(point):
            lon, lat = to_lonlat.transform(point[0], point[1])
            return [round(lat, 5), round(lon, 5)]

        item_id = f"{kind}-{slug(name)}"
        while item_id in taken:
            item_id += "-2"
        taken.add(item_id)
        items.append(
            {
                "id": item_id,
                "name": name,
                "kind": kind,
                "km": round(metres / 1000, 3),
                "on_pick": round(on_pick / 1000, 3),
                "share": round(on_pick / metres, 3) if metres else 0.0,
                "mid": lat_lon((middle.x, middle.y)),
                "ends": [lat_lon(first), lat_lon(second)],
                "lines": [[lat_lon(point) for point in line.coords] for line in lines],
            }
        )
    return items


def read_paths(snapshot: str | Path, pick_lines: list, area: str = "this area") -> list[dict]:
    folder = Path(snapshot)
    crs = utm_crs(*boundary_centre(folder / "boundary.geojson"))
    to_utm = Transformer.from_crs(4326, crs, always_xy=True)
    to_lonlat = Transformer.from_crs(crs, 4326, always_xy=True)
    boundary = boundary_polygon(folder / "boundary.geojson", crs)
    ways, streets = read_ways(folder, to_utm)
    pick = None
    if pick_lines:
        lines = [
            transform(to_utm.transform, LineString(line)) for line in pick_lines if len(line) > 1
        ]
        pick = unary_union(lines).buffer(PICK_M) if lines else None
    suburbs = suburb_points(folder, to_utm)
    boundary_streets = [way for way in clip(streets, boundary.buffer(STREET_M)) if way["name"]]
    taken: set = set()
    items = []
    for kind in ("path", "lane"):
        pieces = clip([way for way in ways if way["kind"] == kind], boundary)
        if pieces:
            items += build_items(
                kind, pieces, boundary_streets, suburbs, pick, to_lonlat, area, taken
            )
    return sorted(items, key=lambda item: (item["kind"] != "path", -item["km"], item["name"]))
