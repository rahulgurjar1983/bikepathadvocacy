import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.review import route_figures
from bikeplan.route import read_route
from tests.route_helpers import (
    REGION,
    SNAPSHOT,
    corner_route,
    densify,
    edited_snapshot,
    lonlat,
    way_tags,
    write_gpx_tracks,
)


@pytest.fixture(scope="module")
def region():
    return load_region(REGION)


@pytest.fixture(scope="module")
def profile(region):
    return load_profile(region.profile, "profiles")


@pytest.fixture(scope="module")
def graph(region, profile):
    return build(SNAPSHOT, region, profile)


def reviewed(graph, profile, region, tmp_path, tracks, snapshot=SNAPSHOT):
    path = write_gpx_tracks(
        tmp_path / "r.gpx", {name: lonlat(densify(points)) for name, points in tracks.items()}
    )
    return route_figures(graph, profile, read_route(path), region, snapshot)


def test_fr14_6_corner_route_needs_one_signal_and_has_0_4_km_with_no_fit(
    graph, profile, region, tmp_path
):
    total = reviewed(graph, profile, region, tmp_path, {"Corner": corner_route()})["total"]
    assert [(f["fix"], f["junction"]) for f in total["fixes"]] == [("signals", 1009)]
    assert total["disruption"]["signals"] == 1
    assert total["disruption"]["refuges"] == 0
    assert total["disruption"]["parking_spaces"] == 0
    assert total["disruption"]["lane_km"] == 0
    assert total["disruption"]["no_fit_km"] == pytest.approx(0.4)
    assert total["no_fit"][0]["street"] == "Main Road"


def test_fr14_6_a_street_that_needs_parking_removed_adds_its_spaces_per_segment(
    region, profile, tmp_path
):
    def edit(xml):
        return way_tags(xml.replace('<tag k="maxspeed" v="30"/>', "", 1), 2000, {"maxspeed": "50"})

    folder = edited_snapshot(tmp_path, edit)
    street = build(folder, region, profile)
    total = reviewed(street, profile, region, tmp_path, {"Up": [(0, 0), (0, 600)]}, folder)["total"]
    assert [f["fix"] for f in total["fixes"]] == ["cycleway_parking_both_sides"] * 3
    assert total["disruption"]["parking_spaces"] == 3 * 2 * round(200 / 6.0 * 0.7)
    assert total["disruption"]["fix_km"] == pytest.approx({"cycleway_parking_both_sides": 0.6})
    assert total["disruption"]["no_fit_km"] == 0


def test_fr14_6_a_section_keeps_its_own_fixes_and_the_total_adds_them(
    graph, profile, region, tmp_path
):
    found = reviewed(
        graph,
        profile,
        region,
        tmp_path,
        {"Corner": corner_route(), "Spur": [(200, 200), (600, 200)]},
    )
    assert [s["disruption"]["signals"] for s in found["sections"]] == [1, 1]
    assert found["total"]["disruption"]["signals"] == 2


def test_fr14_6_route_through_the_signal_gap_gives_750_people_safe_reach_to_the_school(
    graph, profile, region, tmp_path
):
    total = reviewed(graph, profile, region, tmp_path, {"Spur": [(200, 200), (600, 200)]})["total"]
    assert total["access"]["safe_people_gain"]["school"] == pytest.approx(750)
    assert total["access"]["safe_people_gain"]["library"] == 0
    assert total["access"]["homes_gaining_safe_reach"] == pytest.approx(750)
    assert total["access"]["gain_per_km"] == pytest.approx(750 / total["route_km"], rel=1e-3)


def test_fr14_6_corner_route_gives_no_safe_reach_gain(graph, profile, region, tmp_path):
    total = reviewed(graph, profile, region, tmp_path, {"Corner": corner_route()})["total"]
    assert total["access"]["homes_gaining_safe_reach"] == 0


def test_fr14_6_ranked_projects_of_the_same_length_are_compared(graph, profile, region, tmp_path):
    total = reviewed(graph, profile, region, tmp_path, {"Spur": [(200, 200), (600, 200)]})["total"]
    ranked = total["access"]["ranked"]
    assert ranked["projects"] == 1
    assert ranked["km"] == 0
    assert ranked["safe_people_gain"]["school"] == pytest.approx(750)


def test_fr14_6_without_a_region_the_figures_hold_no_fixes(graph, profile, tmp_path):
    path = write_gpx_tracks(tmp_path / "r.gpx", {"C": lonlat(densify(corner_route()))})
    total = route_figures(graph, profile, read_route(path))["total"]
    assert "fixes" not in total
