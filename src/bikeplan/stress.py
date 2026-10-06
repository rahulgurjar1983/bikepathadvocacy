from bisect import bisect_left

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
