from bisect import bisect_left

from bikeplan.network import first, parking_on_side

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
