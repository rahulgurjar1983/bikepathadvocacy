from pathlib import Path

import pytest

from bikeplan.config import ConfigError, Network, load_profile
from bikeplan.options import build_options, join_places
from tests.option_helpers import (
    NODES,
    PATH_ROADS,
    SQUARE_NODES,
    SQUARE_ROADS,
    pinned_places,
    place,
    street_graph,
)

PROFILE_DIR = "profiles"


def network():
    return load_profile("au-nsw").network


def entrance(destination, node, status="confirmed"):
    return {
        "id": f"gate-{destination}",
        "destination": destination,
        "node": node,
        "bike_accessible": True,
        "status": status,
        "source": "test gate survey",
    }


def joined_square(seed=None):
    graph, ratings = street_graph(SQUARE_NODES, SQUARE_ROADS, seed)
    found = pinned_places(SQUARE_NODES, [1, 2, 3, 4], seed)
    return graph, ratings, join_places(graph, found, [], network())


def by_id(options):
    return {item["id"]: item for item in options}


def test_fr17_2_profile_defaults_and_explicit_network_block(tmp_path):
    found = network()
    assert found.stress_factor == (1.0, 1.2, 3.0, 6.0)
    assert found.no_fix_factor == 10.0
    assert found.place_types == ("school", "station", "town_centre")
    assert isinstance(found, Network)
    text = Path("profiles/au-nsw.yaml").read_text()
    text += "network:\n  stress_factor: [1, 2, 4, 8]\n  no_fix_factor: 20\n"
    text += "  place_types: [school, library]\n"
    (tmp_path / "au-nsw.yaml").write_text(text)
    custom = load_profile("au-nsw", tmp_path).network
    assert custom.stress_factor == (1.0, 2.0, 4.0, 8.0)
    assert custom.no_fix_factor == 20.0
    assert custom.place_types == ("school", "library")
    (tmp_path / "au-nsw.yaml").write_text(text.replace("[1, 2, 4, 8]", "[1, 2, 4]"))
    with pytest.raises(ConfigError, match=r"network\.stress_factor"):
        load_profile("au-nsw", tmp_path)


def test_fr17_1_places_join_the_hand_picked_node_or_are_listed_with_a_reason():
    graph, _ = street_graph(NODES, PATH_ROADS)
    found = [
        place("node/1", "school", 5, 5),
        place("node/2", "station", 295, 5),
        place("node/3", "town_centre", 150, 90),
        place("node/4", "town_centre", 150, 90),
        place("node/5", "library", 5, 5),
        place("node/6", "school", 5000, 5000),
        place("node/7", "school", 2000, 10),
    ]
    entrances = [entrance("node/3", 4), entrance("node/4", 4, status="assumed")]
    result = join_places(graph, found, entrances, network())
    nodes = {item["id"]: (item["node"], item["via"]) for item in result.joined}
    assert nodes == {
        "node/1": (0, "nearest"),
        "node/2": (3, "nearest"),
        "node/3": (4, "entrance"),
        "node/4": (5, "nearest"),
    }
    assert [(item["id"], item["reason"]) for item in result.unjoined] == [
        ("node/6", "no bike-legal node within 300 m"),
        ("node/7", "no bike route to the main network"),
    ]
    assert result.counts == {
        "school": {"joined": 1, "unjoined": 2},
        "station": {"joined": 1, "unjoined": 0},
        "town_centre": {"joined": 2, "unjoined": 0},
    }


def test_fr17_2_each_option_is_connected_holds_every_place_and_takes_its_own_road():
    graph, ratings = street_graph(NODES, PATH_ROADS)
    found = [place("node/1", "school", 5, 5), place("node/2", "station", 295, 5)]
    joined = join_places(graph, found, [], network())
    options = by_id(build_options(graph, joined, ratings, network()))
    assert list(options) == ["calm", "shortest", "separated", "mesh"]
    assert [item["name"] for item in options.values()] == [
        "Calm streets",
        "Shortest",
        "Main roads with separation",
        "Mesh",
    ]
    assert options["calm"]["links"] == [(0, 4, 0), (3, 6, 0), (4, 5, 0), (5, 6, 0)]
    assert options["shortest"]["links"] == [(0, 7, 0), (3, 7, 0)]
    assert options["separated"]["links"] == [(0, 1, 0), (1, 2, 0), (2, 3, 0)]
    assert options["mesh"]["links"] == [(0, 7, 0), (3, 7, 0)]
    assert options["calm"]["km"] == pytest.approx(0.5)
    assert options["shortest"]["km"] == pytest.approx(0.28)
    assert options["separated"]["km"] == pytest.approx(0.3)


def test_fr17_2_the_stress_factor_sets_the_calm_weight():
    graph, ratings = street_graph(NODES, PATH_ROADS)
    found = [place("node/1", "school", 5, 5), place("node/2", "station", 295, 5)]
    joined = join_places(graph, found, [], network())
    cheap = Network(stress_factor=(1.0, 1.0, 1.0, 1.0))
    options = by_id(build_options(graph, joined, ratings, cheap))
    assert options["calm"]["links"] == [(0, 7, 0), (3, 7, 0)]


def test_fr17_2_a_link_with_no_fix_costs_the_no_fix_factor_more():
    graph, ratings = street_graph(NODES, PATH_ROADS)
    for key in [(4, 5, 0), (5, 4, 0)]:
        ratings[key] = {"lts": 1, "separated": False, "no_fix": True}
    found = [place("node/1", "school", 5, 5), place("node/2", "station", 295, 5)]
    joined = join_places(graph, found, [], network())
    options = by_id(build_options(graph, joined, ratings, network()))
    assert options["calm"]["links"] == [(0, 7, 0), (3, 7, 0)]


def test_fr17_2_mesh_adds_a_non_crossing_pair_and_skips_a_crossing_one():
    graph, ratings, joined = joined_square()
    options = by_id(build_options(graph, joined, ratings, network()))
    assert options["mesh"]["links"] == [
        (0, 1, 0),
        (0, 2, 0),
        (0, 3, 0),
        (1, 2, 0),
        (2, 3, 0),
    ]
    for name in ("calm", "shortest", "separated"):
        links = options[name]["links"]
        assert len(links) == 3
        assert {node for link in links for node in link[:2]} == {0, 1, 2, 3}
        assert options[name]["km"] == pytest.approx(0.3)


def test_fr17_3_shuffled_input_order_gives_the_same_links():
    graph, ratings, joined = joined_square()
    base = build_options(graph, joined, ratings, network())
    for seed in range(1, 7):
        graph, ratings, joined = joined_square(seed)
        assert build_options(graph, joined, ratings, network()) == base


def test_fr17_3_equal_options_are_marked_same_as_the_first():
    graph, ratings, joined = joined_square()
    options = by_id(build_options(graph, joined, ratings, network()))
    assert [options[name]["same_as"] for name in ("calm", "shortest", "separated", "mesh")] == [
        None,
        "calm",
        "calm",
        None,
    ]
    graph, ratings = street_graph(NODES, PATH_ROADS)
    found = [place("node/1", "school", 5, 5), place("node/2", "station", 295, 5)]
    joined = join_places(graph, found, [], network())
    options = by_id(build_options(graph, joined, ratings, network()))
    assert options["mesh"]["same_as"] == "shortest"
    assert options["calm"]["same_as"] is None
