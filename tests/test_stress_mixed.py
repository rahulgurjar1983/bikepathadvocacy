import pytest

from bikeplan.stress import SPEED_TOPS_KMH, mixed_traffic_lts, speed_band, street_type

TABLE = {
    "A": [
        (750, [1, 1, 2, 2, 3, 3, 3]),
        (1500, [1, 1, 2, 3, 3, 3, 3]),
        (3000, [2, 2, 2, 3, 3, 4, 4]),
        (3001, [2, 2, 3, 3, 4, 4, 4]),
    ],
    "B": [
        (1000, [1, 1, 2, 2, 3, 3, 3]),
        (1500, [2, 2, 2, 3, 3, 4, 4]),
        (1501, [2, 3, 3, 3, 4, 4, 4]),
    ],
    "C": [
        (600, [1, 1, 2, 2, 3, 3, 3]),
        (1000, [2, 2, 2, 3, 3, 4, 4]),
        (1001, [2, 3, 3, 3, 4, 4, 4]),
    ],
    "D": [(8000, [3, 3, 3, 3, 4, 4, 4]), (8001, [3, 3, 4, 4, 4, 4, 4])],
    "E": [(1, [3, 3, 4, 4, 4, 4, 4])],
}
EDGES = {
    "A": {"highway": "residential", "oneway": False, "lanes_total": 2, "lanes_dir": 1},
    "B": {"highway": "tertiary", "oneway": False, "lanes_total": 2, "lanes_dir": 1},
    "C": {"highway": "tertiary", "oneway": True, "lanes_total": 1, "lanes_dir": 1},
    "D": {"highway": "secondary", "oneway": False, "lanes_total": 4, "lanes_dir": 2},
    "E": {"highway": "primary", "oneway": False, "lanes_total": 6, "lanes_dir": 3},
}
MIDDLE_KMH = [20.0, 42.0, 50.0, 58.0, 66.0, 74.0, 90.0]


def edge(kind, speed, adt):
    return {**EDGES[kind], "speed_kmh": speed, "adt": adt}


def test_fr4_1_every_cell_of_table_1():
    for kind, rows in TABLE.items():
        for adt, scores in rows:
            for speed, score in zip(MIDDLE_KMH, scores, strict=True):
                assert mixed_traffic_lts(edge(kind, speed, adt)) == score, (kind, adt, speed)


def test_fr4_1_row_edges_of_adt():
    assert mixed_traffic_lts(edge("A", 58.0, 750)) == 2
    assert mixed_traffic_lts(edge("A", 58.0, 751)) == 3
    assert mixed_traffic_lts(edge("A", 66.0, 1500)) == 3
    assert mixed_traffic_lts(edge("A", 66.0, 1501)) == 3
    assert mixed_traffic_lts(edge("B", 66.0, 1000)) == 3
    assert mixed_traffic_lts(edge("B", 90.0, 1001)) == 4
    assert mixed_traffic_lts(edge("D", 50.0, 8000)) == 3
    assert mixed_traffic_lts(edge("D", 50.0, 8001)) == 4


def test_fr4_1_band_edges():
    assert speed_band(37.82) == 1
    assert speed_band(37.83) == 2
    assert speed_band(45.87) == 2
    assert speed_band(45.88) == 3
    assert speed_band(78.05) == 6
    assert speed_band(78.06) == 7
    assert SPEED_TOPS_KMH == [37.82, 45.87, 53.91, 61.96, 70.01, 78.05]


def test_fr4_1_lts_changes_across_the_band_edge():
    assert mixed_traffic_lts(edge("A", 45.87, 700)) == 1
    assert mixed_traffic_lts(edge("A", 45.88, 700)) == 2
    assert mixed_traffic_lts(edge("A", 37.82, 3500)) == 2
    assert mixed_traffic_lts(edge("A", 37.83, 3500)) == 2
    assert mixed_traffic_lts(edge("A", 45.88, 3500)) == 3
    assert mixed_traffic_lts(edge("A", 53.91, 700)) == 2
    assert mixed_traffic_lts(edge("A", 53.92, 700)) == 2
    assert mixed_traffic_lts(edge("A", 61.96, 700)) == 2
    assert mixed_traffic_lts(edge("A", 61.97, 700)) == 3


def test_fr4_1_three_lanes_each_way_is_type_e():
    assert street_type({**EDGES["E"], "lanes_dir": 3}) == "E"
    assert street_type({**EDGES["E"], "lanes_dir": 4}) == "E"


def test_fr4_1_two_lanes_each_way_is_type_d():
    assert street_type({**EDGES["D"], "oneway": False, "lanes_dir": 2}) == "D"


def test_fr4_1_two_lane_one_way_is_type_d():
    assert (
        street_type({"oneway": True, "lanes_total": 2, "lanes_dir": 2, "highway": "primary"}) == "D"
    )


def test_fr4_1_one_way_one_lane_is_narrow_type_c():
    assert street_type(EDGES["C"]) == "C"
    assert street_type({**EDGES["C"], "width_tag_m": 4.56}) == "C"


@pytest.mark.parametrize(
    "tags, width, kind",
    [
        ({}, 4.57, "B"),
        ({}, 4.56, "C"),
        ({"parking:left": "lane"}, 6.71, "B"),
        ({"parking:left": "lane"}, 6.70, "C"),
        ({"parking:right": "lane"}, 6.71, "B"),
        ({"parking:both": "lane"}, 9.14, "B"),
        ({"parking:both": "lane"}, 9.13, "C"),
        ({"parking:lane:both": "parallel"}, 9.14, "B"),
        ({"parking:left": "no"}, 4.57, "B"),
    ],
)
def test_fr4_1_wide_one_way_is_type_b(tags, width, kind):
    data = {**EDGES["C"], **tags, "width_tag_m": width}
    assert street_type(data) == kind


def test_fr4_1_two_way_no_centre_line_is_type_a():
    assert street_type({**EDGES["B"], "lane_markings": "no"}) == "A"
    assert street_type({**EDGES["B"], "highway": "secondary", "lane_markings": "no"}) == "A"


@pytest.mark.parametrize("highway", ["residential", "living_street", "service", "unclassified"])
def test_fr4_1_untagged_lanes_on_minor_road_is_type_a(highway):
    assert street_type({**EDGES["B"], "highway": highway}) == "A"


def test_fr4_1_tagged_lanes_make_minor_road_type_b():
    assert street_type({**EDGES["B"], "highway": "residential", "lanes": "2"}) == "B"


def test_fr4_1_busier_class_is_type_b_without_tag():
    assert street_type({**EDGES["B"], "highway": "tertiary"}) == "B"


def test_fr4_1_lane_markings_yes_is_not_type_a():
    assert street_type({**EDGES["B"], "highway": "tertiary", "lane_markings": "yes"}) == "B"
