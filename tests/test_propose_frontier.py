import dataclasses
import json
from pathlib import Path

import pytest

from bikeplan.config import Scenario, load_region
from bikeplan.propose import recommended_stop, scenario_curve, scenarios_for
from tests.test_fit_summary import street
from tests.test_propose_command import run, snapshot
from tests.test_propose_network import BUSY, PROFILE, REGION
from tests.test_propose_picks import DETOUR, REACH_M, WEIGHTS, star

SHIPPED = Scenario("shipped", "Weights as set", {})


def region_with(**changes):
    return dataclasses.replace(REGION, proposals=dataclasses.replace(REGION.proposals, **changes))


def curve(graph, people, region=REGION, scenario=SHIPPED):
    return scenario_curve(
        graph, region, PROFILE, scenario, [("school", 0)], people, WEIGHTS, REACH_M, DETOUR
    )


def test_fr8_13_the_curve_goes_past_min_gain():
    graph = star([(400, BUSY), (400, BUSY)])
    found = curve(graph, {1: 10000, 2: 1})
    assert len(found["picks"]) == 2
    assert found["picks"][1]["gain"] < REGION.proposals.min_gain


def test_fr8_13_the_curve_stops_at_the_cap():
    graph = star([(400, BUSY), (400, BUSY), (400, BUSY)])
    found = curve(graph, {1: 10, 2: 10, 3: 10}, region_with(frontier_max_projects=2))
    assert [item["rank"] for item in found["picks"]] == [1, 2]


def test_fr8_13_the_curve_stops_when_gains_reach_zero():
    graph = star([(400, BUSY), (400, BUSY), (400, BUSY)])
    found = curve(graph, {1: 10, 2: 10, 3: 10})
    assert len(found["picks"]) == 3
    assert found["picks"][-1]["score"] == 100.0


def test_fr8_13_each_running_total_is_the_sum_of_the_picks_so_far():
    graph = star([(400, BUSY), (400, BUSY), (400, BUSY)])
    found = curve(graph, {1: 10, 2: 10, 3: 10})["picks"]
    assert [item["parking_spaces"] for item in found] == [94, 188, 282]
    assert [item["disruption"] for item in found] == [94.0, 188.0, 282.0]
    assert [item["km_by_fix"] for item in found][-1] == {
        "cycleway_parking_both_sides": pytest.approx(1.2)
    }
    assert [item["people"]["school"] for item in found] == [10, 20, 30]
    assert [item["score"] for item in found] == pytest.approx([100 / 3, 200 / 3, 100], abs=0.01)
    for item in found:
        assert {"lane_km", "speed_km", "signals", "refuges", "gain", "id"} <= set(item)


def test_fr8_14_three_default_scenarios_scale_the_weights():
    found = scenarios_for(REGION.proposals)
    assert [item.id for item in found] == ["light", "shipped", "heavy"]
    assert [item.scales for item in found] == [
        {"parking_space": 0.5, "lane_km": 0.5},
        {},
        {"parking_space": 4.0, "lane_km": 4.0},
    ]


def test_fr8_14_the_region_file_can_list_its_own_scenarios(tmp_path):
    text = Path("regions/test-grid.yaml").read_text()
    extra = (
        "  scenarios:\n"
        "    - id: calm\n"
        "      label: Parking is precious\n"
        "      scale:\n"
        "        parking_space: 3\n"
        "  disruption_weights:\n"
    )
    path = tmp_path / "region.yaml"
    path.write_text(text.replace("  disruption_weights:\n", extra, 1))
    region = load_region(str(path))
    assert region.proposals.scenarios == (
        Scenario("calm", "Parking is precious", {"parking_space": 3.0}),
    )
    assert scenarios_for(region.proposals) == list(region.proposals.scenarios)
    assert region.proposals.frontier_max_projects == 150
    assert region.proposals.recommend_ratio == 0.25


def test_fr8_14_a_heavier_parking_scale_moves_a_parking_project_later():
    mid = street("tertiary", 4, 50, 9000, 14.0)
    graph = star([(400, BUSY), (400, mid)])
    people = {1: 100, 2: 10}
    first = curve(graph, people)
    heavy = curve(graph, people, scenario=Scenario("parking", "Parking", {"parking_space": 4.0}))
    assert first["picks"][0]["parking_spaces"] == 94
    assert heavy["picks"][0]["parking_spaces"] == 0
    assert heavy["picks"][1]["disruption"] == 16.0 + 94 * 4


def test_fr8_14_the_recommended_stop_follows_the_ratio_rule():
    picks = [
        {"rank": 1, "gain": 10.0, "cost": 10.0},
        {"rank": 2, "gain": 5.0, "cost": 10.0},
        {"rank": 3, "gain": 1.0, "cost": 10.0},
        {"rank": 4, "gain": 3.0, "cost": 10.0},
    ]
    assert recommended_stop(picks, 0.25) == 4
    assert recommended_stop(picks, 0.4) == 2
    assert recommended_stop(picks, 1.0) == 1
    assert recommended_stop([], 0.25) is None


def test_fr8_14_the_curve_names_its_recommended_stop():
    graph = star([(400, BUSY), (1900, BUSY)])
    found = curve(graph, {1: 100, 2: 10})
    assert found["id"] == "shipped"
    assert found["label"] == "Weights as set"
    assert found["recommended_stop"] == recommended_stop(
        found["picks"], REGION.proposals.recommend_ratio
    )


def test_fr8_13_the_command_writes_frontier_json_with_a_curve_per_scenario(tmp_path):
    folder = snapshot(tmp_path / "snap")
    out = tmp_path / "out"
    assert run(folder, out) == 0
    data = json.loads((out / "frontier.json").read_text())
    assert [item["id"] for item in data["scenarios"]] == ["light", "shipped", "heavy"]
    shipped = data["scenarios"][1]
    projects = json.loads((out / "projects.json").read_text())
    assert len(shipped["picks"]) >= len(projects)
    assert shipped["recommended_stop"] in {item["rank"] for item in shipped["picks"]}


def test_fr13_15_frontier_json_holds_the_shapes_of_every_pick(tmp_path):
    folder = snapshot(tmp_path / "snap")
    out = tmp_path / "out"
    assert run(folder, out) == 0
    data = json.loads((out / "frontier.json").read_text())
    picked = {pick["id"] for item in data["scenarios"] for pick in item["picks"]}
    shaped = {item["properties"]["project"] for item in data["shapes"]["features"]}
    assert picked == shaped
    assert all("rank" not in item["properties"] for item in data["shapes"]["features"])
    assert all(item["geometry"]["coordinates"] for item in data["shapes"]["features"])


def test_fr8_14_the_stop_compares_each_pick_with_the_best_pick_so_far():
    picks = [
        {"rank": 1, "gain": 1.0, "cost": 10.0},
        {"rank": 2, "gain": 10.0, "cost": 10.0},
        {"rank": 3, "gain": 2.0, "cost": 10.0},
        {"rank": 4, "gain": 3.0, "cost": 10.0},
    ]
    assert recommended_stop(picks, 0.25) == 4
    assert recommended_stop(picks, 0.3) == 4
    assert recommended_stop(picks, 0.5) == 2


def test_fr8_14_the_best_so_far_can_come_after_a_weak_first_pick():
    picks = [
        {"rank": 1, "gain": 1.0, "cost": 10.0},
        {"rank": 2, "gain": 10.0, "cost": 10.0},
        {"rank": 3, "gain": 2.4, "cost": 10.0},
    ]
    assert recommended_stop(picks, 0.25) == 2


def test_fr8_13_the_default_cap_is_150_picks():
    assert (
        load_region("tests/fixtures/test-grid/region.yaml").proposals.frontier_max_projects == 150
    )


def test_fr8_14_a_curve_cut_off_by_the_cap_says_so():
    graph = star([(400, BUSY), (400, BUSY), (400, BUSY)])
    people = {1: 10, 2: 10, 3: 10}
    cut = curve(graph, people, region_with(frontier_max_projects=2))
    whole = curve(graph, people)
    assert cut["cap_reached"] is True
    assert whole["cap_reached"] is False
