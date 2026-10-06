import math

import pytest
from shapely.geometry import LineString, box

from bikeplan.config import load_profile
from bikeplan.width import reserve, reserve_estimate

PROFILE = load_profile("au-nsw", "profiles")


def rows(gap, length=200, depth=30, skip=()):
    half = gap / 2
    parcels = []
    for index in range(length // 20):
        x = index * 20
        if ("north", index) not in skip:
            parcels.append(box(x, half, x + 20, half + depth))
        if ("south", index) not in skip:
            parcels.append(box(x, -half - depth, x + 20, -half))
    return parcels


def test_fr5_3_straight_street_between_parcel_rows_gives_the_gap():
    found = reserve(LineString([(0, 0), (200, 0)]), rows(20))
    assert found.width_m == pytest.approx(20)
    assert found.spread_m == pytest.approx(0)


def test_fr5_3_lines_with_a_gap_on_one_side_are_skipped():
    skip = {("north", index) for index in range(0, 6)}
    found = reserve(LineString([(0, 0), (200, 0)]), rows(20, skip=skip))
    assert found.width_m == pytest.approx(20)


def test_fr5_3_too_few_hits_give_no_value():
    skip = {("north", index) for index in range(0, 10) if index not in (0, 1)}
    assert reserve(LineString([(0, 0), (200, 0)]), rows(20, skip=skip)) is None


def test_fr5_3_under_sixty_percent_of_lines_gives_no_value():
    skip = {("north", index) for index in range(0, 10) if index > 4}
    assert reserve(LineString([(0, 0), (200, 0)]), rows(20, skip=skip)) is None


def test_fr5_3_curved_street_still_gives_the_right_width():
    radius = 100
    centre = LineString(
        [
            (radius * math.sin(a / 40 * math.pi / 2), radius * (1 - math.cos(a / 40 * math.pi / 2)))
            for a in range(41)
        ]
    )
    parcels = [centre.buffer(10 + 30, cap_style="flat").difference(centre.buffer(10))]
    found = reserve(centre, parcels)
    assert found.width_m == pytest.approx(20, abs=0.5)


def test_fr5_3_spread_is_the_gap_between_quartiles():
    parcels = [box(0, 10, 100, 40), box(100, 12, 200, 40), box(0, -40, 200, -10)]
    found = reserve(LineString([(0, 0), (200, 0)]), parcels)
    assert found.spread_m == pytest.approx(2, abs=0.01)


def test_fr5_4_twenty_metre_reserve_gives_thirteen_metres_with_range():
    found = reserve_estimate(reserve(LineString([(0, 0), (200, 0)]), rows(20)), PROFILE)
    assert (found.width_m, found.low_m, found.high_m) == pytest.approx((13, 11.5, 14.5))
    assert found.source == "reserve"
    assert found.confidence == "low"


def test_fr5_4_wide_spread_drops_the_confidence_one_level():
    parcels = [box(0, 10, 100, 40), box(100, 14, 200, 40), box(0, -40, 200, -10)]
    found = reserve(LineString([(0, 0), (200, 0)]), parcels)
    assert found.spread_m > 2
    assert reserve_estimate(found, PROFILE).confidence == "very low"
