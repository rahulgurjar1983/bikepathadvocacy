import gzip
import hashlib
import json
import math
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import networkx as nx
import osmnx as ox
from pyproj import CRS, Transformer

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
    "cycleway:left:separation",
    "cycleway:right:separation",
    "cycleway:both:separation",
    "cycleway:left:width",
    "cycleway:right:width",
    "cycleway:both:width",
    "cycleway:width",
    "parking:left",
    "parking:right",
    "parking:both",
    "parking:lane:left",
    "parking:lane:right",
    "parking:lane:both",
    "width",
    "width:carriageway",
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
FOOT_PATHS = {"path", "footway"}
PROTECTED_VALUES = {"track", "separate"}
SHARED_VALUES = {"shared_lane", "share_busway"}
PROTECTING_SEPARATION = {"kerb", "bollard", "flex_post", "planter"}
NO_PARKING = {"no", "no_parking", "no_stopping", "separate"}
OPTIONAL_FIELDS = ["bike_lane_width_m", "width_tag_m", "width_drop_reason"]
POINT_HIGHWAYS = {"traffic_signals", "crossing"}
FEET_M = 0.3048
WIDTH_RANGE_M = (2.0, 40.0)


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


def travel_side(data: dict) -> str:
    return "right" if data["reversed"] else "left"


def side_value(data: dict, side: str, prefix: str, suffix: str = ""):
    for key in (f"{prefix}:{side}{suffix}", f"{prefix}:both{suffix}"):
        if data.get(key) is not None:
            return first(data[key])
    return None


def bike_facility(data: dict, side: str) -> str:
    highway = first(data.get("highway"))
    if highway == "cycleway" or (
        highway in FOOT_PATHS and first(data.get("bicycle")) == "designated"
    ):
        return "off_road"
    value = side_value(data, side, "cycleway")
    if value is None:
        value = first(data.get("cycleway"))
    if value in PROTECTED_VALUES:
        return "protected"
    if value == "lane":
        separation = side_value(data, side, "cycleway", ":separation")
        return "protected" if separation in PROTECTING_SEPARATION else "painted_lane"
    return "shared" if value in SHARED_VALUES else "none"


def parking_on_side(data: dict, side: str) -> str:
    value = side_value(data, side, "parking")
    if value is None:
        value = side_value(data, side, "parking:lane")
    if value is None:
        return "unknown"
    return "no" if value in NO_PARKING else "yes"


def parse_length(value) -> float | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m|ft|')?", str(first(value)).strip())
    if not match:
        return None
    return float(match[1]) * (FEET_M if match[2] in {"ft", "'"} else 1)


def parse_width(value) -> tuple[float | None, str | None]:
    metres = parse_length(value)
    if metres is None:
        return None, "unreadable"
    if not WIDTH_RANGE_M[0] <= metres <= WIDTH_RANGE_M[1]:
        return None, "out_of_range"
    return metres, None


def set_width_tag(data: dict) -> None:
    data["width_tag_m"], data["width_drop_reason"] = None, None
    for key in ("width:carriageway", "width"):
        if data.get(key) is None:
            continue
        metres, reason = parse_width(data[key])
        if metres is not None:
            data["width_tag_m"], data["width_drop_reason"] = metres, None
            return
        data["width_drop_reason"] = data["width_drop_reason"] or reason


def set_side_fields(data: dict) -> None:
    side = travel_side(data)
    data["bike_facility"] = bike_facility(data, side)
    lane_width = side_value(data, side, "cycleway", ":width")
    if lane_width is None:
        lane_width = first(data.get("cycleway:width"))
    data["bike_lane_width_m"] = parse_length(lane_width) if lane_width is not None else None
    data["parking"] = parking_on_side(data, side)
    set_width_tag(data)


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
        set_side_fields(data)


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
        ends = f"{min(u, v)}:{max(u, v)}"
        data["segment_id"] = hashlib.sha256(f"{data['osm_way']}:{ends}".encode()).hexdigest()[:16]
        for key in OPTIONAL_FIELDS:
            value = data.get(key)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                data[key] = None


def signal_points(xml: Path, crs: CRS) -> list[dict]:
    to_metres = Transformer.from_crs(4326, crs, always_xy=True)
    points = []
    for _, node in ET.iterparse(xml):
        if node.tag != "node":
            continue
        tags = {tag.get("k"): tag.get("v") for tag in node.iter("tag")}
        signal = "traffic_signals" in (tags.get("highway"), tags.get("crossing"))
        refuge = tags.get("crossing:island") == "yes"
        crossing = tags.get("highway") in POINT_HIGHWAYS or "crossing" in tags
        if signal or refuge or crossing:
            x, y = to_metres.transform(float(node.get("lon")), float(node.get("lat")))
            points.append(
                {"osm_id": int(node.get("id")), "x": x, "y": y, "signal": signal, "refuge": refuge}
            )
        node.clear()
    return points


def build(snapshot: str | Path, region: Region, profile: Profile) -> nx.MultiDiGraph:
    folder = Path(snapshot)
    crs = utm_crs(*boundary_centre(folder / "boundary.geojson"))
    ox.settings.useful_tags_way = WAY_TAGS
    with tempfile.TemporaryDirectory() as scratch:
        xml = Path(scratch) / "network.osm"
        xml.write_bytes(gzip.decompress((folder / "network.osm.gz").read_bytes()))
        graph = ox.graph_from_xml(xml, bidirectional=False, simplify=False, retain_all=True)
        points = signal_points(xml, crs)
    mark_bike_access(graph, profile)
    graph = ox.simplify_graph(graph, edge_attrs_differ=KEPT_APART)
    graph = ox.project_graph(graph, to_crs=crs)
    set_lengths(graph)
    graph.graph["points"] = points
    return graph


def tag_share(graph: nx.MultiDiGraph, is_tag) -> float:
    total = sum(data["length_m"] for _, _, data in graph.edges(data=True))
    tagged = sum(d["length_m"] for _, _, d in graph.edges(data=True) if is_tag(d))
    return tagged / total if total else 0.0


def summarise(graph: nx.MultiDiGraph) -> dict:
    segments = {}
    for _, _, data in graph.edges(data=True):
        if data["bike_ok"]:
            segments[data["segment_id"]] = data["length_m"]
    return {
        "edges": graph.number_of_edges(),
        "bike_km": sum(segments.values()) / 1000,
        "speed_tag_share": tag_share(graph, lambda d: d["speed_source"] != "default"),
        "lanes_tag_share": tag_share(graph, lambda d: d["lanes_source"] == "tag"),
        "parking_tag_share": tag_share(graph, lambda d: d["parking"] != "unknown"),
    }
