import networkx as nx

from bikeplan.access import reach
from bikeplan.propose import planning_network, update_reach
from tests.test_propose_network import BUSY, PROFILE, REGION
from tests.test_propose_picks import DETOUR, REACH_M, chain


def two_chains():
    graph = chain([(300, BUSY), (400, BUSY)])
    other = nx.MultiDiGraph()
    for index in range(3):
        other.add_node(10 + index, x=9000.0 + 300 * index, y=0.0)
    for index in range(2):
        other.add_edge(
            10 + index,
            11 + index,
            0,
            segment_id=f"t{index}",
            bike_ok=True,
            length_m=300.0,
            **BUSY,
        )
    return nx.compose(graph, other)


def aaa_for(graph, planning, fixed):
    return {key for key, item in planning.edges.items() if set(item["needs"]) <= fixed}


def test_fr8_9_updated_reach_equals_a_full_recompute():
    graph = two_chains()
    planning = planning_network(graph, PROFILE, REGION)
    sources = [2, 12]
    old = aaa_for(graph, planning, set())
    new = aaa_for(graph, planning, {"segment:s1"})
    before = reach(graph, sources, REACH_M, DETOUR, old)
    updated, _ = update_reach(graph, sources, before, REACH_M, DETOUR, old, new)
    assert updated == reach(graph, sources, REACH_M, DETOUR, new)
    assert updated != before


def test_fr8_9_only_places_within_reach_of_a_changed_edge_are_worked_out_again():
    graph = two_chains()
    planning = planning_network(graph, PROFILE, REGION)
    sources = [2, 12]
    old = aaa_for(graph, planning, set())
    new = aaa_for(graph, planning, {"segment:s1"})
    before = reach(graph, sources, REACH_M, DETOUR, old)
    _, redone = update_reach(graph, sources, before, REACH_M, DETOUR, old, new)
    assert redone == [0]


def test_fr8_9_nothing_is_worked_out_again_when_no_edge_changed():
    graph = two_chains()
    planning = planning_network(graph, PROFILE, REGION)
    old = aaa_for(graph, planning, set())
    before = reach(graph, [2, 12], REACH_M, DETOUR, old)
    same, redone = update_reach(graph, [2, 12], before, REACH_M, DETOUR, old, old)
    assert redone == []
    assert same == before
