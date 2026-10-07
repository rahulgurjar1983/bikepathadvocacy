import networkx as nx

from bikeplan.access import reach


def link(graph, u, v, length, both=True):
    graph.add_edge(u, v, 0, bike_ok=True, length_m=float(length))
    if both:
        graph.add_edge(v, u, 0, bike_ok=True, length_m=float(length))


def keys(graph):
    return {(u, v, k) for u, v, k in graph.edges(keys=True)}


def test_fr7_5_distances_match_hand_sums_and_stop_at_reach():
    graph = nx.MultiDiGraph()
    link(graph, 0, 1, 100)
    link(graph, 1, 2, 250)
    link(graph, 2, 3, 400)
    result = reach(graph, [0], 700.0, 1.25, keys(graph))[0]
    assert result.within == {0: 0.0, 1: 100.0, 2: 350.0}


def test_fr7_5_the_shorter_of_two_routes_wins():
    graph = nx.MultiDiGraph()
    link(graph, 0, 1, 300)
    link(graph, 1, 2, 300)
    link(graph, 0, 2, 450)
    result = reach(graph, [2], 1000.0, 1.25, keys(graph))[0]
    assert result.within[0] == 450.0


def test_fr7_5_one_way_edges_are_followed_from_home_to_place():
    graph = nx.MultiDiGraph()
    link(graph, 0, 1, 100, both=False)
    link(graph, 1, 2, 100)
    result = reach(graph, [1], 500.0, 1.25, keys(graph))[0]
    assert 0 in result.within
    assert result.within[0] == 100.0
    result = reach(graph, [0], 500.0, 1.25, keys(graph))[0]
    assert 0 in result.within
    assert 1 not in result.within


def test_fr7_5_edges_that_are_not_bike_legal_are_left_out():
    graph = nx.MultiDiGraph()
    link(graph, 0, 1, 100)
    graph.add_edge(1, 2, 0, bike_ok=False, length_m=50.0)
    graph.add_edge(2, 1, 0, bike_ok=False, length_m=50.0)
    result = reach(graph, [1], 500.0, 1.25, keys(graph))[0]
    assert 2 not in result.within


def detour_graph(safe_length):
    graph = nx.MultiDiGraph()
    link(graph, 0, 1, 1000)
    graph.add_edge(0, 2, 0, bike_ok=True, length_m=float(safe_length))
    graph.add_edge(2, 1, 0, bike_ok=True, length_m=0.0)
    graph.add_edge(2, 0, 0, bike_ok=True, length_m=float(safe_length))
    graph.add_edge(1, 2, 0, bike_ok=True, length_m=0.0)
    return graph


def safe_keys(graph):
    return {(u, v, k) for u, v, k in graph.edges(keys=True) if 2 in (u, v)}


def test_fr7_6_a_safe_route_20_percent_longer_passes():
    graph = detour_graph(1200)
    result = reach(graph, [1], 2000.0, 1.25, safe_keys(graph))[0]
    assert result.within[0] == 1000.0
    assert 0 in result.safe


def test_fr7_6_a_safe_route_30_percent_longer_fails():
    graph = detour_graph(1300)
    result = reach(graph, [1], 2000.0, 1.25, safe_keys(graph))[0]
    assert 0 in result.within
    assert 0 not in result.safe


def test_fr7_6_a_safe_route_beyond_reach_fails():
    graph = detour_graph(1200)
    result = reach(graph, [1], 1100.0, 1.25, safe_keys(graph))[0]
    assert 0 in result.within
    assert 0 not in result.safe


def test_fr7_6_no_aaa_edges_means_no_safe_reach():
    graph = detour_graph(1200)
    result = reach(graph, [1], 2000.0, 1.25, set())[0]
    assert result.safe == {1}


def test_fr7_6_a_place_reaches_itself_safely():
    graph = detour_graph(1200)
    result = reach(graph, [1], 2000.0, 1.25, set())[0]
    assert result.within[1] == 0.0
    assert 1 in result.safe
