import networkx as nx
from shapely.geometry import box

from bikeplan.access import homes, in_scope_places, snap_points


def road(graph, u, v, highway="residential", bike_ok=True):
    graph.add_edge(u, v, highway=highway, bike_ok=bike_ok)
    graph.add_edge(v, u, highway=highway, bike_ok=bike_ok)


def line_graph(xs, highway="residential"):
    graph = nx.MultiDiGraph()
    for number, x in enumerate(xs):
        graph.add_node(number, x=float(x), y=0.0)
    for number in range(len(xs) - 1):
        road(graph, number, number + 1, highway)
    return graph


def test_fr7_3_a_point_250_m_away_snaps_and_one_350_m_away_is_listed():
    graph = line_graph([0, 100])
    nodes, missed = snap_points([(0.0, 250.0), (0.0, 350.0)], graph)
    assert nodes == [0, None]
    assert missed == [1]


def test_fr7_3_nodes_without_a_bike_legal_edge_are_not_targets():
    graph = line_graph([0, 100, 200])
    graph.add_node(9, x=0.0, y=10.0)
    road(graph, 9, 2, "motorway", bike_ok=False)
    nodes, _ = snap_points([(0.0, 20.0)], graph)
    assert nodes == [0]


def test_fr7_4_a_unit_of_120_people_over_3_residential_nodes_gives_40_each():
    graph = line_graph([10, 50, 90, 400])
    unit = {"polygon": box(0, -50, 100, 50), "people": 120.0}
    result = homes([unit], graph, box(-100, -100, 1000, 100))
    assert result.people == {0: 40.0, 1: 40.0, 2: 40.0}
    assert result.unsnapped == 0


def test_fr7_4_residential_nodes_win_over_other_nodes():
    graph = line_graph([10, 50], "residential")
    graph.add_node(5, x=80.0, y=0.0)
    road(graph, 1, 5, "tertiary")
    unit = {"polygon": box(0, -50, 100, 50), "people": 90.0}
    result = homes([unit], graph, box(-100, -100, 1000, 100))
    assert result.people == {0: 45.0, 1: 45.0}


def test_fr7_4_first_fallback_spreads_over_all_nodes():
    graph = line_graph([10, 50, 90], "tertiary")
    unit = {"polygon": box(0, -50, 100, 50), "people": 90.0}
    result = homes([unit], graph, box(-100, -100, 1000, 100))
    assert result.people == {0: 30.0, 1: 30.0, 2: 30.0}


def test_fr7_4_second_fallback_uses_the_nearest_node():
    graph = line_graph([200, 260])
    unit = {"polygon": box(0, -50, 100, 50), "people": 70.0}
    result = homes([unit], graph, box(-100, -100, 1000, 100))
    assert result.people == {0: 70.0}


def test_fr7_4_a_unit_outside_the_boundary_is_left_out():
    graph = line_graph([10, 50, 1010])
    inside = {"polygon": box(0, -50, 100, 50), "people": 20.0}
    outside = {"polygon": box(1000, -50, 1100, 50), "people": 99.0}
    result = homes([inside, outside], graph, box(-100, -100, 500, 100))
    assert result.people == {0: 10.0, 1: 10.0}


def test_fr7_3_people_with_no_node_in_300_m_are_counted_as_not_snapped():
    graph = line_graph([2000, 2060])
    unit = {"polygon": box(0, -50, 100, 50), "people": 70.0}
    result = homes([unit], graph, box(-100, -100, 1000, 100))
    assert result.people == {}
    assert result.unsnapped == 70.0


def test_fr7_9_a_school_1_km_outside_counts_and_far_ones_do_not():
    boundary = box(0, 0, 1000, 1000)
    found = [
        {"osm_id": "node/1", "x": 2000.0, "y": 500.0},
        {"osm_id": "node/2", "x": 500.0, "y": 500.0},
        {"osm_id": "node/3", "x": 9000.0, "y": 500.0},
    ]
    kept = in_scope_places(found, boundary, 1500.0)
    assert [place["osm_id"] for place in kept] == ["node/1", "node/2"]


def test_fr7_9_a_home_outside_the_boundary_does_not_count():
    graph = line_graph([10, 1010])
    outside = {"polygon": box(1000, -50, 1100, 50), "people": 50.0}
    result = homes([outside], graph, box(0, -100, 500, 100))
    assert result.people == {}
    assert result.unsnapped == 0
