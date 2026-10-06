import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.fit import disruption_score, options
from tests.test_fit_options import CASES, street

PROFILE = load_profile("au-nsw", "profiles")
WEIGHTS = load_region("regions/test-grid.yaml").proposals.disruption_weights


def found_for(data):
    return {f["fix"]: f for f in options(data, PROFILE)}


def test_fr6_4_fix_that_fits_at_the_low_width_is_robust():
    data = {**CASES[2], "width_low_m": 13.8}
    assert found_for(data)["cycleway_in_spare"]["robust"] == "robust"


def test_fr6_4_fix_that_fits_only_at_the_high_width_is_check_on_site():
    data = {**CASES[2], "width_low_m": 13.0}
    found = found_for(data)["cycleway_in_spare"]
    assert found["fits"]
    assert found["robust"] == "check on site"


def test_fr6_4_fix_that_does_not_fit_has_no_robust_flag():
    data = {**CASES[2], "width_low_m": 13.0}
    assert found_for(data)["road_diet"]["robust"] is None


def test_fr6_4_without_a_low_width_the_width_is_used():
    assert found_for(CASES[2])["cycleway_in_spare"]["robust"] == "robust"
    assert found_for(CASES[4])["cycleway_in_spare"]["robust"] == "robust"


def test_fr6_5_parking_spaces_for_one_side_of_120_m():
    data = {**CASES[3], "length_m": 120.0}
    one = found_for(data)["cycleway_parking_one_side"]
    assert one["disruption"]["parking_spaces"] == 14


def test_fr6_5_parking_spaces_for_both_sides_of_120_m():
    data = {**CASES[3], "length_m": 120.0}
    both = found_for(data)["cycleway_parking_both_sides"]
    assert both["disruption"]["parking_spaces"] == 28


def test_fr6_5_fix_that_keeps_parking_removes_no_spaces():
    data = {**CASES[2], "length_m": 120.0}
    assert found_for(data)["cycleway_in_spare"]["disruption"]["parking_spaces"] == 0


def test_fr6_5_road_diet_counts_lane_km_and_vehicle_km():
    data = {**CASES[5], "length_m": 500.0}
    counts = found_for(data)["road_diet"]["disruption"]
    assert counts["lane_km"] == pytest.approx(0.5)
    assert counts["vehicle_km"] == pytest.approx(7500.0)


def test_fr6_5_quietway_counts_km_of_lower_speed_with_old_and_new_speed():
    data = {**CASES[1], "length_m": 250.0}
    counts = found_for(data)["quietway"]["disruption"]
    assert counts["speed_km"] == pytest.approx(0.25)
    assert counts["old_speed_kmh"] == 50
    assert counts["new_speed_kmh"] == 30


def test_fr6_5_verge_path_counts_km_of_path():
    data = {**CASES[6], "length_m": 100.0}
    assert found_for(data)["verge_path"]["disruption"]["path_km"] == pytest.approx(0.1)


def test_fr6_5_cycleway_in_spare_has_zero_score():
    data = {**CASES[2], "length_m": 300.0}
    found = found_for(data)["cycleway_in_spare"]
    assert disruption_score(found["disruption"], WEIGHTS) == 0


def test_fr6_5_score_is_the_weighted_sum():
    data = {**CASES[3], "length_m": 120.0}
    counts = found_for(data)["cycleway_parking_one_side"]["disruption"]
    assert disruption_score(counts, WEIGHTS) == pytest.approx(14 * WEIGHTS.parking_space)


def test_fr6_5_verge_score_beats_parking_on_a_short_street():
    data = {**CASES[3], "reserve_m": 27.0, "length_m": 100.0}
    found = found_for(data)
    verge = disruption_score(found["verge_path"]["disruption"], WEIGHTS)
    parking = disruption_score(found["cycleway_parking_one_side"]["disruption"], WEIGHTS)
    assert verge == pytest.approx(0.5)
    assert parking == pytest.approx(12.0)


def test_fr6_5_one_side_parking_street_counts_spaces_for_one_side():
    data = {**street("tertiary", 12.0, 2, "no", 50, 5000), "parking:left": "yes", "length_m": 60.0}
    found = found_for(data)["cycleway_parking_one_side"]
    assert found["disruption"]["parking_spaces"] == 7
