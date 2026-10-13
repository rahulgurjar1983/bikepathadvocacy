import networkx as nx
import pytest

from bikeplan.config import load_profile
from bikeplan.options import build_options, join_places, link_table
from bikeplan.rating import model_ratings, option_totals
from bikeplan.stress import score_edges
from tests.option_helpers import NODES, PATH_ROADS, place, street_graph

PROFILE = load_profile("au-nsw")
NETWORK = PROFILE.network
FIX = {"status": "fix", "fix": "cycleway_in_spare"}
CALM = [(0, 4, 0), (4, 5, 0), (5, 6, 0), (6, 3, 0)]
DETOUR = [(0, 7, 0), (7, 3, 0)]


def rated_graph():
    graph = nx.MultiDiGraph(points=[])
    for node in range(4):
        graph.add_node(node, x=node * 100, y=0)
    roads = [
        (0, 1, {}),
        (1, 2, {"speed_source": "default", "adt_source": "default"}),
        (2, 3, {"speed_kmh": 60, "adt": 9000, "highway": "secondary"}),
    ]
    for u, v, extra in roads:
        data = {
            "segment_id": f"s{u}{v}",
            "bike_ok": True,
            "bike_facility": "none",
            "highway": "residential",
            "lanes_total": 2,
            "lanes_dir": 1,
            "oneway": False,
            "speed_kmh": 30,
            "speed_source": "tag",
            "adt": 750,
            "adt_source": "observed",
        } | extra
        for a, b in ((u, v), (v, u)):
            graph.add_edge(a, b, 0, **data)
    return graph


def three_places():
    return [
        place("node/1", "school", 5, 5),
        place("node/2", "station", 295, 5),
        place("node/3", "town_centre", 295, 95),
    ]


def test_fr17_4_model_rating_uses_defaults_and_counts_assumed_inputs():
    graph = rated_graph()
    fits = {"s12": FIX, "s23": {"status": "no_fit"}}
    found = model_ratings(graph, score_edges(graph, PROFILE), fits)
    assert found[0, 1, 0] == {
        "lts": 1,
        "all_ages": True,
        "assumed": False,
        "separated": False,
        "no_fix": False,
    }
    assert found[2, 1, 0] == {
        "lts": 1,
        "all_ages": True,
        "assumed": True,
        "separated": True,
        "no_fix": False,
    }
    assert found[2, 3, 0] == {
        "lts": 3,
        "all_ages": False,
        "assumed": False,
        "separated": False,
        "no_fix": True,
    }
    assert set(found) == set(graph.edges(keys=True))


def test_fr17_4_a_quietway_fix_is_not_a_separated_fix():
    graph = rated_graph()
    fits = {"s12": {"status": "fix", "fix": "quietway"}}
    found = model_ratings(graph, score_edges(graph, PROFILE), fits)
    assert found[1, 2, 0]["separated"] is False


def test_fr17_4_the_link_table_carries_the_rating_and_the_assumed_flag():
    graph, ratings = street_graph(NODES, PATH_ROADS)
    for key in [(0, 4, 0), (4, 0, 0)]:
        ratings[key] = ratings[key] | {"all_ages": True, "assumed": True}
    for key in [(4, 5, 0)]:
        ratings[key] = ratings[key] | {"all_ages": False, "assumed": False}
    ratings[5, 4, 0] = ratings[5, 4, 0] | {"all_ages": True, "assumed": True}
    table = link_table(graph, ratings)
    assert table[0, 4, 0]["all_ages"] is True
    assert table[0, 4, 0]["assumed"] is True
    assert table[4, 5, 0]["all_ages"] is False
    assert table[4, 5, 0]["assumed"] is True


def joined_path():
    graph, ratings = street_graph(NODES, PATH_ROADS)
    return graph, ratings, join_places(graph, three_places(), [], NETWORK)


def test_fr17_5_step_zero_totals_follow_the_shortest_path_inside_the_option():
    graph, ratings, joined = joined_path()
    table = link_table(graph, ratings)
    totals = option_totals(table, CALM + DETOUR, joined.joined)
    assert totals["trips"] == 3
    assert totals["safe_trips"] == 1
    assert totals["score"] == pytest.approx(100 / 3)
    assert totals["km_by_level"] == {1: pytest.approx(0.5), 2: 0.0, 3: pytest.approx(0.28), 4: 0.0}
    assert totals["km_all_ages"] == pytest.approx(0.5)
    assert totals["places_safe"] == {"school": 0, "station": 1, "town_centre": 1}


def test_fr17_5_fixed_links_become_all_ages_at_a_later_step():
    graph, ratings, joined = joined_path()
    table = link_table(graph, ratings)
    totals = option_totals(table, CALM + DETOUR, joined.joined, frozenset(DETOUR))
    assert totals["safe_trips"] == 3
    assert totals["score"] == pytest.approx(100.0)
    assert totals["km_by_level"][1] == pytest.approx(0.78)
    assert totals["km_by_level"][3] == 0.0
    assert totals["km_all_ages"] == pytest.approx(0.78)
    assert totals["places_safe"] == {"school": 1, "station": 1, "town_centre": 1}


def test_fr17_5_an_option_with_one_place_has_no_trips_and_a_zero_score():
    graph, ratings, joined = joined_path()
    table = link_table(graph, ratings)
    totals = option_totals(table, [], joined.joined[:1])
    assert totals["trips"] == 0
    assert totals["score"] == 0.0
    assert totals["places_safe"] == {"school": 0}


def test_fr17_4_the_assumed_share_is_the_km_rated_from_assumed_inputs():
    graph, ratings, joined = joined_path()
    for key in [(0, 4, 0), (4, 0, 0)]:
        ratings[key] = ratings[key] | {"assumed": True}
    table = link_table(graph, ratings)
    totals = option_totals(table, CALM, joined.joined)
    assert totals["assumed_share"] == pytest.approx(0.1 / 0.5)


def test_fr17_5_each_built_option_carries_its_step_zero_totals():
    graph, ratings, joined = joined_path()
    options = {item["id"]: item for item in build_options(graph, joined, ratings, NETWORK)}
    assert options["calm"]["totals"]["safe_trips"] == 3
    assert options["calm"]["totals"]["score"] == pytest.approx(100.0)
    assert options["shortest"]["totals"]["safe_trips"] == 1
    assert options["shortest"]["totals"]["trips"] == 3
