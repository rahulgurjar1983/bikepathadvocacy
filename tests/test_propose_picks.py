import dataclasses
import hashlib
import math

import networkx as nx
from shapely.geometry import box

from bikeplan.propose import greedy_picks, planning_network
from tests.test_propose_network import BUSY, PROFILE, QUIET, REGION

REACH_M = 2000.0
DETOUR = 1.25
WEIGHTS = {"school": 1.0}


def project_id(names):
    return hashlib.sha256("".join(sorted(names)).encode()).hexdigest()[:16]


def star(arms):
    graph = nx.MultiDiGraph(crs="EPSG:32756", points=[], boundary=box(-5000, -5000, 5000, 5000))
    graph.add_node(0, x=0.0, y=0.0)
    for index, (length, data) in enumerate(arms, start=1):
        angle = math.pi * index / 8
        graph.add_node(index, x=length * math.cos(angle), y=length * math.sin(angle))
        graph.add_edge(
            index, 0, 0, segment_id=f"s{index}", bike_ok=True, length_m=float(length), **data
        )
    return graph


def chain(streets):
    graph = nx.MultiDiGraph(crs="EPSG:32756", points=[], boundary=box(-5000, -5000, 5000, 5000))
    x = 0.0
    for index, (length, data) in enumerate(streets):
        graph.add_node(index, x=x, y=0.0)
        graph.add_node(index + 1, x=x + length, y=0.0)
        graph.add_edge(
            index,
            index + 1,
            0,
            segment_id=f"s{index}",
            bike_ok=True,
            length_m=float(length),
            **data,
        )
        x += length
    return graph


def limits(**changes):
    return dataclasses.replace(REGION.proposals, **changes)


def picks(graph, people, proposals=None, place=None):
    planning = planning_network(graph, PROFILE, REGION)
    if place is None:
        place = max(graph.nodes)
    return greedy_picks(
        graph,
        planning,
        [("school", place)],
        people,
        WEIGHTS,
        proposals or REGION.proposals,
        REACH_M,
        DETOUR,
    )


def test_fr8_4_the_pick_with_less_disruption_per_gain_goes_first():
    graph = star([(400, BUSY), (800, BUSY)])
    found = picks(graph, {1: 10, 2: 10}, place=0)
    assert [item["elements"] for item in found] == [("segment:s1",), ("segment:s2",)]
    assert found[0]["gain"] == found[1]["gain"] == 50.0


def test_fr8_4_the_gain_is_the_exact_change_in_region_score():
    graph = star([(400, BUSY), (800, BUSY)])
    found = picks(graph, {1: 30, 2: 10}, place=0)
    assert [item["gain"] for item in found] == [75.0, 25.0]
    assert [item["score_after"] for item in found] == [75.0, 100.0]


def test_fr8_4_a_pick_that_gains_more_per_disruption_beats_a_bigger_gain():
    graph = star([(400, BUSY), (1900, BUSY)])
    found = picks(graph, {1: 20, 2: 25}, place=0)
    assert found[0]["elements"] == ("segment:s1",)


def test_fr8_4_ties_go_to_the_smallest_id():
    graph = star([(400, BUSY), (400, BUSY)])
    found = picks(graph, {1: 10, 2: 10}, place=0)
    names = sorted([("segment:s1",), ("segment:s2",)], key=project_id)
    assert [item["elements"] for item in found] == names
    assert found[0]["id"] == project_id(names[0])


def test_fr8_4_the_candidate_pool_limits_which_route_fixes_are_tested():
    graph = star([(400, BUSY), (2000, BUSY)])
    full = picks(graph, {1: 10, 2: 40}, limits(candidate_pool=5), place=0)
    one = picks(graph, {1: 10, 2: 40}, limits(candidate_pool=1, max_projects=1), place=0)
    assert len(one) == 1
    assert one[0]["elements"] == full[0]["elements"]


def test_fr8_5_a_route_with_two_gaps_is_one_project():
    graph = chain([(300, BUSY), (400, BUSY)])
    found = picks(graph, {0: 10})
    assert len(found) == 1
    assert found[0]["elements"] == ("segment:s0", "segment:s1")
    assert found[0]["gain"] == 100.0


def test_fr8_5_after_a_pick_its_elements_are_fixed_and_trips_are_worked_out_again():
    graph = chain([(300, BUSY), (400, BUSY), (300, BUSY)])
    found = picks(graph, {0: 10, 1: 30})
    assert [item["elements"] for item in found] == [
        ("segment:s1", "segment:s2"),
        ("segment:s0",),
    ]
    assert [item["score_after"] for item in found] == [75.0, 100.0]


def test_fr8_5_picking_stops_at_max_projects():
    graph = star([(400, BUSY), (800, BUSY)])
    found = picks(graph, {1: 10, 2: 10}, limits(max_projects=1), place=0)
    assert len(found) == 1


def test_fr8_5_picking_stops_when_the_fixed_km_reach_the_budget():
    graph = star([(400, BUSY), (800, BUSY)])
    found = picks(graph, {1: 10, 2: 10}, limits(budget_km=0.4), place=0)
    assert [item["elements"] for item in found] == [("segment:s1",)]


def test_fr8_5_picking_stops_when_the_best_gain_is_under_the_minimum():
    graph = star([(400, BUSY), (800, BUSY)])
    found = picks(graph, {1: 99, 2: 1}, limits(min_gain=5.0), place=0)
    assert [item["elements"] for item in found] == [("segment:s1",)]


def test_fr8_5_nothing_is_picked_when_every_trip_is_already_safe():
    graph = star([(400, QUIET)])
    assert picks(graph, {1: 10}, place=0) == []
