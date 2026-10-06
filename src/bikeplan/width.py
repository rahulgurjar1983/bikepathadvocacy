import math
from dataclasses import dataclass

import numpy as np
from shapely import Point, unary_union
from shapely.geometry import LineString

from bikeplan.config import Profile
from bikeplan.network import bike_facility, parking_on_side, road_class

LANE_MARGIN_M = 0.3
PAINTED_LANE_M = 1.5
LANE_RANGE_M = (1.0, 1.5)
TAG_RANGE_M = 0.5
WIDTH_LIMITS_M = (3.0, 40.0)
SIDES = ("left", "right")
RESERVE_STEP_M = 20.0
RESERVE_REACH_M = 40.0
RESERVE_MIN_LINES = 3
RESERVE_MIN_SHARE = 0.6
RESERVE_RANGE_M = 1.5
RESERVE_WIDE_SPREAD_M = 2.0
CONFIDENCE_LEVELS = ("high", "medium", "low", "very low")


@dataclass(frozen=True)
class Estimate:
    width_m: float
    low_m: float
    high_m: float
    source: str
    confidence: str


@dataclass(frozen=True)
class Reserve:
    width_m: float
    spread_m: float
    lines: int


def first_hit_m(origin: Point, direction: tuple[float, float], parcels) -> float | None:
    end = (
        origin.x + direction[0] * RESERVE_REACH_M,
        origin.y + direction[1] * RESERVE_REACH_M,
    )
    hit = LineString([(origin.x, origin.y), end]).intersection(parcels)
    return None if hit.is_empty else origin.distance(hit)


def reserve(segment: LineString, parcels: list) -> Reserve | None:
    if not parcels or segment.length == 0:
        return None
    merged = unary_union(parcels)
    count = max(1, math.ceil(segment.length / RESERVE_STEP_M))
    totals = []
    for index in range(count):
        along = (index + 0.5) * segment.length / count
        origin = segment.interpolate(along)
        ahead = segment.interpolate(min(along + 0.5, segment.length))
        behind = segment.interpolate(max(along - 0.5, 0))
        dx, dy = ahead.x - behind.x, ahead.y - behind.y
        norm = math.hypot(dx, dy)
        if norm == 0:
            continue
        normal = (-dy / norm, dx / norm)
        left = first_hit_m(origin, normal, merged)
        right = first_hit_m(origin, (-normal[0], -normal[1]), merged)
        if left is not None and right is not None:
            totals.append(left + right)
    if len(totals) < RESERVE_MIN_LINES or len(totals) < RESERVE_MIN_SHARE * count:
        return None
    low, median, high = np.percentile(totals, [25, 50, 75])
    return Reserve(float(median), float(high - low), len(totals))


def reserve_estimate(found: Reserve, profile: Profile) -> Estimate:
    width = found.width_m - 2 * profile.widths_m.verge_default.value
    level = CONFIDENCE_LEVELS.index("low")
    if found.spread_m > RESERVE_WIDE_SPREAD_M:
        level += 1
    return Estimate(
        width, width - RESERVE_RANGE_M, width + RESERVE_RANGE_M, "reserve", CONFIDENCE_LEVELS[level]
    )


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
