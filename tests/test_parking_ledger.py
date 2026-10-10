import copy
import json
from pathlib import Path

import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.run import build_all
from tests.test_physical_works import build, case


def supplied(before, removed=(), added=()):
    return {
        "source": "test bay survey and design",
        "date": "2026-10-01",
        "evidence_status": "observed",
        "before_bays": before,
        "removed_ids": list(removed),
        "added_bays": list(added),
    }


def bay(key, *uses):
    return {"id": key, "uses": list(uses)}


def test_fr16_7_local_loss_survives_net_gain_and_shared_elements():
    graph, elements = case()
    elements["segment:a"]["parking_evidence"] = supplied(
        [bay(str(i)) for i in range(10)], [str(i) for i in range(5)]
    )
    elements["segment:c"]["parking_evidence"] = supplied(
        [bay("old")], added=[bay(f"new{i}") for i in range(7)]
    )
    catalog, works = build(graph, elements, ["segment:a", "segment:a", "segment:c"])
    totals = works["parking_spaces"]
    assert [totals[k]["value"] for k in ("before", "removed", "added", "after", "net")] == [
        11,
        5,
        7,
        13,
        2,
    ]
    rows = {s["element_ids"][0]: s["parking_spaces"] for s in works["sections"]}
    assert rows["segment:a"]["net"]["value"] == -5
    assert rows["segment:c"]["net"]["value"] == 7
    assert catalog["segment:a"]["parking_spaces"]["source"] == "test bay survey and design"
    assert catalog["segment:a"]["parking_spaces"]["date"] == "2026-10-01"


def test_fr16_7_unknown_inventory_keeps_loss_and_names_missing_locations():
    graph, elements = case()
    elements["segment:a"].update(fix="cycleway_parking_one_side", counts={"parking_spaces": 5})
    elements["segment:c"]["parking_evidence"] = supplied([bay("known")])
    catalog, works = build(graph, elements, ["segment:a", "segment:c"])
    row = catalog["segment:a"]["parking_spaces"]
    assert row["before"] is None and row["after"] is None
    assert row["removed"] == 5 and row["added"] == 0 and row["net"] == -5
    assert row["evidence_status"] == "modelled"
    assert row["reason"] and row["method"] and row["source"]
    total = works["parking_spaces"]["before"]
    assert total["value"] is None and total["known_subtotal"] == 1
    assert total["missing_element_ids"] == ["segment:a"]
    assert total["known_element_ids"] == ["segment:c"]
    assert works["parking_spaces"]["removed"]["value"] == 5


def test_fr16_7_special_uses_overlap_without_inflating_capacity_or_inventing_occupancy():
    graph, elements = case()
    shared = bay("shared", "accessible", "loading", "short_stay", "school_drop_off")
    elements["segment:a"]["parking_evidence"] = supplied(
        [shared, shared, bay("regular"), bay("rack", "bike_parking")], ["shared"]
    )
    catalog, works = build(graph, elements, ["segment:a"])
    row = catalog["segment:a"]["parking_spaces"]
    assert row["before"] == 2 and row["removed"] == 1 and row["after"] == 1
    for use in ("accessible", "loading", "short_stay", "school_drop_off"):
        assert row["special_uses"][use]["removed"] == 1
    assert row["special_uses"]["bike_parking"]["before"] == 1
    assert row["occupancy"]["value"] is None and row["spillover"]["value"] is None
    assert works["parking_spaces"]["before"]["value"] == 2


def test_fr16_7_changed_total_and_bad_inventory_fail():
    from bikeplan.parking import verify_parking

    graph, elements = case()
    elements["segment:a"]["parking_evidence"] = supplied([bay("one")], ["one"])
    catalog, works = build(graph, elements, ["segment:a"])
    changed = copy.deepcopy(works)
    changed["parking_spaces"]["removed"]["value"] = 0
    with pytest.raises(ValueError, match="Parking"):
        verify_parking(catalog, changed)
    elements["segment:a"]["parking_evidence"]["removed_ids"] = ["missing"]
    with pytest.raises(ValueError, match="Parking"):
        build(graph, elements, ["segment:a"])


def test_fr16_7_pipeline_archives_and_displays_the_selected_parking_ledger():
    _, outputs, _, figures = build_all(
        load_region("tests/fixtures/test-grid/region.yaml"),
        load_profile("au-nsw"),
        Path("tests/fixtures/test-grid/snapshot"),
    )
    frontier = json.loads(outputs["frontier.json"])
    for curve in frontier["scenarios"]:
        for package in curve["trip_packages"]:
            assert "parking_spaces" in package["works"]
    assert "parking_spaces" in json.loads(outputs["projects.geojson"])["trip_proof"]["works"]
    page = outputs["report.html"].decode()
    assert "Spaces before, removed, added, after and net" in page
    assert "A net gain elsewhere does not hide local loss" in page
    assert 'href="#F23"' in page
    assert "F23" in {f["id"] for f in figures}
