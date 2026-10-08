import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.review import route_figures
from bikeplan.route import read_route
from tests.route_helpers import REGION, SNAPSHOT, corner_route, densify, lonlat, write_gpx_track


@pytest.fixture(scope="module")
def graph():
    region = load_region(REGION)
    return build(SNAPSHOT, region, load_profile(region.profile, "profiles"))


@pytest.fixture(scope="module")
def profile():
    return load_profile(load_region(REGION).profile, "profiles")


def total(graph, profile, tmp_path, points):
    path = write_gpx_track(tmp_path / "r.gpx", lonlat(densify(points)))
    return route_figures(graph, profile, read_route(path))["total"]


def test_fr14_5_route_across_the_main_road_has_one_unsignalised_crossing(graph, profile, tmp_path):
    result = total(graph, profile, tmp_path, [(200, 200), (600, 200)])
    assert result["crossings_unsignalised"] == 1
    (crossing,) = result["crossings"]
    assert crossing["road"] == "Main Road"
    assert crossing["lts"] == 3
    assert crossing["signal"] is False
    assert crossing["refuge"] is False
    assert crossing["lonlat"] == pytest.approx(lonlat([(400, 200)])[0], abs=2e-5)


def test_fr14_5_signalised_crossing_is_listed_but_not_counted(graph, profile, tmp_path):
    result = total(graph, profile, tmp_path, [(200, 600), (600, 600)])
    assert result["crossings_unsignalised"] == 0
    (crossing,) = result["crossings"]
    assert crossing["signal"] is True
    assert crossing["lts"] == 1
    assert crossing["road"] == "Main Road"


def test_fr14_5_joining_the_main_road_from_a_side_street_is_a_crossing(graph, profile, tmp_path):
    result = total(graph, profile, tmp_path, corner_route())
    assert result["crossings_unsignalised"] == 1
    assert result["crossings"][0]["lonlat"] == pytest.approx(lonlat([(400, 0)])[0], abs=2e-5)


def test_fr14_5_route_along_side_streets_has_no_crossing(graph, profile, tmp_path):
    result = total(graph, profile, tmp_path, [(0, 0), (0, 600)])
    assert result["crossings"] == []
    assert result["crossings_unsignalised"] == 0
