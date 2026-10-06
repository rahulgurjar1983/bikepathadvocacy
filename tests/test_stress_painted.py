import pytest

from bikeplan.stress import painted_lane_lts, parking_beside

MIDDLE_KMH = [20.0, 42.0, 50.0, 58.0, 66.0, 74.0, 90.0]
TABLE_2 = [
    ("one", 1.83, [1, 1, 1, 2, 3, 3, 3]),
    ("one", 1.82, [2, 2, 2, 2, 3, 3, 4]),
    ("two", 1.83, [2, 2, 2, 2, 3, 3, 3]),
    ("two", 1.82, [2, 2, 2, 2, 3, 4, 4]),
    ("three", 1.5, [3, 3, 3, 3, 4, 4, 4]),
    ("three", 2.5, [3, 3, 3, 3, 4, 4, 4]),
]
TABLE_3 = [
    ("one", 4.57, [1, 1, 2, 2, 3, 3, 3]),
    ("one", 4.56, [2, 2, 2, 3, 3, 3, 3]),
    ("oneway2", 4.57, [2, 2, 3, 3, 3, 3, 3]),
    ("oneway2", 4.56, [3, 3, 3, 3, 3, 3, 3]),
    ("two", 4.57, [2, 2, 3, 3, 3, 3, 3]),
    ("two", 4.56, [3, 3, 3, 3, 3, 3, 3]),
    ("many", 6.0, [3, 3, 3, 3, 3, 3, 3]),
]
BASE = {"bike_facility": "painted_lane", "adt": 100, "highway": "tertiary"}
ROADS = {
    "one": {"oneway": False, "lanes_total": 2, "lanes_dir": 1},
    "two": {"oneway": False, "lanes_total": 4, "lanes_dir": 2},
    "three": {"oneway": False, "lanes_total": 6, "lanes_dir": 3},
    "oneway2": {"oneway": True, "lanes_total": 2, "lanes_dir": 2},
    "many": {"oneway": False, "lanes_total": 6, "lanes_dir": 3},
}
PARKING_M = 2.1


def lane(road, speed, width=None, parking="no", **extra):
    return {
        **BASE,
        **ROADS[road],
        "speed_kmh": speed,
        "bike_lane_width_m": width,
        "parking": parking,
        **extra,
    }


def score(data, class_parking=False):
    return painted_lane_lts(data, PARKING_M, class_parking)


@pytest.mark.parametrize("road, width, scores", TABLE_2)
def test_fr4_2_every_cell_of_table_2(road, width, scores):
    for speed, want in zip(MIDDLE_KMH, scores, strict=True):
        got = score(lane(road, speed, width, adt=100000))
        assert got == want, (road, width, speed)


@pytest.mark.parametrize("road, reach, scores", TABLE_3)
def test_fr4_2_every_cell_of_table_3(road, reach, scores):
    for speed, want in zip(MIDDLE_KMH, scores, strict=True):
        got = score(lane(road, speed, reach - PARKING_M, "yes", adt=100000))
        assert got == want, (road, reach, speed)


def test_fr4_2_contraflow_lane_uses_the_one_lane_rows():
    data = {**lane("one", 58.0, 1.83), "lanes_dir": 0, "contraflow": True, "oneway": True}
    assert score(data) == 2
    data = {**lane("one", 66.0, 1.83), "lanes_dir": 0, "contraflow": True, "oneway": True}
    assert score(data) == 3


def test_fr4_2_untagged_lane_width_counts_as_under_1_83():
    assert score(lane("one", 42.0, None, adt=100000)) == 2
    assert score(lane("one", 42.0, 1.83, adt=100000)) == 1


def test_fr4_2_untagged_reach_counts_as_under_4_57():
    assert score(lane("one", 42.0, None, "yes", adt=100000)) == 2


def test_fr4_2_narrow_lane_uses_table_1():
    assert score(lane("one", 42.0, 1.21, adt=100)) == 1
    assert score(lane("one", 42.0, 1.22, adt=100000)) == 2
    assert score(lane("two", 42.0, 1.21, adt=100)) == 3


def test_fr4_2_short_reach_uses_table_1():
    assert score(lane("one", 42.0, 1.55, "yes", adt=100)) == 1
    assert score(lane("one", 42.0, 1.56, "yes", adt=100000)) == 2


def test_fr4_2_table_1_wins_when_lower():
    assert score(lane("one", 20.0, 1.5, adt=100)) == 1
    assert score(lane("one", 20.0, 1.5, adt=100000)) == 2
    assert score(lane("one", 20.0, 3.0, "yes", adt=100)) == 1


def test_fr4_2_parking_yes_when_tagged_or_class_default():
    assert parking_beside({"parking": "yes"}, False)
    assert not parking_beside({"parking": "no"}, True)
    assert parking_beside({"parking": "unknown"}, True)
    assert not parking_beside({"parking": "unknown"}, False)


def test_fr4_2_unknown_parking_follows_class_default():
    data = lane("one", 42.0, 3.0, "unknown", adt=100000)
    assert score(data, class_parking=False) == 1
    assert score(data, class_parking=True) == 1
    data = lane("one", 58.0, 2.0, "unknown", adt=100000)
    assert score(data, class_parking=False) == 2
    assert score(data, class_parking=True) == 3
