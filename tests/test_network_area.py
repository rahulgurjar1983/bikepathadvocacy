from pathlib import Path

import pytest
from shapely.geometry import box

from bikeplan.config import ConfigError, Network, load_profile
from bikeplan.options import build_options, join_places, link_table
from bikeplan.rating import option_totals, option_trips
from tests.option_helpers import place, street_graph

LINE_NODES = {0: (0, 0), 1: (100, 0), 2: (200, 0), 3: (300, 0), 4: (400, 0), 5: (500, 0)}
LINE_ROADS = [(n, n + 1, 100.0, 1, False, False) for n in range(5)]


def network(**changes):
    found = load_profile("au-nsw").network
    return Network(**{**found.__dict__, **changes})


def line_graph(boundary):
    graph, ratings = street_graph(LINE_NODES, LINE_ROADS)
    graph.graph["boundary"] = boundary
    return graph, ratings


def test_fr17_1_profile_defaults_and_explicit_buffer_and_trip_length(tmp_path):
    found = load_profile("au-nsw").network
    assert found.boundary_buffer_m == 200.0
    assert found.max_trip_km == 5.0
    text = Path("profiles/au-nsw.yaml").read_text()
    (tmp_path / "au-nsw.yaml").write_text(
        text + "network:\n  boundary_buffer_m: 50\n  max_trip_km: 3.5\n"
    )
    custom = load_profile("au-nsw", tmp_path).network
    assert (custom.boundary_buffer_m, custom.max_trip_km) == (50.0, 3.5)
    (tmp_path / "au-nsw.yaml").write_text(text + "network:\n  max_trip_km: 0\n")
    with pytest.raises(ConfigError, match=r"network\.max_trip_km"):
        load_profile("au-nsw", tmp_path)
    (tmp_path / "au-nsw.yaml").write_text(text + "network:\n  boundary_buffer_m: -1\n")
    with pytest.raises(ConfigError, match=r"network\.boundary_buffer_m"):
        load_profile("au-nsw", tmp_path)


def test_fr17_1_a_place_outside_the_boundary_is_not_a_place():
    graph, _ = line_graph(box(-50, -50, 250, 50))
    found = [
        place("node/1", "school", 5, 5),
        place("node/2", "school", 240, 5),
        place("node/3", "school", 300, 5),
        place("node/4", "station", 450, 5),
    ]
    result = join_places(graph, found, [], network())
    assert [item["id"] for item in result.joined] == ["node/1", "node/2"]
    assert result.unjoined == []
    assert result.counts["school"] == {"joined": 2, "unjoined": 0}
    assert result.counts["station"] == {"joined": 0, "unjoined": 0}


def test_fr17_1_a_place_joins_the_nearest_node_inside_the_widened_boundary():
    graph, _ = line_graph(box(-50, -50, 150, 50))
    found = [place("node/1", "school", 140, 5)]
    near = join_places(graph, found, [], network(boundary_buffer_m=100.0))
    assert [(item["id"], item["node"]) for item in near.joined] == [("node/1", 1)]
    tight = join_places(graph, found, [], network(boundary_buffer_m=0.0))
    assert [(item["id"], item["node"]) for item in tight.joined] == [("node/1", 1)]
    far = place("node/2", "school", 152, 5)
    graph.graph["boundary"] = box(-50, -50, 180, 50)
    result = join_places(graph, [far], [], network(boundary_buffer_m=30.0))
    assert [(item["id"], item["node"]) for item in result.joined] == [("node/2", 2)]
    result = join_places(graph, [far], [], network(boundary_buffer_m=10.0))
    assert [(item["id"], item["node"]) for item in result.joined] == [("node/2", 1)]


def test_fr17_1_no_option_link_lies_outside_the_widened_boundary():
    graph, ratings = line_graph(box(-50, -50, 250, 50))
    table = link_table(graph, ratings, network())
    assert {key for key in table} == {(n, n + 1, 0) for n in range(4)}
    found = [place("node/1", "school", 5, 5), place("node/2", "station", 245, 5)]
    joined = join_places(graph, found, [], network())
    for option in build_options(graph, joined, ratings, network()):
        assert option["links"]
        assert all(link[1] <= 4 for link in option["links"])
    narrow = link_table(graph, ratings, network(boundary_buffer_m=0.0))
    assert {key for key in narrow} == {(n, n + 1, 0) for n in range(2)}


def test_fr17_1_a_link_leaving_the_boundary_is_dropped_whole():
    graph, ratings = line_graph(box(-50, -50, 250, 50))
    table = link_table(graph, ratings, network(boundary_buffer_m=0.0))
    assert (2, 3, 0) not in table


def test_fr17_1_a_pair_with_a_route_over_the_limit_is_not_a_trip():
    nodes = {0: (0, 0), 1: (3000, 0), 2: (6000, 0), 3: (6100, 0)}
    roads = [(0, 1, 3000.0, 1, False, False), (1, 2, 3000.0, 1, False, False)]
    roads += [(2, 3, 100.0, 1, False, False)]
    graph, ratings = street_graph(nodes, roads)
    joined = [
        {"id": "node/1", "type": "school", "name": "", "node": 0},
        {"id": "node/2", "type": "school", "name": "", "node": 1},
        {"id": "node/3", "type": "school", "name": "", "node": 2},
    ]
    table = link_table(graph, ratings)
    links = sorted(table)
    limit = 5000.0
    found = option_trips(table, links, joined, limit)
    assert [(a["id"], b["id"]) for a, b, _ in found] == [("node/1", "node/2"), ("node/2", "node/3")]
    totals = option_totals(table, links, joined, max_trip_m=limit)
    assert totals["trips"] == 2
    assert totals["safe_trips"] == 2
    assert option_totals(table, links, joined)["trips"] == 3


def test_fr17_1_the_trip_limit_follows_the_profile_and_the_shortest_route():
    nodes = {0: (0, 0), 1: (4000, 0), 2: (0, 100), 3: (4000, 100)}
    roads = [
        (0, 1, 4000.0, 4, False, False),
        (0, 2, 100.0, 1, False, False),
        (2, 3, 4000.0, 1, False, False),
        (3, 1, 100.0, 1, False, False),
    ]
    graph, ratings = street_graph(nodes, roads)
    table = link_table(graph, ratings)
    joined = [
        {"id": "node/1", "type": "school", "name": "", "node": 0},
        {"id": "node/2", "type": "school", "name": "", "node": 1},
    ]
    keep = [(0, 2, 0), (2, 3, 0), (1, 3, 0)]
    assert len(option_trips(table, keep, joined, 5000.0)) == 1
    assert option_trips(table, keep, joined, 3999.0) == []
