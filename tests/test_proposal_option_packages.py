import json

import pytest

from bikeplan import main
from bikeplan.proposal_record import option_packages

SOURCE = {"source": "council plan", "date": "2026-01-01"}
CONTENTS = {
    "stages": [
        {
            **SOURCE,
            "id": "study",
            "kind": "studies",
            "element_ids": ["segment:a"],
            "project_ids": ["p1"],
            "depends_on": [],
        },
        {
            **SOURCE,
            "id": "build",
            "kind": "construction",
            "element_ids": ["segment:c", "segment:b", "segment:c"],
            "project_ids": ["p3"],
            "depends_on": ["study"],
        },
    ],
    "route_options": [
        {
            **SOURCE,
            "id": "east",
            "name": "East link",
            "goal_ids": ["g1"],
            "element_ids": ["segment:b"],
            "project_ids": [],
        }
    ],
}


def test_fr16_1_stage_packages_keep_exact_sets_parents_and_no_curve_rank():
    packages = option_packages({"contents": CONTENTS})
    assert [p["identity"] for p in packages] == [
        {"option": "study", "type": "stage"},
        {"option": "build", "type": "stage"},
        {"option": "east", "type": "route_option"},
    ]
    build = packages[1]
    assert build["project_ids"] == ["p3"]
    assert build["element_ids"] == ["segment:b", "segment:c"]
    assert build["parents"] == ["study"]
    assert packages[2]["parents"] == ["g1"]
    for package in packages:
        assert "rank" not in package["identity"]
        assert "scenario" not in package["identity"]
        assert package["kind"] == "concept"
        assert package["evidence_mode"] == "sourced_unproved"
        assert package["source"]["source"] == "council plan"
        outcome = package["outcomes"]["strict_return_trips"]
        assert outcome["value"] is None
        assert outcome["evidence_status"] == "unknown"
        assert outcome["reason"]


def test_fr16_1_no_sourced_options_gives_no_packages():
    assert option_packages({"contents": None}) == []
    assert option_packages({}) == []


@pytest.fixture(scope="module")
def record(tmp_path_factory):
    out = tmp_path_factory.mktemp("option-record")
    args = ["run", "tests/fixtures/test-grid/region.yaml", "--snapshot"]
    assert main([*args, "tests/fixtures/test-grid/snapshot", "--out", str(out)]) == 0
    return json.loads((out / "proposal.json").read_text())


def test_fr15_2_archive_lists_option_packages_apart_from_curve_packages(record):
    assert record["option_packages"] == []
    assert all("scenario" in p["identity"] for p in record["packages"])
    assert record["shortlist"]["selected"] is False
