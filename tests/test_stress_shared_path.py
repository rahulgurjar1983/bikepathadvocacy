import pytest

from bikeplan.config import load_profile
from bikeplan.stress import edge_aaa, edge_reason, own_lts

PROFILES = ["au-nsw", "generic"]


def path(highway="path", width=None, **extra):
    return {
        "highway": highway,
        "bike_ok": True,
        "bike_facility": "none",
        "lanes_total": 0,
        "width_tag_m": width,
        **extra,
    }


@pytest.fixture(params=PROFILES)
def profile(request):
    return load_profile(request.param)


@pytest.mark.parametrize("highway", ["path", "footway"])
def test_fr4_10_wide_shared_path_is_aaa(profile, highway):
    minimum = profile.widths_m.two_way_cycleway.min.value
    data = path(highway, minimum)
    assert own_lts(data, profile) == 1
    assert edge_aaa(data, 1, profile)
    reason = edge_reason(data, profile, 1, 1, None)
    assert reason == f"shared path, {minimum:g} m wide -> LTS 1; AAA: path is wide enough"


@pytest.mark.parametrize("highway", ["path", "footway"])
def test_fr4_10_narrow_shared_path_is_level_one_but_not_aaa(profile, highway):
    minimum = profile.widths_m.two_way_cycleway.min.value
    data = path(highway, minimum - 0.1)
    assert own_lts(data, profile) == 1
    assert not edge_aaa(data, 1, profile)
    reason = edge_reason(data, profile, 1, 1, None)
    assert reason.endswith(f"not AAA: path is narrower than {minimum:g} m")
    assert "no motor traffic data" not in reason


def test_fr4_10_shared_path_with_no_width_is_aaa_and_flags_the_width(profile):
    data = path()
    assert edge_aaa(data, 1, profile)
    reason = edge_reason(data, profile, 1, 1, None)
    assert reason == "shared path, width unknown -> LTS 1; AAA: path is wide enough (width unknown)"


def test_fr4_10_shared_path_raised_by_a_crossing_is_not_aaa(profile):
    assert not edge_aaa(path(width=3.0), 2, profile)


def test_fr4_10_path_bikes_may_not_use_is_not_aaa_and_keeps_the_old_reason(profile):
    data = path(bike_ok=False)
    assert not edge_aaa(data, 1, profile)
    assert edge_reason(data, profile, 1, 1, None).endswith("not AAA: no motor traffic data")


def test_fr4_10_path_is_never_judged_by_street_speed_and_traffic(profile):
    data = path(width=3.0, speed_kmh=80.0, adt=30000, lanes_total=2)
    assert own_lts(data, profile) == 1
    assert edge_aaa(data, 1, profile)
