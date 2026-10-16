import json

import pytest
from shapely.geometry import LineString, Point, box

from bikeplan import main
from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.route import Section
from tests.route_helpers import (
    REGION,
    SNAPSHOT,
    corner_route,
    densify,
    lonlat,
    write_geojson,
)

LINE = LineString([(0, 0), (1000, 0)])
EVERYWHERE = box(-9000, -9000, 9000, 9000)


def unit(name, x, y, people):
    return {"id": name, "polygon": Point(x, y).buffer(10), "people": people}


@pytest.fixture(scope="module")
def graph():
    region = load_region(REGION)
    return build(SNAPSHOT, region, load_profile(region.profile, "profiles"))


def section(points):
    return Section("North", lonlat(densify(points)))


def test_fr18_7_people_within_500_m_and_1_km_of_the_line_are_hand_worked_shares():
    from bikeplan.review_measures import people_reach

    units = [
        unit("near", 500, 300, 100),
        unit("mid", 500, 800, 50),
        unit("far", 500, 1500, 50),
        unit("outside", 500, 200, 999),
    ]
    units[3]["polygon"] = Point(500, 20000).buffer(10)
    found = people_reach(units, [LINE], EVERYWHERE)
    assert found["people"] == 200
    assert found["within_500_m"] == pytest.approx(0.5)
    assert found["within_1000_m"] == pytest.approx(0.75)


def test_fr18_7_people_reach_counts_a_unit_once_for_two_lines():
    from bikeplan.review_measures import people_reach

    units = [unit("a", 500, 300, 100), unit("b", 500, 5000, 100)]
    other = LineString([(0, 400), (1000, 400)])
    found = people_reach(units, [LINE, other], EVERYWHERE)
    assert found["within_500_m"] == pytest.approx(0.5)


def test_fr18_7_people_reach_with_no_residents_is_unknown_not_zero():
    from bikeplan.review_measures import people_reach

    found = people_reach([], [LINE], EVERYWHERE)
    assert found == {"people": 0, "within_500_m": None, "within_1000_m": None}


def test_fr18_7_schools_within_100_m_are_counted_with_the_total():
    from bikeplan.review_measures import schools_near

    schools = [(100, 50), (500, 90), (500, 150), (1500, 0)]
    assert schools_near(schools, [LINE]) == {"schools": 4, "within_100_m": 2}


def test_fr18_7_paved_unpaved_and_shared_street_km_are_hand_worked(graph):
    from bikeplan.review_measures import graph_measures

    local = graph.copy()
    for ends, facility, highway, surface in (
        ((1000, 1001), "protected", None, "asphalt"),
        ((1001, 1002), "off_road", "path", "grass"),
    ):
        for u, v, _, data in local.edges(keys=True, data=True):
            if {u, v} == set(ends):
                data["bike_facility"] = facility
                data["surface"] = surface
                if highway:
                    data["highway"] = highway
    found = graph_measures(
        local, load_profile(load_region(REGION).profile, "profiles"), [section([(0, 0), (0, 600)])]
    )
    assert found["route_km"] == pytest.approx(0.6, abs=0.001)
    assert found["paved_offroad_km"] == pytest.approx(0.2)
    assert found["unpaved_km"] == pytest.approx(0.2)
    assert sum(found["shared_street_km_by_lts"].values()) == pytest.approx(0.2)
    assert found["shared_street_km_by_lts"]["1"] == pytest.approx(0.2)
    assert found["paved_offroad_share"] == pytest.approx(0.2 / 0.6, abs=0.01)


def test_fr18_7_corner_route_has_only_shared_street_km_by_level(graph):
    from bikeplan.review_measures import graph_measures

    profile = load_profile(load_region(REGION).profile, "profiles")
    found = graph_measures(graph, profile, [section(corner_route())])
    assert found["paved_offroad_km"] == 0
    assert found["unpaved_km"] == 0
    assert found["shared_street_km_by_lts"] == pytest.approx({"1": 0.2, "2": 0, "3": 0.2, "4": 0.4})


def test_fr18_7_measures_command_writes_the_people_school_and_street_figures(tmp_path, capsys):
    route = write_geojson(tmp_path / "r.geojson", lonlat(densify(corner_route())))
    out = tmp_path / "out"
    code = main(
        [
            "route",
            "measures",
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
    assert capsys.readouterr().out.strip() == str(out / "measures.json")
    written = json.loads((out / "measures.json").read_text())
    assert written["route_km"] == pytest.approx(0.8, abs=0.001)
    assert written["schools"] == {"schools": 1, "within_100_m": 0}
    assert written["people"]["within_1000_m"] >= written["people"]["within_500_m"]
    assert written["crossings_unsignalised"] >= 0


def test_fr18_7_measures_command_names_a_file_with_no_line(tmp_path, capsys):
    empty = tmp_path / "empty.geojson"
    empty.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    code = main(
        [
            "route",
            "measures",
            str(empty),
            "--region",
            REGION,
            "--snapshot",
            SNAPSHOT,
            "--out",
            str(tmp_path / "o"),
        ]
    )
    assert code == 1
    assert "no line found" in capsys.readouterr().err


def test_fr18_7_measures_command_counts_the_school_the_line_passes(tmp_path):
    route = write_geojson(tmp_path / "r.geojson", lonlat(densify([(600, 0), (600, 400)])))
    out = tmp_path / "out"
    assert (
        main(
            [
                "route",
                "measures",
                str(route),
                "--region",
                REGION,
                "--snapshot",
                SNAPSHOT,
                "--out",
                str(out),
            ]
        )
        == 0
    )
    written = json.loads((out / "measures.json").read_text())
    assert written["schools"] == {"schools": 1, "within_100_m": 1}
