import pytest

from bikeplan.access import Reach, homes
from bikeplan.change import STEP_FIGURES
from bikeplan.propose import csv_row, curve_picks, greedy_picks, planning_network, project_records
from bikeplan.review import ranked_like
from bikeplan.run import project_summary
from tests.test_propose_network import BUSY, PROFILE, REGION
from tests.test_propose_picks import DETOUR, REACH_M, star


def test_fr15_6_new_destinations_union_people_and_types():
    from bikeplan.access import people_gains

    placed = [("school", 10), ("school", 11), ("station", 12)]
    before = [Reach({}, set()), Reach({}, {1}), Reach({}, set())]
    after = [Reach({}, {1, 2}), Reach({}, {1, 2}), Reach({}, {1})]
    found = people_gains({1: 0.4, 2: 0.6}, placed, before, after, ["school", "station"])
    assert found == {
        "unique_people": 1.0,
        "unique_people_by_type": {"school": 1.0, "station": 0.4},
        "gains_by_type": pytest.approx(1.4),
    }


def picks():
    graph = star([(400, BUSY), (800, BUSY)])
    planning = planning_network(graph, PROFILE, REGION)
    found = greedy_picks(
        graph,
        planning,
        [("school", 0), ("school", 0), ("station", 0)],
        {1: 30, 2: 10},
        {"school": 1, "station": 1},
        REGION.proposals,
        REACH_M,
        DETOUR,
    )
    return found, planning


def test_fr15_6_packages_records_curves_exports_and_review_use_same_measures():
    picked, planning = picks()
    records = project_records(picked, planning)
    measures = {
        "unique_people": 40,
        "unique_people_by_type": {"school": 40, "station": 40},
        "gains_by_type": 80,
    }
    assert records[-1]["totals"]["package_access_gains"] == measures
    assert records[0]["totals"]["access_gains"]["unique_people"] == 30
    assert curve_picks(picked, planning)[-1]["unique_people"] == 40
    assert project_summary(records, ["school", "station"])["access_gains"] == measures
    assert ranked_like(records, 2, ["school", "station"])["access_gains"] == measures
    row = csv_row(records[0], ["school", "station"])
    assert row["unique_people"] == 30
    assert row["gains_by_type"] == 60
    figure = next(item for item in STEP_FIGURES if item[0] == "F10")
    assert figure[-1](curve_picks(picked, planning)[-1]) == 40


def test_fr15_6_shared_population_unit_is_allocated_once():
    from shapely.geometry import box

    from bikeplan.access import people_gains

    graph = star([(400, BUSY), (800, BUSY)])
    area = box(-2000, -2000, 2000, 2000)
    resident = homes([{"polygon": area, "people": 90}], graph, area)
    placed = [("school", 10), ("school", 11), ("station", 12)]
    before = [Reach({}, set()) for _ in placed]
    after = [Reach({}, set(resident.people)) for _ in placed]
    found = people_gains(resident.people, placed, before, after, ["school", "station"])
    assert found["unique_people"] == pytest.approx(90)
    assert found["unique_people_by_type"] == pytest.approx({"school": 90, "station": 90})
    assert found["gains_by_type"] == pytest.approx(180)


def test_fr15_6_report_tables_label_unique_people_and_type_gains():
    from bikeplan.page import projects_section

    picked, planning = picks()
    records = project_records(picked, planning)
    html = projects_section(records)
    assert "Unique people" in html
    assert "Gains counted by type" in html
    assert "<code>30</code>" in html
    assert "<code>60</code>" in html


def test_fr15_6_route_review_keeps_all_three_measures(tmp_path):
    from bikeplan.config import load_profile, load_region
    from bikeplan.network import build
    from bikeplan.review import route_figures
    from bikeplan.route import read_route
    from tests.route_helpers import REGION as PATH
    from tests.route_helpers import SNAPSHOT, densify, lonlat, write_gpx_tracks

    region = load_region(PATH)
    profile = load_profile(region.profile, "profiles")
    graph = build(SNAPSHOT, region, profile)
    path = write_gpx_tracks(
        tmp_path / "route.gpx", {"Spur": lonlat(densify([(200, 200), (600, 200)]))}
    )
    found = route_figures(graph, profile, read_route(path), region, SNAPSHOT)["total"]["access"]
    measures = found["access_gains"]
    assert measures["unique_people"] == pytest.approx(750)
    assert measures["unique_people_by_type"]["school"] == pytest.approx(750)
    assert measures["gains_by_type"] == pytest.approx(750)
    assert found["ranked"]["access_gains"] == measures


def test_fr15_6_sheets_retain_exact_counts_for_checking():
    from html import unescape

    from bikeplan.page import sheet

    record = {
        "id": "sample",
        "name": "Example people counts",
        "gain": 1.0,
        "score_after": 2.0,
        "elements": [],
        "totals": {
            "parking_spaces": 0,
            "lane_km": 0,
            "speed_km": 0,
            "signals": 0,
            "refuges": 0,
            "km_by_fix": {},
            "access_gains": {
                "unique_people": 0.4,
                "unique_people_by_type": {"station": 0.4, "school": 0.4},
                "gains_by_type": 0.8,
            },
        },
    }
    found = unescape(sheet(record, []))
    assert "<details><summary>Exact people counts to check and reuse</summary>" in found
    assert (
        "{'gains_by_type': 0.8, 'unique_people': 0.4, 'unique_people_by_type': {'school': 0.4, 'station': 0.4}}"
        in found
    )
    assert "Unique people gaining a safe destination" in found
    assert "Gains counted by type" in found
