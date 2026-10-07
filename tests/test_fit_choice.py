import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.fit import choose, cross_section
from tests.test_fit_options import CASES, street

PROFILE = load_profile("au-nsw", "profiles")
WEIGHTS = load_region("regions/test-grid.yaml").proposals.disruption_weights


def pick(data, edges=None):
    return choose(data, PROFILE, WEIGHTS, edges)


def kinds(strips):
    return [strip["kind"] for strip in strips]


@pytest.mark.parametrize(
    ("case", "fix"),
    [
        (1, "quietway"),
        (2, "cycleway_in_spare"),
        (3, "cycleway_parking_one_side"),
        (4, "cycleway_in_spare"),
        (5, "road_diet"),
        (6, "verge_path"),
    ],
)
def test_fr6_7_worked_case_chooses_the_spec_fix(case, fix):
    result = pick({**CASES[case], "length_m": 100.0})
    assert result["status"] == "fix"
    assert result["fix"] == fix


def test_fr6_7_short_street_prefers_the_verge_path_to_parking_removal():
    result = pick({**CASES[3], "reserve_m": 27.0, "length_m": 100.0})
    assert result["fix"] == "verge_path"
    assert result["score"] == pytest.approx(0.5)


def test_fr6_7_verge_score_grows_with_the_street_length():
    result = pick({**CASES[3], "reserve_m": 27.0, "length_m": 1000.0})
    assert result["fix"] == "verge_path"
    assert result["score"] == pytest.approx(5.0)


def test_fr6_7_ties_go_to_the_fix_listed_first():
    result = pick({**CASES[1], "length_m": 0.0})
    assert result["fix"] == "quietway"
    assert result["candidates"][0]["score"] == result["candidates"][2]["score"] == 0


def test_fr6_7_no_fit_keeps_the_reasons():
    data = street("primary", 13.0, 4, "no", 60, 25000)
    result = pick({**data, "length_m": 100.0})
    assert result["status"] == "no_fit"
    assert result["fix"] is None
    assert any("reserve" in reason for reason in result["reasons"])
    assert len(result["reasons"]) == 6


def test_fr6_6_segment_that_is_aaa_on_its_own_needs_no_fix():
    data = street("residential", 12.0, 2, "yes", 30, 300)
    result = pick({**data, "length_m": 100.0})
    assert result["status"] == "aaa"
    assert result["fix"] is None


def test_fr6_6_fix_that_leaves_an_edge_above_lts_1_is_rejected():
    busy = {**CASES[1], "adt": 5000}
    result = pick({**CASES[1], "length_m": 100.0}, [CASES[1], busy])
    quiet = next(c for c in result["candidates"] if c["fix"] == "quietway")
    assert not quiet["accepted"]
    assert "not AAA" in quiet["rejected"]
    assert result["fix"] != "quietway"


def test_fr6_6_accepted_fix_has_no_rejection_reason():
    result = pick({**CASES[2], "length_m": 100.0})
    chosen = next(c for c in result["candidates"] if c["fix"] == "cycleway_in_spare")
    assert chosen["accepted"]
    assert chosen["rejected"] is None


def test_fr6_6_edge_that_bikes_may_not_use_is_not_rescored():
    banned = {**CASES[2], "bike_ok": False, "adt": 90000}
    result = pick({**CASES[2], "length_m": 100.0}, [CASES[2], banned])
    assert result["fix"] == "cycleway_in_spare"


def test_fr6_9_after_strips_put_the_pair_at_the_kerbs():
    result = pick({**CASES[4], "length_m": 100.0})
    after = result["after"]
    assert kinds(after) == [
        "cycleway",
        "separator",
        "through",
        "through",
        "through",
        "through",
        "separator",
        "cycleway",
    ]
    assert sum(s["width_m"] for s in after) == pytest.approx(16.0)
    assert after[0]["width_m"] == pytest.approx(1.5)
    assert after[1]["width_m"] == pytest.approx(0.5)


def test_fr6_9_after_strips_put_the_two_way_cycleway_on_the_unparked_side():
    result = pick({**CASES[3], "length_m": 100.0})
    after = result["after"]
    assert kinds(after) == [
        "cycleway",
        "separator",
        "through",
        "through",
        "parking",
        "spare",
    ]
    assert after[-1]["width_m"] == pytest.approx(0.9)
    assert after[0]["width_m"] == pytest.approx(2.5)
    assert sum(s["width_m"] for s in after) == pytest.approx(12.0)


def test_fr6_9_after_strips_keep_parking_beside_a_separator_of_its_width():
    result = pick({**CASES[2], "length_m": 100.0})
    after = result["after"]
    assert kinds(after)[:2] == ["cycleway", "separator"]
    assert kinds(after).count("parking") == 2
    assert sum(s["width_m"] for s in after) == pytest.approx(14.0)


def test_fr6_9_road_diet_after_strips_have_one_lane_fewer():
    result = pick({**CASES[5], "length_m": 100.0})
    assert kinds(result["after"]).count("through") == 3
    assert sum(s["width_m"] for s in result["after"]) == pytest.approx(13.0)


def test_fr6_9_before_strips_are_the_cross_section():
    result = pick({**CASES[1], "length_m": 100.0})
    assert result["before"] == cross_section(CASES[1], PROFILE)
