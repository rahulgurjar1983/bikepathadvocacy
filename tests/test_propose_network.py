import networkx as nx
import pytest
from shapely.geometry import box

from bikeplan.config import load_profile, load_region
from bikeplan.propose import planning_network
from tests.test_fit_junction import junction
from tests.test_fit_summary import street

PROFILE = load_profile("au-nsw", "profiles")
REGION = load_region("regions/test-grid.yaml")
WEIGHTS = REGION.proposals.disruption_weights


def line(streets):
    graph = nx.MultiDiGraph(crs="EPSG:32756", points=[], boundary=box(-1000, -1000, 5000, 1000))
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


QUIET = street("residential", 2, 30, 750, 12.0)
BUSY = street("tertiary", 2, 50, 5000, 10.0)
HEAVY = street("primary", 4, 60, 25000, 13.0)


def test_fr8_1_an_aaa_edge_costs_its_length():
    found = planning_network(line([(400, QUIET)]), PROFILE, REGION)
    assert found.edges[(0, 1, 0)] == {"cost": 400.0, "needs": ()}
    assert found.elements == {}


def test_fr8_1_a_fixed_edge_adds_metres_per_point_times_its_segment_score():
    found = planning_network(line([(400, BUSY)]), PROFILE, REGION)
    element = found.elements["segment:s0"]
    assert element["fix"] == "cycleway_parking_both_sides"
    assert element["score"] > 0
    assert found.edges[(0, 1, 0)]["cost"] == pytest.approx(400 + 10 * element["score"])
    assert found.edges[(0, 1, 0)]["needs"] == ("segment:s0",)


def test_fr8_1_metres_per_point_comes_from_the_region():
    region = load_region("regions/test-grid.yaml")
    proposals = region.proposals.__class__(
        **{**region.proposals.__dict__, "metres_per_point": 20.0}
    )
    region = region.__class__(**{**region.__dict__, "proposals": proposals})
    found = planning_network(line([(400, BUSY)]), PROFILE, region)
    assert found.edges[(0, 1, 0)]["cost"] == pytest.approx(
        400 + 20 * found.elements["segment:s0"]["score"]
    )


def test_fr8_1_an_edge_that_needs_a_missing_fix_is_not_in_the_network():
    found = planning_network(line([(250, HEAVY), (400, QUIET)]), PROFILE, REGION)
    assert (0, 1, 0) not in found.edges
    assert (1, 2, 0) in found.edges


def test_fr8_1_edges_bikes_cannot_use_are_not_in_the_network():
    graph = line([(400, QUIET)])
    graph[0][1][0]["bike_ok"] = False
    assert planning_network(graph, PROFILE, REGION).edges == {}


def test_fr8_1_an_edge_held_back_by_a_crossing_pays_half_the_junction_score():
    graph = junction(4, 40)
    graph.graph["boundary"] = box(-1000, -1000, 1000, 1000)
    for _, _, data in graph.edges(data=True):
        data["length_m"] = 100.0
    found = planning_network(graph, PROFILE, REGION)
    score = WEIGHTS.refuge
    assert found.elements["junction:0"]["fix"] == "refuge"
    assert found.elements["junction:0"]["score"] == score
    assert found.edges[(3, 0, 0)]["cost"] == pytest.approx(100 + 10 * score / 2)
    assert found.edges[(3, 0, 0)]["needs"] == ("junction:0",)


def test_fr8_1_a_route_across_a_junction_pays_its_score_once():
    graph = junction(4, 40)
    graph.graph["boundary"] = box(-1000, -1000, 1000, 1000)
    graph.add_edge(0, 3, 0, **graph[3][0][0])
    for _, _, data in graph.edges(data=True):
        data["length_m"] = 100.0
    found = planning_network(graph, PROFILE, REGION)
    score = WEIGHTS.refuge
    both = found.edges[(3, 0, 0)]["cost"] + found.edges[(0, 3, 0)]["cost"]
    assert both == pytest.approx(200 + 10 * score)
