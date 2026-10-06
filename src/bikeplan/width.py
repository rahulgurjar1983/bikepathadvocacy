from dataclasses import dataclass

from bikeplan.config import Profile
from bikeplan.network import bike_facility, parking_on_side, road_class

LANE_MARGIN_M = 0.3
PAINTED_LANE_M = 1.5
LANE_RANGE_M = (1.0, 1.5)
TAG_RANGE_M = 0.5
WIDTH_LIMITS_M = (3.0, 40.0)
SIDES = ("left", "right")


@dataclass(frozen=True)
class Estimate:
    width_m: float
    low_m: float
    high_m: float
    source: str
    confidence: str


def parked_sides(data: dict, class_parking: bool) -> int:
    states = [parking_on_side(data, side) for side in SIDES]
    return sum(state == "yes" or (state == "unknown" and class_parking) for state in states)


def lane_estimate(data: dict, profile: Profile) -> Estimate | None:
    lanes = data.get("lanes_total") or 0
    if lanes <= 0:
        return None
    widths = profile.widths_m
    road = road_class(data.get("highway"), profile)
    class_parking = bool(road and road.parking.value)
    painted = sum(bike_facility(data, side) == "painted_lane" for side in SIDES)
    width = (
        lanes * (widths.traffic_lane.min.value + LANE_MARGIN_M)
        + parked_sides(data, class_parking) * widths.parking_lane.value
        + painted * PAINTED_LANE_M
    )
    return Estimate(width, width - LANE_RANGE_M[0], width + LANE_RANGE_M[1], "lanes", "low")


def tag_estimate(data: dict) -> Estimate | None:
    width = data.get("width_tag_m")
    if width is None:
        return None
    return Estimate(width, width - TAG_RANGE_M, width + TAG_RANGE_M, "osm_tag", "medium")


def range_reason(estimate: Estimate) -> str | None:
    low, high = WIDTH_LIMITS_M
    if low <= estimate.width_m <= high:
        return None
    return f"{estimate.width_m:g} m is outside {low:g} m to {high:g} m"


def estimates(data: dict, profile: Profile) -> tuple[list[Estimate], list[tuple[str, str]]]:
    kept, dropped = [], []
    for found in (tag_estimate(data), lane_estimate(data, profile)):
        if found is None:
            continue
        reason = range_reason(found)
        if reason:
            dropped.append((found.source, reason))
        else:
            kept.append(found)
    return kept, dropped
