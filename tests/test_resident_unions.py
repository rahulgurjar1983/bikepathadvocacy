import json
from pathlib import Path

from shapely.geometry import box

from bikeplan import trips
from bikeplan.access import homes
from bikeplan.config import load_profile, load_region
from bikeplan.run import build_all
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


def test_fr16_5_offline_selection_keeps_counts_without_bulk_origin_records():
    from bikeplan.change import change_scripts

    outcomes = {
        "strict": {
            "unique_residents": {"before": 0, "after": 100, "newly_gained": 100},
            "by_place_type": {"school": {"before": 0, "after": 100, "newly_gained": 100}},
            "membership": {"after": [{"unit": "cell", "node": i, "people": 1} for i in range(100)]},
        },
        "population": {"scope": "council cells"},
    }
    frontier = {
        "trip_sources": {"population": {"shares": outcomes["strict"]["membership"]["after"]}},
        "scenarios": [
            {
                "id": "shipped",
                "picks": [{"rank": 1}],
                "trip_packages": [
                    {
                        "package": {"scenario": "shipped", "rank": 1},
                        "project_ids": ["project"],
                        "element_ids": ["link"],
                        "strict": [{"origin": i, "destination": "school"} for i in range(100)],
                        "resident_outcomes": outcomes,
                    }
                ],
            }
        ],
    }
    script = change_scripts(frontier)
    embedded = json.loads(script.split('id="change-data">', 1)[1].split("</script>", 1)[0])
    package = embedded["scenarios"][0]["trip_packages"][0]
    assert package["package"] == {"scenario": "shipped", "rank": 1}
    assert package["project_ids"] == ["project"]
    assert package["resident_outcomes"]["strict"]["unique_residents"]["after"] == 100
    assert package["resident_outcomes"]["strict"]["by_place_type"]["school"]["after"] == 100
    assert "membership" not in package["resident_outcomes"]["strict"]
    assert "strict" not in package
    assert "shares" not in embedded["trip_sources"]["population"]
    assert frontier["trip_sources"]["population"]["shares"]
    assert frontier["scenarios"][0]["trip_packages"][0]["strict"]


def test_fr16_5_offline_report_compacts_maps_without_changing_counts():
    from bikeplan.report import map_scripts

    payload = {
        "population": {"people": 120.5, "scope": "council"},
        "features": [{"id": i, "coordinates": [151.1, -33.9]} for i in range(100)],
    }
    raw = json.dumps(payload, indent=2)
    script = map_scripts(raw, "")
    embedded = script.split('id="map-data">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == payload
    assert len(embedded) < len(json.dumps(payload))


def test_fr16_5_offline_project_data_preserves_counts_in_compact_json():
    from bikeplan.page import data_block

    payload = {
        "project_shapes": {"features": []},
        "projects": [],
        "summary": {"unique_residents": {"before": 10.5, "after": 120.5}},
    }
    script = data_block(payload)
    embedded = script.split('id="page-data">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == payload
    assert len(embedded) < len(json.dumps(payload))
