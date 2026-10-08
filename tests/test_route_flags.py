import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.review import route_figures
from bikeplan.route import read_route
from tests.route_helpers import (
    REGION,
    densify,
    edited_snapshot,
    gate_on_way,
    lonlat,
    way_tags,
    write_gpx_track,
)


@pytest.fixture(scope="module")
def profile():
    return load_profile(load_region(REGION).profile, "profiles")


def flags(tmp_path, profile, edit, points):
    folder = edited_snapshot(tmp_path, edit)
    graph = build(folder, load_region(REGION), profile)
    path = write_gpx_track(tmp_path / "r.gpx", lonlat(densify(points)))
    return route_figures(graph, profile, read_route(path))["total"]["flags"]


def test_fr14_10_route_on_a_street_with_opening_hours_is_flagged(tmp_path, profile):
    def edit(xml):
        return way_tags(xml, 2001, {"opening_hours": "Mo-Fr 07:00-19:00"})

    result = flags(tmp_path, profile, edit, [(200, 0), (200, 200)])
    assert [f["tag"] for f in result] == ["opening_hours=Mo-Fr 07:00-19:00"]
    assert result[0]["length_m"] == pytest.approx(200)


def test_fr14_10_route_through_a_private_gate_is_flagged_on_that_edge_only(tmp_path, profile):
    def edit(xml):
        return gate_on_way(xml, 2000, 1000, (0, 100), {"barrier": "gate", "access": "private"})

    result = flags(tmp_path, profile, edit, [(0, 0), (0, 400)])
    assert [f["tag"] for f in result] == ["barrier=gate access=private"]
    assert result[0]["lonlat"] == pytest.approx(lonlat([(0, 100)])[0], abs=5e-5)


def test_fr14_10_route_on_a_private_access_street_open_to_bikes_is_flagged(tmp_path, profile):
    def edit(xml):
        return way_tags(xml, 2002, {"access": "private", "bicycle": "yes"})

    result = flags(tmp_path, profile, edit, [(600, 0), (600, 200)])
    assert [f["tag"] for f in result] == ["access=private"]


def test_fr14_10_open_streets_have_no_flags(tmp_path, profile):
    result = flags(tmp_path, profile, lambda xml: xml, [(0, 0), (0, 600)])
    assert result == []
