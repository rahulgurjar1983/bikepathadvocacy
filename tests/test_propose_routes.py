from shapely.geometry import box

from bikeplan.access import Reach
from bikeplan.propose import planning_network, route_fixes
from tests.test_propose_network import BUSY, PROFILE, QUIET, REGION, line

REACH_M = 2000.0
DETOUR = 1.25


def fixes(graph, placed, results, values):
    planning = planning_network(graph, PROFILE, REGION)
    return route_fixes(graph, planning, placed, results, values, REACH_M, DETOUR)


def test_fr8_3_a_route_fix_holds_the_elements_of_the_planned_route():
    graph = line([(100, QUIET), (400, BUSY)])
    results = [Reach({2: 0.0, 1: 400.0, 0: 500.0}, set())]
    found = fixes(graph, [("school", 2)], results, {(0, 0): 5.0})
    assert found == {frozenset({"segment:s1"}): 5.0}


def test_fr8_3_two_homes_on_the_same_route_merge_and_their_values_add_up():
    graph = line([(100, QUIET), (400, BUSY)])
    results = [Reach({2: 0.0, 1: 400.0, 0: 500.0}, set())]
    found = fixes(graph, [("school", 2)], results, {(0, 0): 5.0, (0, 1): 2.5})
    assert found == {frozenset({"segment:s1"}): 7.5}


def test_fr8_3_a_route_over_the_detour_limit_is_dropped():
    graph = line([(100, QUIET), (400, BUSY)])
    results = [Reach({2: 0.0, 1: 400.0, 0: 300.0}, set())]
    found = fixes(graph, [("school", 2)], results, {(0, 0): 5.0, (0, 1): 2.5})
    assert found == {frozenset({"segment:s1"}): 2.5}


def test_fr8_3_a_route_longer_than_reach_is_dropped():
    graph = line([(1500, QUIET), (600, BUSY)])
    results = [Reach({2: 0.0, 1: 600.0, 0: 2100.0}, set())]
    found = fixes(graph, [("school", 2)], results, {(0, 0): 5.0, (0, 1): 2.5})
    assert found == {frozenset({"segment:s1"}): 2.5}


def test_fr8_3_routes_that_need_different_elements_stay_apart():
    graph = line([(300, BUSY), (400, BUSY)])
    results = [Reach({2: 0.0, 1: 400.0, 0: 700.0}, set())]
    found = fixes(graph, [("school", 2)], results, {(0, 0): 5.0, (0, 1): 2.5})
    assert found == {
        frozenset({"segment:s0", "segment:s1"}): 5.0,
        frozenset({"segment:s1"}): 2.5,
    }


def test_fr8_7_an_element_in_the_buffer_is_never_in_a_route_fix():
    graph = line([(400, QUIET), (400, BUSY)])
    graph.graph["boundary"] = box(-10, -10, 300, 10)
    results = [Reach({2: 0.0, 1: 400.0, 0: 800.0}, set())]
    assert fixes(graph, [("school", 2)], results, {(0, 0): 5.0, (0, 1): 2.5}) == {}


def test_fr8_7_an_element_inside_the_boundary_is_kept():
    graph = line([(400, QUIET), (400, BUSY)])
    graph.graph["boundary"] = box(-10, -10, 600, 10)
    results = [Reach({2: 0.0, 1: 400.0, 0: 800.0}, set())]
    found = fixes(graph, [("school", 2)], results, {(0, 0): 5.0})
    assert found == {frozenset({"segment:s1"}): 5.0}
