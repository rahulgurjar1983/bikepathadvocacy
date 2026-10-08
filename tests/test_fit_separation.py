import dataclasses

import pytest

from bikeplan.config import Fit, Num, load_profile, load_region
from bikeplan.fit import choose
from tests.test_fit_options import CASES, street

PROFILE = load_profile("au-nsw", "profiles")
GENERIC = load_profile("generic", "profiles")
WEIGHTS = load_region("regions/test-grid.yaml").proposals.disruption_weights
OFF = dataclasses.replace(
    PROFILE, fit=Fit(Num(False, "test", False), PROFILE.fit.speed_approval_body)
)
NARROW = street("residential", 7.0, 2, "no", 50, 750)


def pick(data, profile=PROFILE):
    return choose({**data, "length_m": 100.0}, profile, WEIGHTS)


@pytest.mark.parametrize("profile", [PROFILE, GENERIC])
def test_fr6_11_shipped_profiles_prefer_separation(profile):
    assert profile.fit.prefer_separation.value is True
    assert profile.fit.prefer_separation.assumption


def test_fr6_11_profiles_name_the_speed_approval_body():
    assert PROFILE.fit.speed_approval_body.value == "Transport for NSW"
    assert GENERIC.fit.speed_approval_body.value == "the road authority that sets speed limits"


def test_fr6_11_separated_fix_wins_over_a_cheaper_quietway():
    result = pick(CASES[1])
    quiet = next(c for c in result["candidates"] if c["fix"] == "quietway")
    assert quiet["accepted"]
    assert result["fix"] == "cycleway_parking_one_side"
    assert result["score"] > quiet["score"]
    assert result["needs_speed_approval"] is False
    assert result["speed_approval_body"] is None


def test_fr6_11_wide_street_gets_the_cycleway_in_spare():
    data = street("residential", 14.0, 2, "yes", 50, 750)
    assert pick(data)["fix"] == "cycleway_in_spare"


def test_fr6_11_quietway_is_the_fallback_and_needs_speed_approval():
    result = pick(NARROW)
    assert result["status"] == "fix"
    assert result["fix"] == "quietway"
    assert result["needs_speed_approval"] is True
    assert result["speed_approval_body"] == "Transport for NSW"


def test_fr6_11_generic_fallback_names_its_own_body():
    result = pick(NARROW, GENERIC)
    assert result["fix"] == "quietway"
    assert result["speed_approval_body"] == "the road authority that sets speed limits"


def test_fr6_11_least_disruptive_separated_fix_is_picked_among_separated():
    result = pick({**CASES[3], "reserve_m": 27.0})
    assert result["fix"] == "verge_path"


def test_fr6_11_off_keeps_the_least_disruptive_fix():
    result = pick(CASES[1], OFF)
    assert result["fix"] == "quietway"
    assert result["needs_speed_approval"] is True
