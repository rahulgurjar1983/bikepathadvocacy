import json
from pathlib import Path

from shapely.geometry import box

from bikeplan.access import homes
from bikeplan.config import load_profile, load_region
from bikeplan.run import build_all
from bikeplan import trips
from tests.test_access_homes import line_graph


def population():
    graph = line_graph([10, 50, 1010])
    return homes(
        [
            {"id": "cell-a", "polygon": box(0, -50, 100, 50), "people": 120.5},
            {"id": "buffer", "polygon": box(1000, -50, 1100, 50), "people": 99},
            {"id": "missed", "polygon": box(3000, -50, 3100, 50), "people": 20},
        ],
        graph,
        box(-100, -100, 4000, 100),
    )


def test_fr15_6_population_shares_union_nodes_types_and_destinations():
    resident = population()
    destinations = [
        {"id": key, "type": kind}
        for key, kind in (("school-a", "school"), ("school-b", "school"), ("station", "station"))
    ]
    before = {"strict": [], "first_leg_model": []}
    after = {
        "strict": [
            {"origin": node, "destination": dest["id"]} for node in (0, 1) for dest in destinations
        ],
        "first_leg_model": [],
    }
    after["strict"].append(after["strict"][0])
    result = trips.resident_outcomes(before, after, resident.population, destinations)
    assert result["strict"]["unique_residents"] == {
        "before": 0,
        "after": 120.5,
        "newly_gained": 120.5,
    }
    assert result["strict"]["by_place_type"]["school"]["newly_gained"] == 120.5
    assert result["strict"]["by_place_type"]["station"]["newly_gained"] == 120.5
    assert result["strict"]["gains_counted_by_type"] == 241.0
    assert len(result["strict"]["membership"]["after"]) == 2
    assert {item["unit"] for item in result["strict"]["membership"]["after"]} == {"cell-a"}


def test_fr16_5_buffer_first_legs_existing_access_and_missing_groups_are_explicit():
    graph = line_graph([10, 50, 1010])
    resident = homes(
        [
            {"id": "council", "polygon": box(0, -50, 100, 50), "people": 100},
            {"id": "buffer", "polygon": box(1000, -50, 1100, 50), "people": 99},
            {"id": "missed", "polygon": box(300, 400, 400, 500), "people": 20},
        ],
        graph,
        box(-100, -100, 500, 600),
    )
    destinations = [{"id": "school", "type": "school"}, {"id": "station", "type": "station"}]
    before = {"strict": [{"origin": 0, "destination": "school"}], "first_leg_model": []}
    after = {
        "strict": before["strict"]
        + [{"origin": 0, "destination": "station"}, {"origin": 2, "destination": "school"}],
        "first_leg_model": [{"origin": 1, "destination": "station"}],
    }
    result = trips.resident_outcomes(before, after, resident.population, destinations)
    assert result["strict"]["unique_residents"] == {"before": 50, "after": 50, "newly_gained": 50}
    assert result["first_leg_model"]["unique_residents"]["after"] == 50
    assert result["population"]["buffer_excluded"] == 99
    assert result["population"]["unsnapped"] == 20
    assert (
        result["population"]["partial_cell_rule"] == "whole count when centroid is inside council"
    )
    assert all(item["value"] is None for item in result["missing_groups"].values())
    assert "not home addresses" in result["limit"]
    assert "forecast" in result["limit"]
    assert result["first_leg_model"]["evidence_status"] == "assumed"
    assert "new destination" in result["method"]


def test_fr16_5_saved_packages_shortlist_and_report_publish_resident_unions():
    _, outputs, files, _ = build_all(
        load_region("tests/fixtures/test-grid/region.yaml"),
        load_profile("au-nsw"),
        Path("tests/fixtures/test-grid/snapshot"),
    )
    frontier = json.loads(files["frontier.json"])
    for curve in frontier["scenarios"]:
        for package in curve["trip_packages"]:
            outcomes = package["resident_outcomes"]
            assert outcomes["strict"]["unique_residents"] == {
                "before": 0,
                "after": 0,
                "newly_gained": 0,
            }
            assert outcomes["evidence_status"] == "modelled_with_missing_trip_evidence"
            assert outcomes["population"]["source"]
    shortlist = json.loads(outputs["projects.geojson"])["trip_proof"]
    assert shortlist["resident_outcomes"]["strict"]["unique_residents"]["after"] == 0
    page = outputs["report.html"].decode()
    assert "Unique estimated residents" in page
    assert "not a forecast of rides" in page
    assert "Unknown age, disability, pupil and household data" in page
