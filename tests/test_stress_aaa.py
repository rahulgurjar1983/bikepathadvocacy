from dataclasses import replace

import pytest

from bikeplan.config import load_profile
from bikeplan.stress import edge_lts, is_aaa

SPEEDS = [10.0, 40.0, 60.0, 80.0, 110.0]
PROFILES = ["au-nsw", "generic"]
BUSY = {
    "oneway": False,
    "lanes_total": 6,
    "lanes_dir": 3,
    "adt": 30000,
    "highway": "primary",
    "bike_lane_width_m": None,
    "parking": "no",
    "bike_ok": True,
}


def edge(facility, speed, adt=None, **extra):
    data = {**BUSY, "bike_facility": facility, "speed_kmh": speed, **extra}
    if adt is not None:
        data["adt"] = adt
    return data


def calm(facility, speed=30.0, adt=500, **extra):
    return edge(
        facility,
        speed,
        adt,
        lanes_total=2,
        lanes_dir=1,
        highway="residential",
        **extra,
    )


@pytest.fixture(params=PROFILES)
def profile(request):
    return load_profile(request.param)


@pytest.mark.parametrize("facility", ["off_road", "protected"])
@pytest.mark.parametrize("speed", SPEEDS)
def test_fr4_3_paths_and_protected_lanes_score_one_at_any_speed(profile, facility, speed):
    assert edge_lts(edge(facility, speed), profile) == 1


@pytest.mark.parametrize("facility", ["shared", "none"])
def test_fr4_3_shared_and_bare_edges_use_table_1(profile, facility):
    assert edge_lts(calm(facility, 30.0, 500), profile) == 1
    assert edge_lts(edge(facility, 80.0), profile) == 4


def test_fr4_3_painted_lane_uses_painted_tables(profile):
    data = calm("painted_lane", 50.0, 3000, bike_lane_width_m=2.0)
    assert edge_lts(data, profile) == 1
    assert edge_lts({**data, "bike_lane_width_m": 1.5}, profile) == 2


def test_fr4_3_painted_lane_beside_class_parking_uses_table_3(profile):
    data = calm("painted_lane", 40.0, 3000, bike_lane_width_m=2.0, parking="unknown")
    assert profile.road_classes["residential"].parking.value
    assert edge_lts(data, profile) == 2
    assert edge_lts({**data, "parking": "no"}, profile) == 1


@pytest.mark.parametrize("facility", ["off_road", "protected"])
def test_fr4_6_paths_and_protected_lanes_are_aaa(profile, facility):
    assert is_aaa(edge(facility, 80.0), 1, profile)


def test_fr4_6_blocked_edge_is_not_aaa(profile):
    assert not is_aaa(edge("off_road", 10.0, bike_ok=False), 1, profile)


@pytest.mark.parametrize("facility", ["off_road", "protected", "none"])
def test_fr4_6_lts_above_one_is_not_aaa(profile, facility):
    assert not is_aaa(calm(facility), 2, profile)


@pytest.mark.parametrize(
    "speed, adt, nsw, generic",
    [
        (30.0, 2000, True, True),
        (30.0, 2001, False, False),
        (30.1, 1500, False, True),
        (40.0, 1500, False, True),
        (40.0, 1501, False, False),
        (40.1, 500, False, False),
    ],
)
def test_fr4_6_mixed_traffic_rules_per_profile(speed, adt, nsw, generic):
    data = calm("none", speed, adt)
    assert is_aaa(data, 1, load_profile("au-nsw")) is nsw
    assert is_aaa(data, 1, load_profile("generic")) is generic


@pytest.mark.parametrize("facility", ["shared", "none"])
def test_fr4_6_shared_and_bare_edges_use_mixed_rules(profile, facility):
    assert is_aaa(calm(facility, 20.0, 100), 1, profile)


def test_fr4_6_painted_lane_counts_only_when_profile_says_so(profile):
    data = calm("painted_lane", 20.0, 100, bike_lane_width_m=2.0)
    counted = replace(profile.aaa.painted_lanes_count, value=True)
    allowed = replace(profile, aaa=replace(profile.aaa, painted_lanes_count=counted))
    assert is_aaa(data, 1, allowed)
    assert not is_aaa(data, 1, profile)
    assert not is_aaa(data, 2, allowed)
