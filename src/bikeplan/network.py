import gzip
import json
import math
import re
import tempfile
from pathlib import Path

import networkx as nx
import osmnx as ox
from pyproj import CRS

from bikeplan.config import Profile, Region

WAY_TAGS = [
    "highway",
    "name",
    "ref",
    "oneway",
    "oneway:bicycle",
    "access",
    "bicycle",
    "service",
    "cycleway",
    "cycleway:left",
    "cycleway:right",
    "cycleway:both",
    "cycleway:left:oneway",
    "cycleway:right:oneway",
    "cycleway:both:oneway",
    "maxspeed",
    "lanes",
    "lanes:forward",
    "lanes:backward",
]
KEPT_APART = ["osmid", "bike_ok", "contraflow", *WAY_TAGS]
MILE_KMH = 1.609344
WALK_KMH = 10.0
BIKE_YES = {"yes", "designated"}
BIKE_NO = {"no", "dismount"}
CLOSED_ACCESS = {"private", "no"}
SERVICE_BLOCKED = {"parking_aisle", "driveway", "drive-through"}
CONTRAFLOW = {"opposite", "opposite_lane", "opposite_track"}
CONTRAFLOW_KEYS = ["cycleway", "cycleway:left", "cycleway:right", "cycleway:both"]
CONTRAFLOW_ONEWAY_KEYS = ["cycleway:left:oneway", "cycleway:right:oneway", "cycleway:both:oneway"]


def first(value):
    return value[0] if isinstance(value, list) else value


def bike_allowed(tags: dict) -> bool:
    highway = first(tags.get("highway"))
    bicycle = first(tags.get("bicycle"))
    access = first(tags.get("access"))
    if highway == "steps" or bicycle in BIKE_NO:
        return False
    if highway in {"footway", "pedestrian"} and bicycle not in BIKE_YES:
        return False
    if access in CLOSED_ACCESS and bicycle not in BIKE_YES:
        return False
    if highway == "trunk" and bicycle not in BIKE_YES:
        return False
    return not (highway == "service" and first(tags.get("service")) in SERVICE_BLOCKED)


def bike_contraflow(tags: dict) -> bool:
    if first(tags.get("oneway:bicycle")) == "no":
        return True
    if any(first(tags.get(key)) in CONTRAFLOW for key in CONTRAFLOW_KEYS):
        return True
    return any(first(tags.get(key)) == "-1" for key in CONTRAFLOW_ONEWAY_KEYS)


def parse_speed(value, profile: Profile) -> tuple[float, str] | None:
    text = str(first(value) or "").strip()
    if text == "walk":
        return WALK_KMH, "tag"
    if text in profile.implicit_speeds:
        return float(profile.implicit_speeds[text].value), "implicit"
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mph)?", text)
    if not match:
        return None
    return float(match[1]) * (MILE_KMH if match[2] else 1), "tag"


def parse_count(value) -> int | None:
    text = str(first(value) or "").strip()
    return int(text) if text.isdigit() else None


def road_class(highway, profile: Profile):
    name = str(first(highway) or "").removesuffix("_link")
    return profile.road_classes.get(name)


def set_lanes(data: dict, lane_default: int) -> None:
    total = parse_count(data.get("lanes"))
    forward = parse_count(data.get("lanes:forward"))
    backward = parse_count(data.get("lanes:backward"))
    data["lanes_source"] = "tag"
    if total is None and forward is not None and backward is not None:
        total = forward + backward
    if total is None:
        total = lane_default
        data["lanes_source"] = "default"
    if data["oneway"]:
        lanes_dir = 0 if data.get("contraflow") else total
    else:
        if forward is None:
            forward = total - backward if backward is not None else (total + 1) // 2
        if backward is None:
            backward = total - forward
        lanes_dir = backward if data["reversed"] else forward
    data["lanes_total"] = total
    data["lanes_dir"] = lanes_dir


def set_traffic_fields(data: dict, profile: Profile) -> None:
    road = road_class(data.get("highway"), profile)
    speed = parse_speed(data.get("maxspeed"), profile)
    if speed is None:
        speed = (float(road.speed_kmh.value), "default") if road else (None, "default")
    data["speed_kmh"], data["speed_source"] = speed
    set_lanes(data, int(road.lanes.value) if road else 0)
    data["adt"] = road.adt.value if road else 0
    data["adt_source"] = "default"


def utm_crs(longitude: float, latitude: float) -> CRS:
    zone = int((longitude + 180) // 6) % 60 + 1
    return CRS.from_epsg((32600 if latitude >= 0 else 32700) + zone)


def boundary_centre(path: Path) -> tuple[float, float]:
    feature = json.loads(path.read_text())
    geometry = feature["geometry"] if feature["type"] == "Feature" else feature
    polygons = (
        geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    )
    points = [point for polygon in polygons for ring in polygon for point in ring]
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return (min(longitudes) + max(longitudes)) / 2, (min(latitudes) + max(latitudes)) / 2


def mark_bike_access(graph: nx.MultiDiGraph, profile: Profile) -> None:
    for u, v, data in list(graph.edges(data=True)):
        data["bike_ok"] = bike_allowed(data)
        if data["oneway"] and data["bike_ok"] and bike_contraflow(data):
            reverse = dict(data)
            reverse["reversed"] = not data["reversed"]
            reverse["contraflow"] = True
            graph.add_edge(v, u, **reverse)
    for _, _, data in graph.edges(data=True):
        set_traffic_fields(data, profile)


def set_lengths(graph: nx.MultiDiGraph) -> None:
    for u, v, data in graph.edges(data=True):
        geometry = data.get("geometry")
        if geometry is not None:
            length = geometry.length
        else:
            length = math.dist(
                (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                (graph.nodes[v]["x"], graph.nodes[v]["y"]),
            )
        data["length_m"] = length
        data["osm_way"] = first(data["osmid"])


def build(snapshot: str | Path, region: Region, profile: Profile) -> nx.MultiDiGraph:
    folder = Path(snapshot)
    crs = utm_crs(*boundary_centre(folder / "boundary.geojson"))
    ox.settings.useful_tags_way = WAY_TAGS
    with tempfile.TemporaryDirectory() as scratch:
        xml = Path(scratch) / "network.osm"
        xml.write_bytes(gzip.decompress((folder / "network.osm.gz").read_bytes()))
        graph = ox.graph_from_xml(xml, bidirectional=False, simplify=False, retain_all=True)
    mark_bike_access(graph, profile)
    graph = ox.simplify_graph(graph, edge_attrs_differ=KEPT_APART)
    graph = ox.project_graph(graph, to_crs=crs)
    set_lengths(graph)
    return graph
