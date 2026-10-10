import hashlib
import json
import socket

import pytest

from bikeplan import main
from bikeplan.config import ConfigError

SOURCE = {"source": "https://example.org/public-plan", "date": "2026-10-01"}
CATALOG = {"segment:a": {"length_m": 100}, "segment:b": {"length_m": 200}}


def metadata():
    return {"version": 1, "public": True}


def cost(key, elements, currency="AUD", year=2026, unit="total"):
    return {
        **SOURCE,
        "id": key,
        "element_ids": elements,
        "kind": "capital",
        "low": 10,
        "high": 20,
        "currency": currency,
        "base_year": year,
        "unit": unit,
        "scope": "Test design only",
        "exclusions": ["Land", "Tax"],
    }


def load(tmp_path, data):
    from bikeplan.proposal_inputs import load_proposal_inputs

    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(data))
    return load_proposal_inputs(path)


def test_fr16_10_hashes_public_contents_and_rejects_private_paths(tmp_path):
    from bikeplan.proposal_inputs import load_proposal_inputs, metadata_bytes

    supplied = load(tmp_path, metadata())
    assert supplied["sha256"] == hashlib.sha256(metadata_bytes(supplied["contents"])).hexdigest()
    private = tmp_path / "data/private"
    private.mkdir(parents=True)
    path = private / "plan.json"
    path.write_text(json.dumps(metadata()))
    link = tmp_path / "public.json"
    link.symlink_to(path)
    for target in (path, link):
        with pytest.raises(ConfigError, match="private"):
            load_proposal_inputs(target)


@pytest.mark.parametrize(
    "change",
    [
        {"public": False},
        {"residents": [{"name": "A person", "address": "Their home"}]},
        {"owners": [{**SOURCE, "id": "owner", "organization": "person@example.org"}]},
        {"costs": [cost("bad", ["segment:a"], year=0)]},
        {"costs": [{**cost("bad", ["segment:a"]), "high": 5}]},
        {"costs": [{**cost("bad", ["segment:a"]), "source": ""}]},
    ],
)
def test_fr16_10_rejects_personal_records_and_bad_cost_evidence(tmp_path, change):
    with pytest.raises(ConfigError):
        load(tmp_path, {**metadata(), **change})


def test_fr16_10_prices_shared_works_once_and_rates_by_physical_length(tmp_path):
    from bikeplan.proposal_inputs import delivery_record

    supplied = load(tmp_path, {**metadata(), "costs": [cost("one", ["segment:a"], unit="per_m")]})
    result = delivery_record(supplied, ["segment:a", "segment:a"], CATALOG)
    capital = result["costs"]["capital"]
    assert capital["low"] == 1000 and capital["high"] == 2000
    assert capital["element_ids"] == ["segment:a"]
    assert capital["currency"] == "AUD" and capital["base_year"] == 2026
    assert capital["exclusions"] == ["Land", "Tax"]
    assert result["costs"]["upkeep"]["low"] is None


@pytest.mark.parametrize(
    "currency,year,unit",
    [("USD", 2026, "total"), ("AUD", 2025, "total"), ("AUD", 2026, "per_year")],
)
def test_fr16_10_incompatible_costs_do_not_form_a_budget(tmp_path, currency, year, unit):
    from bikeplan.proposal_inputs import delivery_record

    data = {
        **metadata(),
        "costs": [cost("a", ["segment:a"]), cost("b", ["segment:b"], currency, year, unit)],
    }
    if unit == "per_year":
        with pytest.raises(ConfigError):
            load(tmp_path, data)
    else:
        result = delivery_record(load(tmp_path, data), list(CATALOG), CATALOG)
        assert result["costs"]["capital"]["low"] is None
        assert result["costs"]["capital"]["reason"]
        assert len(result["costs"]["capital"]["groups"]) == 2


def test_fr16_10_partial_cost_and_spending_constraint_stay_unproved(tmp_path):
    from bikeplan.proposal_inputs import delivery_record

    data = {
        **metadata(),
        "costs": [cost("a", ["segment:a"])],
        "budget": {**SOURCE, "currency": "AUD", "base_year": 2026, "capital_limit": 1000},
    }
    result = delivery_record(load(tmp_path, data), list(CATALOG), CATALOG)
    assert result["costs"]["capital"]["low"] is None
    assert result["costs"]["capital"]["groups"][0]["low"] == 10
    assert result["costs"]["capital"]["missing_element_ids"] == ["segment:b"]
    assert result["budget"]["status"] == "unproved"
    data["costs"].append(cost("b", ["segment:b"]))
    data["budget"]["capital_limit"] = 30
    assert (
        delivery_record(load(tmp_path, data), list(CATALOG), CATALOG)["budget"]["status"]
        == "exceeded"
    )


def test_fr16_10_rejects_overlapping_scopes_and_bad_references(tmp_path):
    from bikeplan.proposal_inputs import validate_references

    for data in (
        {**metadata(), "costs": [cost("a", ["segment:a"]), cost("b", ["segment:a"])]},
        {
            **metadata(),
            "stages": [
                {
                    **SOURCE,
                    "id": "s",
                    "kind": "construction",
                    "element_ids": ["segment:missing"],
                    "depends_on": [],
                }
            ],
        },
        {
            **metadata(),
            "stages": [
                {**SOURCE, "id": "s", "kind": "studies", "element_ids": [], "depends_on": ["s"]}
            ],
        },
        {**metadata(), "goals": [{**SOURCE, "id": "g", "destination_ids": ["missing"]}]},
    ):
        with pytest.raises(ConfigError):
            validate_references(load(tmp_path, data), CATALOG, [], [])


def test_fr16_10_unfunded_dates_never_become_commitments(tmp_path):
    from bikeplan.proposal_inputs import delivery_record, validate_references

    data = {
        **metadata(),
        "stages": [
            {
                **SOURCE,
                "id": "design",
                "kind": "concept_design",
                "element_ids": ["segment:a"],
                "depends_on": [],
                "proposed_date": "2027-01-01",
            }
        ],
    }
    supplied = load(tmp_path, data)
    validate_references(supplied, CATALOG, [], [])
    record = delivery_record(supplied, ["segment:a"], CATALOG)
    assert record["stages"][0]["funding_status"] == "unknown"
    assert record["stages"][0]["date_status"] == "proposed, not a commitment"
    assert record["stages"][0]["trip_status"] == "unproved"
    assert record["owner"]["value"] is None
    assert record["approvals"]["value"] is None


def test_fr15_14_unknown_costs_owner_and_next_ask_are_explicit(tmp_path):
    from bikeplan.proposal_inputs import delivery_record, load_proposal_inputs

    record = delivery_record(load_proposal_inputs(None), ["segment:a"], CATALOG)
    assert record["costs"]["capital"]["low"] is None
    assert record["costs"]["upkeep"]["high"] is None
    assert record["owner"]["value"] is None and record["owner"]["reason"]
    assert record["approvals"]["value"] is None
    assert record["decision"]["kind"] == "survey_or_concept_design"
    assert record["decision"]["required_evidence"]
    assert record["permission_dependencies"]["value"] is None


@pytest.mark.parametrize("command", ["run", "propose", "report"])
def test_fr16_10_cli_archives_metadata_offline_for_each_command(tmp_path, monkeypatch, command):
    from bikeplan.proposal_inputs import metadata_bytes

    supplied = {
        **metadata(),
        "next_decision": {
            **SOURCE,
            "kind": "studies",
            "ask": "Seek public route records",
            "required_evidence": ["Crossing movements"],
            "permission_dependencies": ["Public land access"],
        },
    }
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps(supplied))
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("network call"))
    out = tmp_path / "out"
    assert (
        main(
            [
                command,
                "tests/fixtures/test-grid/region.yaml",
                "--snapshot",
                "tests/fixtures/test-grid/snapshot",
                "--proposal-inputs",
                str(path),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    frontier = json.loads((out / "frontier.json").read_text())
    archived = frontier["proposal_metadata"]
    assert archived["contents"] == supplied
    assert archived["sha256"] == hashlib.sha256(metadata_bytes(supplied)).hexdigest()
    for curve in frontier["scenarios"]:
        for package in curve["trip_packages"]:
            assert package["delivery"]["owner"]["value"] is None
            assert package["delivery"]["decision"]["ask"] == "Seek public route records"
    if command != "propose":
        assert "Seek public route records" in (out / "report.html").read_text()


def test_fr15_14_project_sheets_show_delivery_and_evidence_gaps(tmp_path):
    from bikeplan.proposal_inputs import enrich_projects, load_proposal_inputs

    from bikeplan.page import sheet
    from bikeplan.propose import planning_network, project_sheet_records
    from tests.test_propose_network import PROFILE, REGION
    from tests.test_propose_picks import star
    from tests.test_propose_records import HIGH, records

    graph = star([(400, HIGH)])
    found = records(graph, {1: 30}, 0, ["Test School"])
    sheets = project_sheet_records(found, planning_network(graph, PROFILE, REGION))
    enrich_projects(sheets, load_proposal_inputs(None), CATALOG)
    rendered = sheet(sheets[0], [])
    for label in (
        "Owner",
        "Approvals",
        "Capital",
        "Upkeep",
        "Next decision",
        "Survey needs",
        "Alternatives",
        "Dependencies",
        "Observed problem",
        "Complete trips",
    ):
        assert label in rendered
    assert sheets[0]["delivery"]["costs"]["capital"]["low"] is None
