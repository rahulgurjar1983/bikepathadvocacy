import dataclasses
import json

import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.fit import choose, options
from bikeplan.propose import greedy_picks, planning_network
from bikeplan.run import build_all
from bikeplan.width import fuse
from tests.test_fit_options import street
from tests.test_propose_network import line

PROFILE = load_profile("au-nsw", "profiles")
REGION = load_region("regions/test-grid.yaml")
CHECKS = (
    "footpath space",
    "trees",
    "utilities",
    "drainage",
    "driveways",
    "bus stops",
    "narrow points",
)


def observation(width=5.0, low=4.5, constraints=None):
    return {
        "width_m": width,
        "low_m": low,
        "high_m": width + 0.5,
        "source": "test-only site survey",
        "date": "2026-10-01",
        "confidence": "high",
        "constraints": dict.fromkeys(CHECKS, "clear") if constraints is None else constraints,
    }


def busy():
    return street("primary", 13.0, 4, "no", 60, 25000, reserve=27.0)


def verge(data):
    return next(item for item in options(data, PROFILE) if item["fix"] == "verge_path")


def test_fr15_4_parcel_estimate_keeps_three_distinct_width_records():
    found = fuse(
        {
            **busy(),
            "width_m": None,
            "reserve_source": "test parcels",
            "reserve_date": "2026-09-01",
            "reserve_spread_m": 2.0,
        },
        PROFILE,
    )
    assert found["carriageway"]["source"] == "reserve"
    assert found["carriageway"]["observed"] is False
    assert found["road_reserve"]["source"] == "test parcels"
    assert found["road_reserve"]["date"] == "2026-09-01"
    assert found["road_reserve"]["low_m"] == 26.0
    assert found["usable_verge"]["width_m"] is None
    assert found["usable_verge"]["confidence"] == "unknown"
    assert found["usable_verge"]["date"] is None


def test_fr15_4_reserve_minus_assumed_verges_is_only_a_survey_option():
    fused = fuse(busy(), PROFILE)
    item = verge({**busy(), **fused})
    assert not item["fits"]
    assert item["fit_status"] == "needs_survey"
    assert set(item["survey_checks"]) == set(CHECKS)
    assert item["source_confidence"] == "unknown"


@pytest.mark.parametrize("low, confirmed", [(4.5, True), (3.4, False)])
def test_fr15_4_observed_usable_verge_uses_its_lower_bound(low, confirmed):
    item = verge({**busy(), "usable_verge": observation(low=low)})
    assert item["confirmed"] is confirmed
    assert item["source_confidence"] == "high"
    assert item["model_margin"] == ("robust" if confirmed else "check on site")
    assert item["fit_status"] == ("confirmed" if confirmed else "needs_survey")
    assert item["usable_margin_low_m"] == pytest.approx(low - item["needs_m"])


@pytest.mark.parametrize("gap", CHECKS)
def test_fr15_4_missing_constraint_keeps_wide_verge_unconfirmed(gap):
    checks = dict.fromkeys(CHECKS, "clear")
    checks.pop(gap)
    item = verge({**busy(), "usable_verge": observation(constraints=checks)})
    assert not item["confirmed"]
    assert item["fit_status"] == "needs_survey"
    assert gap in item["survey_checks"]


def test_fr15_4_low_source_confidence_is_not_a_robust_width_proof():
    data = street("tertiary", 14.0, 2, "yes", 50, 5000)
    data |= {"width_low_m": 13.8, "width_source": "lanes", "width_confidence": "low"}
    item = next(item for item in options(data, PROFILE) if item["fix"] == "cycleway_in_spare")
    assert item["model_margin"] == "robust"
    assert item["source_confidence"] == "low"
    assert not item["confirmed"]
    assert item["fit_status"] == "needs_survey"


def test_fr15_4_default_network_excludes_survey_fix_and_retains_other_valid_fix():
    inferred = {**busy(), "width_m": None, "width_tag_m": None}
    valid = {**street("tertiary", 10.0, 2, "yes", 50, 5000), "width_tag_m": 10.0}
    planning = planning_network(line([(100, inferred), (100, valid)]), PROFILE, REGION)
    assert (0, 1, 0) not in planning.edges
    assert (1, 2, 0) in planning.edges
    assert planning.survey_options
    assert all(item["fit_status"] == "needs_survey" for item in planning.survey_options)
    assert planning.elements["segment:s1"]["confirmed"]


def test_fr15_4_choose_preserves_a_confirmed_fix_over_a_cheaper_survey_fix():
    data = {
        **street("tertiary", 12.0, 2, "yes", 50, 5000, reserve=27.0),
        "width_low_m": 11.5,
        "width_source": "osm_tag",
        "width_confidence": "medium",
        "length_m": 100.0,
    }
    result = choose(data, PROFILE, REGION.proposals.disruption_weights)
    assert result["fix"] == "cycleway_parking_one_side"
    assert result["survey_options"]
    assert result["confirmed"]


def test_fr15_4_empty_shortlist_retains_survey_layer_and_reason():
    region = dataclasses.replace(
        REGION, proposals=dataclasses.replace(REGION.proposals, min_gain=100.0)
    )
    summary, outputs, files, _ = build_all(region, PROFILE, "tests/fixtures/test-grid/snapshot")
    assert summary["projects"] == 0
    assert (
        summary["shortlist_reason"] == "No confirmed project gains enough at the set minimum gain."
    )
    surveys = json.loads(outputs["survey_options.geojson"])
    assert surveys["features"]
    assert json.loads(files["map.json"])["survey_options"] == surveys
    assert b'id="layer-survey"' in outputs["report.html"]
    assert b"Survey options need site checks" in outputs["report.html"]
    assert b"No confirmed project gains enough" in outputs["report.html"]


def test_fr15_4_empty_default_picks_do_not_lower_minimum_gain():
    graph = line([(100, {**busy(), "width_tag_m": None})])
    planning = planning_network(graph, PROFILE, REGION)
    found = greedy_picks(
        graph,
        planning,
        [("school", 1)],
        {0: 10},
        {"school": 1.0},
        REGION.proposals,
        REGION.access.reach_m,
        REGION.access.detour_max,
    )
    assert found == []
    assert planning.survey_options
    assert REGION.proposals.min_gain > 0


def test_fr15_4_snapshot_dates_follow_the_width_source(tmp_path):
    from bikeplan.network import build

    from tests.test_propose_command import snapshot

    graph = build(snapshot(tmp_path / "snapshot"), REGION, PROFILE)
    data = next(data for _, _, data in graph.edges(data=True) if data.get("width_tag_m"))
    found = fuse(data, PROFILE)
    assert found["carriageway"]["date"] == REGION.snapshot.osm_date
    assert found["carriageway"]["source"] == "osm_tag"
    assert found["carriageway"]["observed"]


def test_fr15_4_survey_fixes_are_not_labelled_as_default_network_works():
    from bikeplan.run import network_features

    data = {
        **busy(),
        "speed_source": "test-only posted speed",
        "adt_source": "default",
        "width_tag_m": None,
    }
    features, _ = network_features(
        line([(100, data)]), PROFILE, REGION.proposals.disruption_weights
    )
    assert features[0]["properties"]["fix"] is None
    assert features[0]["properties"]["fit"] == "needs_survey"


def test_fr15_4_survey_layer_lists_checks_and_keeps_links_to_width_records():
    _, outputs, _, _ = build_all(REGION, PROFILE, "tests/fixtures/test-grid/snapshot")
    surveys = json.loads(outputs["survey_options.geojson"])["features"]
    assert surveys
    for feature in surveys:
        properties = feature["properties"]
        assert properties["segments"]
        assert properties["fixes"]
        assert set(CHECKS) <= set(properties["survey_checks"])
        assert properties["source_confidence"]
        assert properties["model_margin"]
        assert properties["fit_status"] == "needs_survey"


def test_fr15_4_project_sheet_names_margin_and_source_confidence_separately():
    from bikeplan.page import sheet
    from bikeplan.propose import project_records

    data = {**street("tertiary", 10.0, 2, "yes", 50, 5000), "width_tag_m": 10.0}
    graph = line([(100, data)])
    planning = planning_network(graph, PROFILE, REGION)
    picks = greedy_picks(
        graph,
        planning,
        [("school", 1)],
        {0: 10},
        {"school": 1.0},
        REGION.proposals,
        REGION.access.reach_m,
        REGION.access.detour_max,
    )
    record = project_records(picks, planning)[0]
    markup = sheet(record, [])
    assert "Model margin" in markup
    assert "Source confidence" in markup
    assert record["elements"][0]["model_margin"] == "robust"
    assert record["elements"][0]["source_confidence"] == "medium"
