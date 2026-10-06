import pytest

from bikeplan.config import load_profile
from bikeplan.fit import cross_section, options

PROFILE = load_profile("au-nsw", "profiles")


def street(highway, width, lanes, parking, speed, adt, reserve=None, oneway=False):
    return {
        "highway": highway,
        "width_m": width,
        "lanes_total": lanes,
        "lanes_dir": lanes if oneway else lanes // 2,
        "oneway": oneway,
        "parking:both": parking,
        "bike_facility": "none",
        "speed_kmh": speed,
        "adt": adt,
        "reserve_m": reserve,
    }


CASES = {
    1: street("residential", 12.0, 2, "yes", 50, 750),
    2: street("tertiary", 14.0, 2, "yes", 50, 5000),
    3: street("tertiary", 12.0, 2, "yes", 50, 5000),
    4: street("primary", 16.0, 4, "no", 60, 25000),
    5: street("primary", 13.0, 4, "no", 60, 15000),
    6: street("primary", 13.0, 4, "no", 60, 25000, reserve=27.0),
}


def by_fix(case):
    return {found["fix"]: found for found in options(CASES[case], PROFILE)}


@pytest.mark.parametrize("case", sorted(CASES))
def test_fr6_1_strips_add_up_to_the_carriageway(case):
    strips = cross_section(CASES[case], PROFILE)
    assert sum(strip["width_m"] for strip in strips) == pytest.approx(CASES[case]["width_m"])
    kinds = {"parking", "painted_lane", "through", "median", "spare"}
    assert all(strip["kind"] in kinds for strip in strips)


def test_fr6_1_strips_run_kerb_to_kerb_with_parking_outside():
    strips = cross_section(CASES[1], PROFILE)
    kinds = [strip["kind"] for strip in strips]
    assert kinds.count("parking") == 2
    assert kinds.count("through") == 2
    spare = [strip for strip in strips if strip["kind"] == "spare"]
    assert spare[0]["width_m"] == pytest.approx(1.8)


def test_fr6_1_painted_lanes_and_median_are_strips():
    data = {**CASES[4], "bike_facility": "painted_lane", "bike_lane_width_m": 1.5, "median_m": 2.0}
    strips = cross_section(data, PROFILE)
    kinds = [strip["kind"] for strip in strips]
    assert "painted_lane" in kinds
    assert "median" in kinds
    assert sum(strip["width_m"] for strip in strips) == pytest.approx(16.0)


def test_fr6_2_case_1_reasons():
    found = by_fix(1)
    assert set(found) == {
        "quietway",
        "cycleway_in_spare",
        "cycleway_parking_one_side",
        "cycleway_parking_both_sides",
        "road_diet",
        "verge_path",
    }
    assert found["quietway"]["fits"]
    assert not found["cycleway_in_spare"]["fits"]
    assert found["cycleway_in_spare"]["reason"] == "needs 3.5 m, spare 1.8 m"
    assert found["cycleway_in_spare"]["margin_m"] == pytest.approx(-1.7)
    assert found["cycleway_in_spare"]["spare_m"] == pytest.approx(1.8)
    assert not found["road_diet"]["fits"]
    assert found["road_diet"]["reason"] == "needs 2 lanes each way, has 1"
    assert not found["verge_path"]["fits"]
    assert found["verge_path"]["reason"] == "road reserve unknown"


def test_fr6_2_case_2_has_no_quietway_and_fits_in_spare():
    found = by_fix(2)
    assert not found["quietway"]["fits"]
    assert found["quietway"]["reason"] == "ADT 5000 is over 2000"
    assert found["cycleway_in_spare"]["fits"]
    assert found["cycleway_in_spare"]["spare_m"] == pytest.approx(3.8)
    assert found["cycleway_in_spare"]["needs_m"] == pytest.approx(3.5)
    assert found["cycleway_in_spare"]["margin_m"] == pytest.approx(0.3)


def test_fr6_2_case_3_needs_parking_gone_from_one_side():
    found = by_fix(3)
    assert not found["cycleway_in_spare"]["fits"]
    one = found["cycleway_parking_one_side"]
    assert one["fits"]
    assert one["spare_m"] == pytest.approx(3.9)
    assert one["needs_m"] == pytest.approx(3.0)
    both = found["cycleway_parking_both_sides"]
    assert both["fits"]
    assert both["spare_m"] == pytest.approx(6.0)


def test_fr6_2_case_5_road_diet_adds_a_lane_of_spare():
    found = by_fix(5)
    assert not found["cycleway_in_spare"]["fits"]
    diet = found["road_diet"]
    assert diet["fits"]
    assert diet["spare_m"] == pytest.approx(4.0)
    assert diet["needs_m"] == pytest.approx(4.0)


def test_fr6_2_case_6_road_diet_barred_by_adt_and_verge_path_fits():
    found = by_fix(6)
    assert not found["road_diet"]["fits"]
    assert found["road_diet"]["reason"] == "ADT 25000 is over 20000"
    verge = found["verge_path"]
    assert verge["fits"]
    assert verge["spare_m"] == pytest.approx(7.0)
    assert verge["needs_m"] == pytest.approx(4.5)


def test_fr6_2_verge_too_narrow_gives_reason():
    data = {**CASES[6], "reserve_m": 18.0}
    found = {f["fix"]: f for f in options(data, PROFILE)}
    assert not found["verge_path"]["fits"]
    assert found["verge_path"]["reason"] == "needs 3.5 m, spare 2.5 m"


def test_fr6_2_no_width_never_fits_a_cycleway():
    data = {**CASES[2], "width_m": None}
    found = {f["fix"]: f for f in options(data, PROFILE)}
    assert not found["cycleway_in_spare"]["fits"]
    assert found["cycleway_in_spare"]["reason"] == "width unknown"


def test_fr6_3_pair_wins_when_both_fit():
    data = {**CASES[4], "width_m": 20.0}
    found = {f["fix"]: f for f in options(data, PROFILE)}
    assert found["cycleway_in_spare"]["layout"] == "pair"


def test_fr6_3_desirable_widths_when_they_fit():
    data = {**CASES[4], "width_m": 20.0}
    found = {f["fix"]: f for f in options(data, PROFILE)}
    assert found["cycleway_in_spare"]["widths"] == "desirable"
    assert found["cycleway_in_spare"]["needs_m"] == pytest.approx(6.0)


def test_fr6_3_minimum_widths_when_only_those_fit():
    found = by_fix(4)["cycleway_in_spare"]
    assert found["layout"] == "pair"
    assert found["widths"] == "minimum"
    assert found["needs_m"] == pytest.approx(4.0)


def test_fr6_3_two_way_cycleway_when_the_pair_does_not_fit():
    found = by_fix(2)["cycleway_in_spare"]
    assert found["layout"] == "two_way"
    assert found["widths"] == "minimum"


def test_fr6_3_one_way_street_takes_the_two_way_cycleway():
    data = street("residential", 20.0, 2, "no", 50, 5000, oneway=True)
    found = {f["fix"]: f for f in options(data, PROFILE)}
    assert found["cycleway_in_spare"]["layout"] == "two_way"
    assert found["cycleway_in_spare"]["widths"] == "desirable"
