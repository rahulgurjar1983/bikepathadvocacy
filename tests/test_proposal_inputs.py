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
    from bikeplan.page import sheet
    from bikeplan.proposal_inputs import enrich_projects, load_proposal_inputs
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


def test_fr16_10_cost_range_recipes_and_opening_replay_archived_sources(tmp_path):
    import subprocess
    import sys

    from bikeplan.proposal_inputs import load_proposal_inputs
    from tests.test_report import Page

    supplied = {
        **metadata(),
        "costs": [cost("crossing", ["junction:1010"])],
        "owners": [{**SOURCE, "id": "council", "organization": "Test Council"}],
        "approvals": [
            {**SOURCE, "id": "permission", "authority": "Test Authority", "status": "pending"}
        ],
        "stages": [
            {
                **SOURCE,
                "id": "design",
                "kind": "concept_design",
                "depends_on": [],
                "element_ids": ["junction:1010"],
                "proposed_date": "2027-01-01",
            }
        ],
    }
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps(supplied))
    assert load_proposal_inputs(path)["contents"] == supplied
    out = tmp_path / "report"
    assert (
        main(
            [
                "report",
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
    figures = json.loads((out / "figures.json").read_text())
    priced = [r for r in figures if r["spec"] == "FR-16.10"]
    assert priced
    for figure in priced:
        done = subprocess.run(
            [sys.executable, "-I", "-c", figure["recipe"]],
            cwd=out,
            check=True,
            text=True,
            capture_output=True,
        )
        assert float(done.stdout) == figure["value"]
        assert (
            figure["inputs"][0]["sha256"]
            == hashlib.sha256((out / "frontier.json").read_bytes()).hexdigest()
        )
    page = (out / "report.html").read_text()
    opening = page.split('<section id="opening"', 1)[1].split("</section>", 1)[0]
    assert "Test Council" in opening and "pending" in opening
    assert "No sourced rates or budget are supplied" not in opening
    parsed = Page()
    parsed.feed(page)
    assert not any(char.isdigit() for char in " ".join(parsed.outside))


def test_fr16_10_supplied_stage_owner_permissions_and_mitigation_are_retained(tmp_path):
    from bikeplan.proposal_inputs import delivery_record, validate_references

    data = {
        **metadata(),
        "owners": [{**SOURCE, "id": "o", "organization": "Council"}],
        "stages": [
            {
                **SOURCE,
                "id": "study",
                "kind": "studies",
                "owner_id": "o",
                "depends_on": [],
                "element_ids": ["segment:a"],
            },
            {
                **SOURCE,
                "id": "design",
                "kind": "detailed_design",
                "owner_id": "o",
                "depends_on": ["study"],
                "element_ids": ["segment:a"],
            },
        ],
        "approvals": [
            {
                **SOURCE,
                "id": "land",
                "authority": "Land authority",
                "status": "required",
                "permission": "Public land use",
            }
        ],
        "mitigation": [
            {
                **SOURCE,
                "id": "walk",
                "element_ids": ["segment:a"],
                "description": "Keep walking access in concept review",
            }
        ],
    }
    supplied = load(tmp_path, data)
    validate_references(supplied, CATALOG, [], [])
    record = delivery_record(supplied, ["segment:a"], CATALOG)
    assert record["owner"]["value"] == data["owners"]
    assert record["approvals"]["value"] == data["approvals"]
    assert record["mitigation"] == data["mitigation"]
    assert record["stages"][1]["depends_on"] == ["study"]
    assert record["stages"][0]["owner_id"] == "o"


def test_fr16_10_upkeep_is_annual_and_a_build_request_needs_design_proof(tmp_path):
    from bikeplan.proposal_inputs import delivery_record

    annual = {**cost("upkeep", ["segment:a"], unit="per_m_year"), "kind": "upkeep"}
    data = {
        **metadata(),
        "costs": [annual],
        "next_decision": {
            **SOURCE,
            "kind": "construction",
            "ask": "Build the route",
            "required_evidence": ["Land approval"],
            "permission_dependencies": ["Land permission"],
        },
    }
    record = delivery_record(load(tmp_path, data), ["segment:a"], CATALOG)
    assert record["costs"]["upkeep"]["low"] == 1000
    assert record["costs"]["upkeep"]["unit"] == "per_year"
    assert record["costs"]["capital"]["low"] is None
    assert record["decision"]["kind"] == "survey_or_concept_design"
    assert record["requested_decision"]["ask"] == "Build the route"
    assert record["decision"]["build_ready"] is False


def test_fr16_10_hash_tamper_area_bounds_and_unproved_funding_are_rejected(tmp_path):
    from bikeplan.proposal_inputs import load_proposal_inputs, validate_references

    supplied = load(tmp_path, metadata())
    supplied["contents"]["goals"] = []
    with pytest.raises(ConfigError, match="hash"):
        load_proposal_inputs(supplied)
    data = {
        **metadata(),
        "stages": [
            {
                **SOURCE,
                "id": "build",
                "kind": "construction",
                "depends_on": [],
                "funding_status": "funded",
            }
        ],
    }
    with pytest.raises(ConfigError, match="funding source"):
        load(tmp_path, data)
    data = {
        **metadata(),
        "areas": [
            {
                **SOURCE,
                "id": "area",
                "name": "Test area",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[200, 0], [201, 0], [201, 1], [200, 0]]],
                },
            }
        ],
    }
    with pytest.raises(ConfigError, match="area geometry"):
        validate_references(load(tmp_path, data), CATALOG, [], [])
    data["areas"][0]["geometry"]["coordinates"] = [[[0, 0], [1, 0], [1, 1], [0, 0]]]
    validate_references(load(tmp_path, data), CATALOG, [], [])


def test_fr16_10_cost_figure_ids_are_stable_when_a_cost_kind_is_added(tmp_path):
    from bikeplan.proposal_inputs import cost_figures, delivery_record

    annual = {**cost("upkeep", ["segment:a"], unit="per_year"), "kind": "upkeep"}

    def figures(costs):
        delivery = delivery_record(
            load(tmp_path, {**metadata(), "costs": costs}), ["segment:a"], CATALOG
        )
        frontier = {
            "scenarios": [
                {"id": "test", "trip_packages": [{"package": {"rank": 1}, "delivery": delivery}]}
            ]
        }
        records, _ = cost_figures(frontier, json.dumps(frontier))
        return {r["label"]: r["id"] for r in records if "upkeep" in r["label"]}

    original = figures([annual])
    expanded = figures([cost("capital", ["segment:a"]), annual])
    assert original == expanded
    assert len(original) == 2


def test_fr16_10_length_rates_cannot_price_missing_physical_length_as_zero(tmp_path):
    from bikeplan.proposal_inputs import delivery_record

    supplied = load(tmp_path, {**metadata(), "costs": [cost("rate", ["segment:a"], unit="per_m")]})
    with pytest.raises(ConfigError, match="physical length"):
        delivery_record(supplied, ["segment:a"], {"segment:a": {"length_m": 0}})
