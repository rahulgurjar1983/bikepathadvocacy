import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import gpxpy
import networkx as nx
import yaml
from mappymatch.constructs.trace import Trace
from mappymatch.maps.nx.nx_map import NxMap
from mappymatch.matchers.lcss.lcss import LCSSMatcher
from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from bikeplan.config import ConfigError, load_region
from bikeplan.network import utm_crs

OFF_NETWORK_M = 30.0
MAX_CORRIDOR_KM2 = 300.0
KML_LINE = "{http://www.opengis.net/kml/2.2}LineString"
KML_PLACEMARK = "{http://www.opengis.net/kml/2.2}Placemark"
KML_NAME = "{http://www.opengis.net/kml/2.2}name"
KML_COORDINATES = "{http://www.opengis.net/kml/2.2}coordinates"
GEOJSON_LINES = {"LineString": 1, "MultiLineString": 2}


class RouteError(Exception):
    pass


@dataclass(frozen=True)
class Section:
    name: str
    points: list[tuple[float, float]]


@dataclass(frozen=True)
class RouteMatch:
    edges: list[tuple]
    length_m: float
    off_network_m: float
    off_stretches: list[tuple[float, float]]
    matched_share: float


def read_gpx(text: str) -> list[Section]:
    gpx = gpxpy.parse(text)
    sections = []
    for number, track in enumerate(gpx.tracks, 1):
        points = [(p.longitude, p.latitude) for s in track.segments for p in s.points]
        sections.append(Section(track.name or f"Track {number}", points))
    for number, route in enumerate(gpx.routes, 1):
        points = [(p.longitude, p.latitude) for p in route.points]
        sections.append(Section(route.name or f"Route {number}", points))
    return sections


def kml_points(text: str) -> list[tuple[float, float]]:
    pairs = (item.split(",") for item in text.split())
    return [(float(pair[0]), float(pair[1])) for pair in pairs]


def read_kml(text: str) -> list[Section]:
    sections = []
    for placemark in ET.fromstring(text).iter(KML_PLACEMARK):
        name = placemark.findtext(KML_NAME) or f"Placemark {len(sections) + 1}"
        for line in placemark.iter(KML_LINE):
            sections.append(Section(name, kml_points(line.findtext(KML_COORDINATES) or "")))
    return sections


def geojson_sections(node: dict, label: str) -> list[Section]:
    kind = node.get("type")
    if kind == "FeatureCollection":
        return [s for f in node["features"] for s in geojson_sections(f, label)]
    if kind == "Feature":
        name = (node.get("properties") or {}).get("name")
        return [
            Section(name or s.name, s.points)
            for s in geojson_sections(node["geometry"] or {}, label)
        ]
    if kind == "LineString":
        return [Section(label, [(p[0], p[1]) for p in node["coordinates"]])]
    if kind == "MultiLineString":
        return [Section(label, [(p[0], p[1]) for p in line]) for line in node["coordinates"]]
    return []


def read_geojson(text: str, label: str) -> list[Section]:
    return geojson_sections(json.loads(text), label)


def read_route(path: str | Path) -> list[Section]:
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        text = path.read_text()
        if suffix == ".gpx":
            sections = read_gpx(text)
        elif suffix == ".kml":
            sections = read_kml(text)
        elif suffix in {".geojson", ".json"}:
            sections = read_geojson(text, path.stem)
        else:
            raise RouteError(f"{path}: not a GPX, KML or GeoJSON file")
    except (OSError, ValueError, KeyError, ET.ParseError, gpxpy.gpx.GPXException) as error:
        raise RouteError(f"{path}: cannot read: {error}") from error
    sections = [s for s in sections if len(s.points) >= 2]
    if not sections:
        raise RouteError(f"{path}: no line found")
    return sections


def bike_map(graph: nx.MultiDiGraph) -> NxMap:
    bike = nx.MultiDiGraph(crs=graph.graph["crs"])
    for u, v, k, data in graph.edges(keys=True, data=True):
        if not data["bike_ok"]:
            continue
        ends = [(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in (u, v)]
        bike.add_edge(u, v, k, geometry=data.get("geometry") or LineString(ends))
    return NxMap(bike)


def off_network(line: LineString, road_map: NxMap) -> list[tuple[float, float]]:
    geometries = [road_map.g.edges[e]["geometry"] for e in road_map.g.edges(keys=True)]
    tree = STRtree(geometries)
    near = tree.query(line.buffer(OFF_NETWORK_M))
    covered = unary_union([geometries[i].buffer(OFF_NETWORK_M) for i in near])
    rest = line.difference(covered)
    pieces = [rest] if rest.geom_type == "LineString" else list(getattr(rest, "geoms", []))
    stretches = []
    for piece in pieces:
        if piece.is_empty:
            continue
        stretches.append(
            (line.project(Point(piece.coords[0])), line.project(Point(piece.coords[-1])))
        )
    return sorted(stretches)


def match_route(graph: nx.MultiDiGraph, points: list[tuple[float, float]]) -> RouteMatch:
    crs = graph.graph["crs"]
    to_metres = Transformer.from_crs(4326, crs, always_xy=True)
    line = LineString([to_metres.transform(lon, lat) for lon, lat in points])
    road_map = bike_map(graph)
    stretches = off_network(line, road_map)
    off_m = sum(end - start for start, end in stretches)
    frame = gpd.GeoDataFrame(geometry=[Point(c) for c in line.coords], crs=crs)
    result = LCSSMatcher(road_map).match_trace(Trace.from_geo_dataframe(frame, xy=False))
    near = {m.road.road_id for m in result.matches if m.road and m.distance <= OFF_NETWORK_M}
    edges = []
    for road in result.path or []:
        key = (road.road_id.start, road.road_id.end, road.road_id.key)
        if road.road_id in near and key not in edges:
            edges.append(key)
    return RouteMatch(edges, line.length, off_m, stretches, 1 - off_m / line.length)


def corridor_boundary(points: list[list[tuple[float, float]]], buffer_m: float):
    longitude = sum(p[0] for line in points for p in line) / sum(len(line) for line in points)
    latitude = sum(p[1] for line in points for p in line) / sum(len(line) for line in points)
    crs = utm_crs(longitude, latitude)
    forward = Transformer.from_crs(4326, crs, always_xy=True)
    back = Transformer.from_crs(crs, 4326, always_xy=True)
    lines = [LineString([forward.transform(lon, lat) for lon, lat in line]) for line in points]
    area = unary_union(lines).buffer(buffer_m)
    return transform(back.transform, area), area.area / 1e6


def write_corridor(route: str | Path, region_id: str, like: str | Path, out: str | Path) -> Path:
    base = load_region(like)
    sections = read_route(route)
    boundary, area_km2 = corridor_boundary([s.points for s in sections], base.analysis_buffer_m)
    if area_km2 > MAX_CORRIDOR_KM2:
        raise RouteError(
            f"{route}: the corridor covers {area_km2:.0f} km2, over the {MAX_CORRIDOR_KM2:.0f} km2 "
            "limit for one run; split the route into sections and make one region for each"
        )
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    geojson = out / f"{region_id}.geojson"
    geojson.write_text(
        json.dumps(
            {"type": "Feature", "properties": {"name": region_id}, "geometry": mapping(boundary)}
        )
    )
    raw = yaml.safe_load(Path(like).read_text())
    raw["id"] = region_id
    raw["name"] = f"Corridor {region_id}"
    raw["boundary"] = {"geojson": str(geojson)}
    target = out / f"{region_id}.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False))
    try:
        load_region(target)
    except ConfigError as error:
        target.unlink()
        geojson.unlink()
        raise RouteError(str(error)) from error
    return target
