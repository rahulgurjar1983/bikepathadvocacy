import math
from bisect import bisect_left
from collections import defaultdict
from itertools import combinations

from bikeplan.config import Profile
from bikeplan.network import first, parking_on_side, road_class

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
    if data["bike_facility"] in OFF_ROAD_FACILITIES:
        return 1
    if data["bike_facility"] == "painted_lane":
        parking = road_class(first(data.get("highway")), profile).parking.value
        return painted_lane_lts(data, profile.widths_m.parking_lane.value, parking)
    return mixed_traffic_lts(data)


def is_aaa(data: dict, lts: int, profile: Profile) -> bool:
    if not data["bike_ok"] or lts != 1:
        return False
    facility = data["bike_facility"]
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
