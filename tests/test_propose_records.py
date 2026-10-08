import pytest

from bikeplan.propose import Planning, greedy_picks, planning_network, project_records
from tests.test_propose_network import BUSY, PROFILE, REGION
from tests.test_propose_picks import DETOUR, REACH_M, WEIGHTS, chain, star

HIGH = {**BUSY, "name": "High St"}
LOW = {**BUSY, "name": "Low St"}
FIELDS = {
    "rank",
    "id",
    "kind",
    "name",
    "elements",
    "totals",
    "gain",
    "score_after",
    "people",
}


def records(graph, people, place, names):
    planning = planning_network(graph, PROFILE, REGION)
    found = greedy_picks(
        graph,
        planning,
        [("school", place)],
        people,
        WEIGHTS,
        REGION.proposals,
        REACH_M,
        DETOUR,
        names=names,
    )
    return project_records(found, planning)


def test_fr8_6_a_project_record_holds_every_field():
    graph = star([(400, HIGH), (800, LOW)])
    found = records(graph, {1: 30, 2: 10}, 0, ["Test School"])
    assert [item["rank"] for item in found] == [1, 2]
    first = found[0]
    assert set(first) == FIELDS
    assert first["name"] == "Test School: High St"
    assert first["gain"] == 75.0
    assert first["score_after"] == 75.0
    assert first["people"] == {"school": 30.0}
    assert first["elements"] == [
        {
            "id": "segment:s1",
            "street": "High St",
            "length_m": 400.0,
            "fix": "cycleway_parking_both_sides",
            "robust": "robust",
            "width_source": "osm_tag",
            "km": 0.4,
            "parking_spaces": first["totals"]["parking_spaces"],
            "lane_km": 0.0,
            "speed_km": 0.0,
            "signals": 0,
            "refuges": 0,
        }
    ]


def test_fr8_6_the_name_lists_the_street_names_of_a_two_gap_project():
    graph = chain([(300, HIGH), (400, LOW)])
    found = records(graph, {0: 10}, 2, ["Test School"])
    assert len(found) == 1
    assert found[0]["name"] == "Test School: High St, Low St"


def test_fr8_6_totals_add_up_from_the_elements():
    graph = chain([(300, HIGH), (400, LOW)])
    item = records(graph, {0: 10}, 2, ["Test School"])[0]
    totals = item["totals"]
    assert totals["km_by_fix"] == {"cycleway_parking_both_sides": pytest.approx(0.7)}
    assert totals["parking_spaces"] == sum(e["parking_spaces"] for e in item["elements"])
    assert totals["parking_spaces"] > 0
    assert {"lane_km", "speed_km", "signals", "refuges"} <= set(totals)


def test_fr8_6_signals_and_refuges_are_counted_from_junction_elements():
    junction = {"kind": "junction", "score": 4.0, "legs": (), "street": "Side St"}
    planning = Planning(
        {},
        {
            "junction:1": {**junction, "junction": 1, "fix": "signals"},
            "junction:2": {**junction, "junction": 2, "fix": "refuge"},
            "junction:3": {**junction, "junction": 3, "fix": "refuge"},
        },
    )
    picked = [
        {
            "id": "abc",
            "kind": "route",
            "elements": ("junction:1", "junction:2", "junction:3"),
            "gain": 1.0,
            "score_after": 1.0,
            "place": "Test School",
            "people": {"school": 5.0},
        }
    ]
    record = project_records(picked, planning)[0]
    totals = record["totals"]
    assert record["kind"] == "route"
    assert (totals["signals"], totals["refuges"]) == (1, 2)
    assert totals["km_by_fix"] == {}


def test_fr8_6_the_main_place_is_where_most_people_gain_safe_reach():
    graph = star([(400, HIGH), (800, LOW)])
    planning = planning_network(graph, PROFILE, REGION)
    found = greedy_picks(
        graph,
        planning,
        [("school", 0), ("school", 0)],
        {1: 30, 2: 10},
        WEIGHTS,
        REGION.proposals,
        REACH_M,
        DETOUR,
        names=["First", "Second"],
    )
    assert found[0]["place"] == "First"
