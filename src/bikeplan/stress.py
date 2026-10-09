import json
import math
from bisect import bisect_left
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from pyproj import Transformer

from bikeplan.config import Profile
from bikeplan.network import FOOT_PATHS, bike_segments, first, parking_on_side, road_class
from bikeplan.safety import audit

SPEED_TOPS_KMH = [37.82, 45.87, 53.91, 61.96, 70.01, 78.05]
MINOR_CLASSES = {"residential", "living_street", "service", "unclassified"}
WIDE_ONE_WAY_M = {0: 4.57, 1: 6.71, 2: 9.14}
TABLE_1 = {
    "A": [
        (750, [1, 1, 2, 2, 3, 3, 3]),
        (1500, [1, 1, 2, 3, 3, 3, 3]),
        (3000, [2, 2, 2, 3, 3, 4, 4]),
        (None, [2, 2, 3, 3, 4, 4, 4]),
    ],
    "B": [
        (1000, [1, 1, 2, 2, 3, 3, 3]),
        (1500, [2, 2, 2, 3, 3, 4, 4]),
        (None, [2, 3, 3, 3, 4, 4, 4]),
    ],
    "C": [
        (600, [1, 1, 2, 2, 3, 3, 3]),
        (1000, [2, 2, 2, 3, 3, 4, 4]),
        (None, [2, 3, 3, 3, 4, 4, 4]),
    ],
    "D": [(8000, [3, 3, 3, 3, 4, 4, 4]), (None, [3, 3, 4, 4, 4, 4, 4])],
    "E": [(None, [3, 3, 4, 4, 4, 4, 4])],
}
TABLE_2 = {
    1: ([1, 1, 2, 3, 3, 3], [2, 2, 2, 3, 3, 4]),
    2: ([2, 2, 2, 3, 3, 3], [2, 2, 2, 3, 4, 4]),
    3: ([3, 3, 3, 4, 4, 4], [3, 3, 3, 4, 4, 4]),
}
TABLE_3 = {
    "one": ([1, 2, 2, 3], [2, 2, 3, 3]),
    "many_one_way": ([2, 3, 3, 3], [3, 3, 3, 3]),
    "two": ([2, 3, 3, 3], [3, 3, 3, 3]),
    "other": ([3, 3, 3, 3], [3, 3, 3, 3]),
}
OFF_ROAD_FACILITIES = {"off_road", "protected"}
WIDE_LANE_M = 1.83
MIN_LANE_M = 1.22
WIDE_REACH_M = 4.57
MIN_REACH_M = 3.66
POINT_RADIUS_M = 25.0
STRAIGHT_TOLERANCE_DEG = 30.0
CROSSING_SPEED_TOPS_KMH = [40.0, 50.0, 60.0]
CROSSING_LANE_TOPS = [3, 5]
CROSSING_TABLE = [
    [1, 2, 4, 1, 1, 2],
    [1, 2, 4, 1, 2, 3],
    [2, 3, 4, 2, 3, 4],
    [3, 4, 4, 3, 4, 4],
]
ROAD_RANK = {
    name: rank
    for rank, name in enumerate(
        [
            "living_street",
            "service",
            "residential",
            "unclassified",
            "tertiary",
            "secondary",
            "primary",
            "trunk",
        ]
    )
}


def speed_band(speed_kmh: float) -> int:
    return bisect_left(SPEED_TOPS_KMH, speed_kmh) + 1


def parked_sides(data: dict) -> int:
    return sum(parking_on_side(data, side) == "yes" for side in ("left", "right"))


def wide_one_way(data: dict) -> bool:
    width = data.get("width_tag_m")
    return width is not None and width >= WIDE_ONE_WAY_M[parked_sides(data)]


def street_type(data: dict) -> str:
    lanes = data["lanes_total"] if data["oneway"] else data["lanes_dir"]
    if lanes >= 3:
        return "E"
    if lanes == 2:
        return "D"
    if data["oneway"]:
        return "B" if wide_one_way(data) else "C"
    if first(data.get("lane_markings")) == "no":
        return "A"
    minor = first(data.get("highway")) in MINOR_CLASSES
    return "A" if minor and data.get("lanes") is None else "B"


def mixed_traffic_lts(data: dict) -> int:
    band = speed_band(data["speed_kmh"]) - 1
    for top, scores in TABLE_1[street_type(data)]:
        if top is None or data["adt"] <= top:
            return scores[band]
    raise AssertionError("unreachable")


def parking_beside(data: dict, class_parking: bool) -> bool:
    return data["parking"] == "yes" or (data["parking"] == "unknown" and class_parking)


def lanes_each_way(data: dict) -> int:
    if data.get("contraflow"):
        return 1
    return max(data["lanes_total"] if data["oneway"] else data["lanes_dir"], 1)


def table_2_lts(data: dict, lanes: int) -> int:
    wide = (data["bike_lane_width_m"] or 0) >= WIDE_LANE_M
    column = max(speed_band(data["speed_kmh"]) - 2, 0)
    return TABLE_2[min(lanes, 3)][0 if wide else 1][column]


def table_3_lts(data: dict, lanes: int, reach: float | None) -> int:
    if lanes <= 1:
        row = "one"
    elif data["oneway"] and not data.get("contraflow"):
        row = "many_one_way"
    else:
        row = "two" if lanes == 2 else "other"
    long_reach = reach is not None and reach >= WIDE_REACH_M
    column = min(max(speed_band(data["speed_kmh"]) - 2, 0), 3)
    return TABLE_3[row][0 if long_reach else 1][column]


def painted_lane_lts(data: dict, parking_lane_m: float, class_parking: bool) -> int:
    lane = data["bike_lane_width_m"]
    lanes = lanes_each_way(data)
    mixed = mixed_traffic_lts(data)
    if not parking_beside(data, class_parking):
        if lane is not None and lane < MIN_LANE_M:
            return mixed
        return min(table_2_lts(data, lanes), mixed)
    reach = None if lane is None else round(lane + parking_lane_m, 2)
    if reach is not None and reach < MIN_REACH_M:
        return mixed
    return min(table_3_lts(data, lanes, reach), mixed)


def edge_lts(data: dict, profile: Profile) -> int:
    if data["bike_facility"] in OFF_ROAD_FACILITIES or is_shared_path(data):
        return 1
    if data["bike_facility"] == "painted_lane":
        parking = road_class(first(data.get("highway")), profile).parking.value
        return painted_lane_lts(data, profile.widths_m.parking_lane.value, parking)
    return mixed_traffic_lts(data)


def is_shared_path(data: dict) -> bool:
    return (
        data["bike_ok"]
        and data["bike_facility"] not in OFF_ROAD_FACILITIES
        and first(data.get("highway")) in FOOT_PATHS
    )


def path_min_width(profile: Profile) -> float:
    return profile.widths_m.two_way_cycleway.min.value


def path_wide_enough(data: dict, profile: Profile) -> bool:
    width = data.get("width_tag_m")
    return width is None or width >= path_min_width(profile)


def path_text(data: dict) -> str:
    width = data.get("width_tag_m")
    return "width unknown" if width is None else f"{width:g} m wide"


def path_verdict(data: dict, final: int, profile: Profile) -> str:
    if final != 1:
        return f"not AAA: LTS is {final}"
    if not path_wide_enough(data, profile):
        return f"not AAA: path is narrower than {path_min_width(profile):g} m"
    flag = " (width unknown)" if data.get("width_tag_m") is None else ""
    return f"AAA: path is wide enough{flag}"


def is_aaa(data: dict, lts: int, profile: Profile) -> bool:
    if not data["bike_ok"] or lts != 1:
        return False
    facility = data["bike_facility"]
    if is_shared_path(data):
        return path_wide_enough(data, profile)
    if facility in OFF_ROAD_FACILITIES:
        return True
    if facility == "painted_lane":
        return bool(profile.aaa.painted_lanes_count.value)
    return any(
        data["speed_kmh"] <= rule.max_speed_kmh.value and data["adt"] <= rule.max_adt.value
        for rule in profile.aaa.mixed_traffic
    )


def junction_points(graph, radius_m: float = POINT_RADIUS_M) -> dict:
    cells = defaultdict(list)
    for point in graph.graph["points"]:
        cells[(int(point["x"] // radius_m), int(point["y"] // radius_m))].append(point)
    flags = {}
    for node, data in graph.nodes(data=True):
        cx, cy = int(data["x"] // radius_m), int(data["y"] // radius_m)
        near = [
            point
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for point in cells.get((cx + dx, cy + dy), [])
            if math.hypot(point["x"] - data["x"], point["y"] - data["y"]) <= radius_m
        ]
        flags[node] = {
            "signal": any(point["signal"] for point in near),
            "refuge": any(point["refuge"] for point in near),
        }
    return flags


def crossing_lts(speed_kmh: float, lanes: int, refuge: bool) -> int:
    row = bisect_left(CROSSING_SPEED_TOPS_KMH, speed_kmh)
    column = bisect_left(CROSSING_LANE_TOPS, lanes) + 3 * bool(refuge)
    return CROSSING_TABLE[row][column]


def leg_bearing(graph, node, u, v, data) -> float:
    geometry = data.get("geometry")
    if geometry is not None:
        coords = list(geometry.coords)
    else:
        coords = [
            (graph.nodes[u]["x"], graph.nodes[u]["y"]),
            (graph.nodes[v]["x"], graph.nodes[v]["y"]),
        ]
    start, towards = (coords[0], coords[1]) if node == u else (coords[-1], coords[-2])
    return math.degrees(math.atan2(towards[0] - start[0], towards[1] - start[1])) % 360


def junction_legs(graph, node) -> list[dict]:
    legs = {}
    for u, v, k, data in list(graph.in_edges(node, keys=True, data=True)) + list(
        graph.out_edges(node, keys=True, data=True)
    ):
        if u == v:
            continue
        leg = legs.setdefault(
            data["segment_id"],
            {"data": data, "bearing": leg_bearing(graph, node, u, v, data), "keys": set()},
        )
        leg["keys"].add((u, v, k))
    return list(legs.values())


def leg_rank(leg: dict) -> int:
    return ROAD_RANK.get(str(first(leg["data"].get("highway")) or "").removesuffix("_link"), -1)


def is_straight(first_leg: dict, second_leg: dict) -> bool:
    turn = abs(first_leg["bearing"] - second_leg["bearing"]) % 360
    return abs(min(turn, 360 - turn) - 180) <= STRAIGHT_TOLERANCE_DEG


def main_street(legs: list[dict]):
    pairs = [
        pair
        for pair in combinations(legs, 2)
        if all(leg["data"]["lanes_total"] > 0 and "speed_kmh" in leg["data"] for leg in pair)
        and is_straight(*pair)
    ]
    if not pairs:
        return None
    return max(
        pairs,
        key=lambda pair: (
            sum(leg["data"]["lanes_total"] for leg in pair),
            sum(leg_rank(leg) for leg in pair),
        ),
    )


def raise_for_crossings(graph, lts: dict, profile: Profile) -> tuple[dict, dict]:
    flags = junction_points(graph)
    final = dict(lts)
    crossings = {}
    for node in graph.nodes:
        if flags[node]["signal"]:
            continue
        legs = junction_legs(graph, node)
        main = main_street(legs)
        if main is None:
            continue
        lanes = max(leg["data"]["lanes_total"] for leg in main)
        speed = max(leg["data"]["speed_kmh"] for leg in main)
        score = crossing_lts(speed, lanes, flags[node]["refuge"])
        for leg in legs:
            if any(leg is street for street in main):
                continue
            for key in leg["keys"]:
                if score > final[key]:
                    final[key] = score
                    crossings[key] = {
                        "junction": node,
                        "lts": score,
                        "speed_kmh": speed,
                        "lanes": lanes,
                        "refuge": flags[node]["refuge"],
                    }
    return final, crossings


def has_traffic(data: dict) -> bool:
    return "speed_kmh" in data and data["lanes_total"] > 0


def own_lts(data: dict, profile: Profile) -> int:
    if data["bike_facility"] in OFF_ROAD_FACILITIES or is_shared_path(data):
        return 1
    if not has_traffic(data):
        return 1
    return edge_lts(data, profile)


def edge_aaa(data: dict, final: int, profile: Profile) -> bool:
    if (
        data["bike_facility"] not in OFF_ROAD_FACILITIES
        and not is_shared_path(data)
        and not has_traffic(data)
    ):
        return False
    return is_aaa(data, final, profile)


def rule_verdict(data: dict, profile: Profile) -> str:
    rules = profile.aaa.mixed_traffic
    for rule in rules:
        speed, adt = rule.max_speed_kmh.value, rule.max_adt.value
        if data["speed_kmh"] <= speed and data["adt"] <= adt:
            return (
                f"{data['speed_kmh']:g} km/h is within {speed:g} "
                f"and ADT {data['adt']} is within {adt:g}"
            )
    rule = rules[0]
    if data["speed_kmh"] > rule.max_speed_kmh.value:
        return f"{data['speed_kmh']:g} km/h is above {rule.max_speed_kmh.value:g}"
    return f"ADT {data['adt']} is above {rule.max_adt.value:g}"


def aaa_verdict(data: dict, final: int, aaa: bool, profile: Profile) -> str:
    facility = data["bike_facility"]
    if aaa and facility in OFF_ROAD_FACILITIES:
        return "AAA: off-road paths and protected lanes are AAA"
    if aaa and facility == "painted_lane":
        return "AAA: painted lanes count as AAA in this profile"
    if aaa:
        return f"AAA: {rule_verdict(data, profile)}"
    if not data["bike_ok"]:
        return "not AAA: bikes may not use it"
    if facility == "painted_lane":
        return "not AAA: painted lanes do not count as AAA"
    verdict = rule_verdict(data, profile)
    if final != 1 and " is within " in verdict:
        return f"not AAA: LTS is {final}"
    return f"not AAA: {verdict}"


def traffic_text(data: dict) -> str:
    return (
        f"{data['speed_kmh']:g} km/h ({data['speed_source']}), "
        f"ADT {data['adt']} ({data['adt_source']})"
    )


def own_text(data: dict, own: int, profile: Profile) -> str:
    facility = data["bike_facility"]
    if facility in OFF_ROAD_FACILITIES:
        return f"off-road path -> LTS {own}"
    if is_shared_path(data):
        return f"shared path, {path_text(data)} -> LTS {own}"
    if not has_traffic(data):
        return f"no motor traffic -> LTS {own}"
    if facility == "painted_lane":
        parking = road_class(first(data.get("highway")), profile).parking.value
        table = 3 if parking_beside(data, parking) else 2
        lanes = lanes_each_way(data)
        width = data["bike_lane_width_m"]
        lane = "untagged" if width is None else f"{width:g} m"
        plural = "lane" if lanes == 1 else "lanes"
        return (
            f"painted lane, table {table}, {lanes} {plural} each way, lane {lane}, "
            f"{traffic_text(data)} -> LTS {own}"
        )
    return f"mixed traffic, type {street_type(data)}, {traffic_text(data)} -> LTS {own}"


def edge_reason(data: dict, profile: Profile, own: int, final: int, crossing) -> str:
    parts = [own_text(data, own, profile)]
    if crossing is not None:
        refuge = "refuge" if crossing["refuge"] else "no refuge"
        parts.append(
            f"raised to LTS {final} by crossing at junction {crossing['junction']} "
            f"(main street {crossing['speed_kmh']:g} km/h, {crossing['lanes']} lanes, {refuge})"
        )
    aaa = edge_aaa(data, final, profile)
    if is_shared_path(data):
        parts.append(path_verdict(data, final, profile))
    elif aaa or has_traffic(data):
        parts.append(aaa_verdict(data, final, aaa, profile))
    else:
        parts.append("not AAA: no motor traffic data")
    return "; ".join(parts)


def score_edges(graph, profile: Profile, assumptions: bool = False) -> dict:
    own = {(u, v, k): own_lts(d, profile) for u, v, k, d in graph.edges(keys=True, data=True)}
    final, crossings = raise_for_crossings(graph, own, profile)
    evidence = audit(
        graph,
        profile,
        {key: edge_aaa(graph.edges[key], own[key], profile) for key in own},
        own,
        junction_points(graph),
        junction_legs,
        main_street,
        crossing_lts,
        assumptions,
    )
    return {
        key: {
            **evidence[key],
            "lts": final[key],
            "aaa": edge_aaa(data, final[key], profile),
            "reason": edge_reason(data, profile, own[key], final[key], crossings.get(key)),
        }
        for u, v, k, data in graph.edges(keys=True, data=True)
        for key in [(u, v, k)]
    }


def stress_features(graph, scores: dict) -> list[dict]:
    to_lonlat = Transformer.from_crs(graph.graph["crs"], "EPSG:4326", always_xy=True)
    features = []
    for u, v, k, data in graph.edges(keys=True, data=True):
        geometry = data.get("geometry")
        if geometry is not None:
            points = list(geometry.coords)
        else:
            points = [(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in (u, v)]
        xs, ys = to_lonlat.transform([p[0] for p in points], [p[1] for p in points])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": list(zip(xs, ys, strict=True))},
                "properties": {
                    "u": u,
                    "v": v,
                    "k": k,
                    "osm_way": data.get("osm_way"),
                    "segment_id": data["segment_id"],
                    "highway": first(data.get("highway")),
                    "length_m": round(data["length_m"], 2),
                    "bike_ok": data["bike_ok"],
                    **scores[(u, v, k)],
                },
            }
        )
    return features


def stress_summary(graph, scores: dict) -> dict:
    def empty():
        return {"km_by_lts": {str(lts): 0.0 for lts in range(1, 5)}, "km_aaa": 0.0}

    total, by_class = empty(), {}
    for segment in bike_segments(graph).values():
        keys, datas = zip(*segment["edges"], strict=True)
        lts = max(scores[key]["lts"] for key in keys)
        aaa = all(scores[key]["aaa"] for key in keys)
        km = segment["inside_m"] / 1000
        name = str(first(datas[0].get("highway")))
        for bucket in (total, by_class.setdefault(name, empty())):
            bucket["km_by_lts"][str(lts)] += km
            bucket["km_aaa"] += km * aaa
    return {**total, "by_road_class": dict(sorted(by_class.items()))}


def write_stress(graph, profile: Profile, out) -> dict:
    scores = score_edges(graph, profile)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", "features": stress_features(graph, scores)}
    (out / "stress.geojson").write_text(json.dumps(collection))
    summary = stress_summary(graph, scores)
    (out / "stress_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def eligible_links(scores: dict, assumptions: bool = False) -> set:
    states = {"confirmed", "assumed"} if assumptions else {"confirmed"}
    return {key for key, item in scores.items() if item["all_ages_status"] in states}
