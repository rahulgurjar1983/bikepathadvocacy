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
    lonlat,
    write_gpx_track,
    write_gpx_tracks,
)


@pytest.fixture(scope="module")
def graph():
    region = load_region(REGION)
    return build(SNAPSHOT, region, load_profile(region.profile, "profiles"))


@pytest.fixture(scope="module")
def profile():
    return load_profile(load_region(REGION).profile, "profiles")


def figures(graph, profile, tmp_path, tracks):
    path = write_gpx_tracks(
        tmp_path / "r.gpx", {name: lonlat(densify(points)) for name, points in tracks.items()}
    )
    return route_figures(graph, profile, read_route(path))


def set_facility(graph, ends, facility):
    for u, v, _, data in graph.edges(keys=True, data=True):
        if {u, v} == set(ends):
            data["bike_facility"] = facility
            if facility == "protected":
                data["bike_lane_width_m"] = 1.5
                data["bicycle"] = "designated"


def test_fr14_4_corner_route_gives_the_hand_worked_km_by_facility_and_level(
    graph, profile, tmp_path
):
    total = figures(graph, profile, tmp_path, {"Corner": corner_route()})["total"]
    assert total["km_by_facility"] == pytest.approx(
        {"separated": 0, "painted": 0, "shared": 0.8, "off_network": 0}
    )
    assert total["km_by_lts"] == pytest.approx({"1": 0.2, "2": 0, "3": 0.2, "4": 0.4})
    assert total["km_aaa"] == pytest.approx(0.2)
    assert total["route_km"] == pytest.approx(0.8, abs=0.001)


def test_fr14_4_corner_route_has_one_break_from_the_first_junction_to_the_end(
    graph, profile, tmp_path
):
    breaks = figures(graph, profile, tmp_path, {"Corner": corner_route()})["total"]["breaks"]
    assert len(breaks) == 1
    assert breaks[0]["length_m"] == pytest.approx(600, abs=0.5)
    assert breaks[0]["lonlat"] == pytest.approx(lonlat([(200, 0)])[0], abs=2e-5)


def test_fr14_4_facility_classes_and_a_painted_lane_break(graph, profile, tmp_path):
    local = graph.copy()
    set_facility(local, (1000, 1001), "protected")
    set_facility(local, (1001, 1002), "painted_lane")
    total = figures(local, profile, tmp_path, {"Edge": [(0, 0), (0, 600)]})["total"]
    assert total["km_by_facility"] == pytest.approx(
        {"separated": 0.2, "painted": 0.2, "shared": 0.2, "off_network": 0}
    )
    assert sum(total["km_by_lts"].values()) == pytest.approx(0.6)
    assert total["km_aaa"] == pytest.approx(0.4)
    assert [b["length_m"] for b in total["breaks"]] == pytest.approx([200], abs=0.5)
    assert total["breaks"][0]["lonlat"] == pytest.approx(lonlat([(0, 200)])[0], abs=2e-5)


def test_fr14_4_off_network_stretch_is_its_own_class_and_a_break(graph, profile, tmp_path):
    total = figures(graph, profile, tmp_path, {"Off": [(0, 0), (200, 0), (200, -100)]})["total"]
    assert total["km_by_facility"]["off_network"] == pytest.approx(0.07, abs=0.001)
    assert total["km_by_facility"]["shared"] == pytest.approx(0.2)
    assert total["km_aaa"] == pytest.approx(0.2)
    assert sum(total["km_by_lts"].values()) == pytest.approx(0.2)
    assert len(total["breaks"]) == 1
    assert total["breaks"][0]["length_m"] == pytest.approx(70, abs=1)
    assert total["breaks"][0]["lonlat"] == pytest.approx(lonlat([(200, -30)])[0], abs=2e-5)
    assert total["matched_share"] == pytest.approx(230 / 300, abs=0.01)


def test_fr14_4_totals_add_up_the_sections(graph, profile, tmp_path):
    result = figures(
        graph, profile, tmp_path, {"Corner": corner_route(), "North": [(0, 0), (0, 600)]}
    )
    assert [s["name"] for s in result["sections"]] == ["Corner", "North"]
    north = result["sections"][1]
    assert north["km_aaa"] == pytest.approx(0.6)
    assert north["breaks"] == []
    assert result["total"]["km_aaa"] == pytest.approx(0.8)
    assert result["total"]["km_by_facility"]["shared"] == pytest.approx(1.4)
    assert len(result["total"]["breaks"]) == 1


def test_fr14_4_route_figures_command_writes_the_json(graph, tmp_path, capsys):
    import json

    from bikeplan import main

    route = write_gpx_track(tmp_path / "r.gpx", lonlat(densify(corner_route())))
    out = tmp_path / "out"
    code = main(
        [
            "route",
            "figures",
            str(route),
            "--region",
            REGION,
            "--snapshot",
            SNAPSHOT,
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert capsys.readouterr().out.strip() == str(out / "route_figures.json")
    written = json.loads((out / "route_figures.json").read_text())
    assert written["total"]["km_aaa"] == pytest.approx(0.2)
    assert written["sections"][0]["name"] == "Test route"


def test_fr14_4_route_figures_command_names_a_file_with_no_line(tmp_path, capsys):
    from bikeplan import main

    empty = tmp_path / "empty.geojson"
    empty.write_text('{"type": "FeatureCollection", "features": []}')
    code = main(
        [
            *["route", "figures", str(empty), "--region", REGION, "--snapshot", SNAPSHOT],
            *["--out", str(tmp_path / "out")],
        ]
    )
    assert code == 1
    assert "empty.geojson" in capsys.readouterr().err
