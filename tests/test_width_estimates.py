import pytest

from bikeplan.config import load_profile
from bikeplan.width import estimates, lane_estimate, tag_estimate

PROFILE = load_profile("au-nsw", "profiles")


def street(**extra):
    return {"highway": "residential", "lanes_total": 2, "lanes_dir": 1, **extra}


def test_fr5_1_lanes_only_use_lane_width_plus_margin():
    found = lane_estimate(street(**{"parking:both": "no"}), PROFILE)
    assert found.source == "lanes"
    assert found.confidence == "low"
    assert (found.width_m, found.low_m, found.high_m) == pytest.approx((6.6, 5.6, 8.1))


def test_fr5_1_each_tagged_parking_side_adds_a_parking_lane():
    one = lane_estimate(street(highway="primary", **{"parking:left": "lane"}), PROFILE)
    both = lane_estimate(street(**{"parking:both": "lane"}), PROFILE)
    assert one.width_m == pytest.approx(8.7)
    assert both.width_m == pytest.approx(10.8)
    assert (both.low_m, both.high_m) == pytest.approx((9.8, 12.3))


def test_fr5_1_untagged_parking_follows_the_class_default():
    assert PROFILE.road_classes["residential"].parking.value
    assert not PROFILE.road_classes["primary"].parking.value
    residential = lane_estimate(street(), PROFILE)
    primary = lane_estimate(street(highway="primary"), PROFILE)
    assert residential.width_m == pytest.approx(6.6 + 2 * 2.1)
    assert primary.width_m == pytest.approx(6.6)


def test_fr5_1_tagged_no_parking_beats_the_class_default():
    found = lane_estimate(street(**{"parking:both": "no"}), PROFILE)
    assert found.width_m == pytest.approx(6.6)


def test_fr5_1_each_painted_lane_adds_one_and_a_half_metres():
    one = lane_estimate(street(**{"cycleway:left": "lane", "parking:both": "no"}), PROFILE)
    both = lane_estimate(street(**{"cycleway:both": "lane", "parking:both": "no"}), PROFILE)
    assert one.width_m == pytest.approx(8.1)
    assert both.width_m == pytest.approx(9.6)


def test_fr5_1_a_road_with_no_lanes_has_no_lane_estimate():
    assert lane_estimate(street(lanes_total=0, highway="cycleway"), PROFILE) is None


def test_fr5_2_a_width_tag_gives_plus_or_minus_half_a_metre():
    found = tag_estimate({"width_tag_m": 9.0})
    assert found.source == "osm_tag"
    assert found.confidence == "medium"
    assert (found.width_m, found.low_m, found.high_m) == (9.0, 8.5, 9.5)


def test_fr5_2_no_tag_gives_no_estimate():
    assert tag_estimate({"width_tag_m": None}) is None


@pytest.mark.parametrize("metres", [1.0, 2.9, 41.0])
def test_fr5_7_a_tag_out_of_range_is_dropped_with_a_reason(metres):
    kept, dropped = estimates(street(width_tag_m=metres, **{"parking:both": "no"}), PROFILE)
    assert [item.source for item in kept] == ["lanes"]
    assert dropped == [("osm_tag", f"{metres:g} m is outside 3 m to 40 m")]


def test_fr5_7_the_limits_themselves_are_kept():
    for metres in (3.0, 40.0):
        kept, dropped = estimates(street(width_tag_m=metres), PROFILE)
        assert "osm_tag" in [item.source for item in kept]
        assert dropped == []


def test_fr5_7_a_lane_estimate_out_of_range_is_dropped():
    kept, dropped = estimates(street(lanes_total=12, **{"parking:both": "lane"}), PROFILE)
    assert kept == []
    assert dropped[0][0] == "lanes"
    assert "outside 3 m to 40 m" in dropped[0][1]
