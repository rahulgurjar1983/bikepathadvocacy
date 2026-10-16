from bikeplan.config import load_profile, load_region
from bikeplan.fit import choose
from tests.test_fit_options import CASES, TOY_VERGE, street

PROFILE = load_profile("au-nsw", "profiles")
WEIGHTS = load_region("regions/test-grid.yaml").proposals.disruption_weights


def pick(data, free=True):
    return choose({**data, "length_m": 100.0}, PROFILE, WEIGHTS, free_separation=free)


def test_fr17_6_residential_link_takes_quietway_over_a_parking_removal_cycleway():
    result = pick(CASES[1])
    fits = {item["fix"] for item in result["candidates"] if item["accepted"]}
    assert {"quietway", "cycleway_parking_one_side"} <= fits
    assert result["fix"] == "quietway"
    assert result["needs_speed_approval"] is True
    assert result["speed_approval_body"] == "Transport for NSW"


def test_fr17_6_wide_link_takes_the_cycleway_in_spare_width():
    result = pick(street("residential", 14.0, 2, "yes", 50, 750))
    assert result["fix"] == "cycleway_in_spare"
    assert result["needs_speed_approval"] is False


def test_fr17_6_free_separated_fix_beats_a_cheaper_quietway():
    data = {**street("residential", 12.0, 2, "yes", 50, 750), "usable_verge": TOY_VERGE}
    result = pick(data)
    by_fix = {item["fix"]: item for item in result["candidates"]}
    assert by_fix["quietway"]["accepted"]
    assert by_fix["quietway"]["score"] < by_fix["verge_path"]["score"]
    assert result["fix"] == "verge_path"
    assert result["needs_speed_approval"] is False


def test_fr17_6_parking_removal_loses_to_the_least_disruptive_fix_when_no_free_one_fits():
    result = pick(CASES[3])
    assert result["fix"] == "cycleway_parking_one_side"
    taking = [item for item in result["candidates"] if item["accepted"]]
    assert result["score"] == min(item["score"] for item in taking)


def test_fr17_6_lane_removal_is_chosen_only_when_it_is_the_least_disruptive():
    result = pick(CASES[5])
    assert result["fix"] == "road_diet"
