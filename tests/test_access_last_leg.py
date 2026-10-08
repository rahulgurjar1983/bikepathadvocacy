import networkx as nx

from bikeplan.access import last_legs, reach


def street(graph, u, v, length, highway="residential"):
    for a, b in ((u, v), (v, u)):
        graph.add_edge(a, b, 0, bike_ok=True, length_m=float(length), highway=highway)


def scores(graph, lts, aaa):
    return {
        key: {"lts": lts.get(frozenset(key[:2]), 1), "aaa": frozenset(key[:2]) in aaa}
        for key in graph.edges(keys=True)
    }


def town(leg_length, middle=2, cross=None):
    graph = nx.MultiDiGraph()
    street(graph, 0, 1, leg_length / 2)
    street(graph, 1, 3, leg_length / 2)
    street(graph, 3, 2, 500, "cycleway")
    lts = {frozenset((0, 1)): middle}
    aaa = {frozenset((3, 2))}
    if cross is not None:
        street(graph, 1, 9, 50, "primary")
        lts[frozenset((1, 9))] = cross
    return graph, scores(graph, lts, aaa)


def run(graph, table_scores, leg_m, source=2, home=0):
    aaa = {key for key, item in table_scores.items() if item["aaa"]}
    legs = last_legs(graph, table_scores, [home], leg_m) if leg_m else None
    result = reach(graph, [source], 2000.0, 1.25, aaa, legs=legs)[0]
    return home in result.safe


def test_fr7_11_a_home_150_m_along_a_calm_street_is_safe_with_the_default():
    graph, table = town(150)
    assert run(graph, table, 200)


def test_fr7_11_a_home_250_m_along_a_calm_street_is_not_safe():
    graph, table = town(250)
    assert not run(graph, table, 200)


def test_fr7_11_a_last_leg_of_zero_turns_the_allowance_off():
    graph, table = town(150)
    assert not run(graph, table, 0)


def test_fr7_11_a_stress_3_first_stretch_is_not_allowed():
    graph, table = town(150, middle=3)
    assert not run(graph, table, 200)


def test_fr7_11_a_first_stretch_that_crosses_a_level_4_road_is_not_safe():
    graph, table = town(150, cross=4)
    assert not run(graph, table, 200)


def test_fr7_11_a_first_stretch_on_a_main_road_is_not_allowed():
    graph = nx.MultiDiGraph()
    street(graph, 0, 1, 100, "secondary")
    street(graph, 1, 2, 500, "cycleway")
    table = scores(graph, {}, {frozenset((1, 2))})
    assert not run(graph, table, 200)


def test_fr7_11_the_detour_rule_applies_to_the_whole_route():
    graph, table = town(150)
    street(graph, 0, 2, 400, "primary")
    table = scores(graph, {frozenset((0, 2)): 4}, {frozenset((3, 2))})
    assert not run(graph, table, 200)
