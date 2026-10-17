import math

import geopandas
from shapely.geometry import LineString
from shapely.ops import linemerge
from shapely.strtree import STRtree

from bikeplan.config import Profile

SEGMENT_REACH_M = 15.0
SEGMENT_BEARING_DEG = 20.0
SEGMENT_MIN_SHARE = 0.5


def chord_bearing(line) -> float | None:
    if line.is_empty or line.length == 0:
        return None
    if line.geom_type != "LineString":
        line = linemerge(line)
        if line.geom_type != "LineString":
            line = max(line.geoms, key=lambda part: part.length)
    start, end = line.coords[0], line.coords[-1]
    return math.degrees(math.atan2(end[0] - start[0], end[1] - start[1])) % 180


def bearing_gap(first: float, second: float) -> float:
    gap = abs(first - second) % 180
    return min(gap, 180 - gap)


def segment_overlap(edge: LineString, segment: LineString) -> float:
    near = edge.intersection(segment.buffer(SEGMENT_REACH_M))
    ours = chord_bearing(near)
    theirs = chord_bearing(segment.intersection(edge.buffer(SEGMENT_REACH_M)))
    if ours is None or theirs is None or bearing_gap(ours, theirs) > SEGMENT_BEARING_DEG:
        return 0.0
    return near.length / edge.length


def match_segment(edge: LineString, lines: list, index: STRtree) -> int | None:
    best, best_share = None, SEGMENT_MIN_SHARE
    for position in sorted(index.query(edge.buffer(SEGMENT_REACH_M))):
        share = segment_overlap(edge, lines[position])
        if share >= best_share and (best is None or share > best_share):
            best, best_share = int(position), share
    return best


def edge_matches(graph, lines: list, only=None):
    index = STRtree(lines)
    for u, v, data in graph.edges(data=True):
        if only is not None and not only(data):
            continue
        line = data.get("geometry")
        if line is None:
            line = LineString([(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in (u, v)])
        if line.length == 0:
            continue
        found = match_segment(line, lines, index)
        if found is not None:
            yield data, found


def set_zone_speeds(graph, zones_path, crs) -> None:
    frame = geopandas.read_file(zones_path).to_crs(crs)
    speeds = list(frame["speed_kmh"])
    sources = list(frame["speed_source"])
    for data, found in edge_matches(
        graph,
        list(frame.geometry),
        lambda data: data.get("speed_source") == "default" and data.get("speed_kmh") is not None,
    ):
        data["speed_kmh"] = float(speeds[found])
        data["speed_source"] = sources[found]


def set_segment_traffic(graph, segments_path, crs, profile: Profile) -> None:
    frame = geopandas.read_file(segments_path).to_crs(crs)
    frame = frame[frame["function"].isin(profile.road_functions)]
    names = list(frame["function"])
    sources = list(frame["adt_source"])
    for data, found in edge_matches(graph, list(frame.geometry)):
        data["adt"] = profile.road_functions[names[found]].value
        data["adt_source"] = sources[found]
        data["road_function"] = names[found]
    take_way_function(graph, profile, frame)


def take_way_function(graph, profile: Profile, frame) -> None:
    covered: dict = {}
    for _, _, data in graph.edges(data=True):
        if "road_function" in data:
            way = covered.setdefault(data["osm_way"], {})
            way[data["road_function"]] = way.get(data["road_function"], 0.0) + data["length_m"]
    source = frame["adt_source"].iloc[0] if len(frame) else None
    for _, _, data in graph.edges(data=True):
        way = covered.get(data["osm_way"])
        if way and "road_function" not in data:
            name = min(way, key=lambda function: (-way[function], function))
            data["adt"] = profile.road_functions[name].value
            data["adt_source"] = source
            data["road_function"] = name
