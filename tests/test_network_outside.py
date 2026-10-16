import pytest
from shapely.geometry import box

from bikeplan.config import Network, load_profile
from bikeplan.options import ISLAND, build_options, join_places, link_table
from tests.option_helpers import place, street_graph

NODES = {
    0: (0, 0),
    1: (100, 0),
    2: (200, 0),
    3: (600, 0),
    4: (700, 0),
    5: (800, 0),
    8: (300, 0),
    9: (450, 0),
    10: (400, 300),
    20: (5000, 0),
    21: (5100, 0),
}
ROADS = [
    (0, 1, 100.0, 1, False, False),
    (1, 2, 100.0, 1, False, False),
    (3, 4, 100.0, 1, False, False),
    (4, 5, 100.0, 1, False, False),
    (2, 8, 100.0, 2, False, False),
    (8, 9, 150.0, 2, False, False),
    (9, 3, 150.0, 2, False, False),
    (2, 10, 360.0, 1, False, False),
    (10, 3, 360.0, 1, False, False),
    (20, 21, 100.0, 1, False, False),
]
AREA = box(-50, -50, 250, 50).union(box(550, -50, 850, 50))


def network(**changes):
    found = load_profile("au-nsw").network
    return Network(**{**found.__dict__, "boundary_buffer_m": 0.0, **changes})


def halves(roads=ROADS):
    graph, ratings = street_graph(NODES, roads)
    graph.graph["boundary"] = AREA
    return graph, ratings


FOUND = [
    place("node/1", "school", 5, 5),
    place("node/2", "station", 100, 5),
    place("node/3", "school", 800, 5),
]


def test_fr17_1_two_halves_meeting_only_outside_join_by_the_shortest_outside_route():
    graph, _ = halves()
    result = join_places(graph, FOUND, [], network())
    assert [item["id"] for item in result.joined] == ["node/1", "node/2", "node/3"]
    assert result.unjoined == []
    assert result.outside == [(2, 8, 0), (3, 9, 0), (8, 9, 0)]


def test_fr17_1_the_same_route_joins_whichever_part_holds_more_places():
    graph, _ = halves()
    found = [place("node/1", "school", 5, 5), place("node/3", "school", 800, 5)]
    swapped = join_places(graph, found + [place("node/9", "school", 720, 5)], [], network())
    assert swapped.outside == [(2, 8, 0), (3, 9, 0), (8, 9, 0)]


def test_fr17_1_a_place_the_full_graph_cannot_reach_is_unjoined():
    graph, _ = halves([road for road in ROADS if road[:2] not in {(2, 8), (2, 10)}])
    result = join_places(graph, FOUND, [], network())
    assert [item["id"] for item in result.joined] == ["node/1", "node/2"]
    assert [(item["id"], item["reason"]) for item in result.unjoined] == [("node/3", ISLAND)]
    assert result.outside == []
    assert result.counts["school"] == {"joined": 1, "unjoined": 1}


def test_fr17_1_outside_links_are_in_the_table_and_the_options_and_are_labelled():
    graph, ratings = halves()
    joined = join_places(graph, FOUND, [], network())
    table = link_table(graph, ratings, network(), joined.outside)
    outside = {key for key, link in table.items() if link.get("outside")}
    assert outside == {(2, 8, 0), (3, 9, 0), (8, 9, 0)}
    assert not any(link.get("outside") for key, link in table.items() if key not in outside)
    for option in build_options(graph, joined, ratings, network()):
        assert option["outside"] == [(2, 8, 0), (3, 9, 0), (8, 9, 0)]
        assert (2, 8, 0) in option["links"]
        assert option["km"] == pytest.approx(
            sum(table[link]["length_m"] for link in option["links"]) / 1000
        )


def test_fr17_1_an_option_that_stays_inside_has_no_outside_links():
    graph, ratings = halves()
    found = [place("node/1", "school", 5, 5), place("node/2", "station", 100, 5)]
    joined = join_places(graph, found, [], network())
    assert joined.outside == []
    for option in build_options(graph, joined, ratings, network()):
        assert option["outside"] == []


def test_fr17_1_the_outside_route_is_the_same_for_any_node_order():
    first = join_places(halves()[0], FOUND, [], network()).outside
    graph, _ = street_graph(NODES, ROADS, seed=7)
    graph.graph["boundary"] = AREA
    assert join_places(graph, FOUND, [], network()).outside == first
