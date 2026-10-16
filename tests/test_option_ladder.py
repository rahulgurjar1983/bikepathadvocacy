from itertools import pairwise

import networkx as nx
import pytest

from bikeplan.config import DisruptionWeights, load_profile
from bikeplan.ladder import build_ladder, link_fixes, link_streets
from bikeplan.options import link_table
from bikeplan.rating import model_ratings
from bikeplan.stress import score_edges

PROFILE = load_profile("au-nsw")
WEIGHTS = DisruptionWeights(1.0, 40.0, 2.0, 15.0, 3.0, 5.0)


def row(level=3, all_ages=False, no_fix=False, length=100.0):
    return {
        "length_m": length,
        "level": level,
        "separated": False,
        "no_fix": no_fix,
        "all_ages": all_ages,
        "assumed": False,
    }


def fix(street, name="cycleway_in_spare", parking=0, lane=0.0, speed=0.0, path=0.0):
    return {
        "street": street,
        "fix": name,
        "parking_spaces": parking,
        "lane_km": lane,
        "speed_km": speed,
        "path_km": path,
    }


def people(*pairs):
    return [{"id": f"node/{n}", "type": "school", "name": "", "node": node} for n, node in pairs]


def chain(count=3):
    return {(i, i + 1, 0): row() for i in range(count)}


def test_fr17_6_next_links_on_one_street_with_one_fix_join_into_one_work():
    table = chain(4)
    fixes = {
        (0, 1, 0): fix("High St", parking=3, path=0.1),
        (1, 2, 0): fix("High St", parking=2, path=0.1),
        (2, 3, 0): fix("Low St", parking=4),
        (3, 4, 0): fix("High St", parking=1),
    }
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 4)), fixes, WEIGHTS)
    works = {tuple(item["links"]): item for item in ladder["works"]}
    assert sorted(works) == [((0, 1, 0), (1, 2, 0)), ((2, 3, 0),), ((3, 4, 0),)]
    joined = works[(0, 1, 0), (1, 2, 0)]
    assert joined["street"] == "High St"
    assert joined["fix"] == "cycleway_in_spare"
    assert joined["parking_spaces"] == 5
    assert joined["path_km"] == pytest.approx(0.2)
    assert joined["km"] == pytest.approx(0.2)
    assert joined["score"] == pytest.approx(5 + 0.2 * 5)


def test_fr17_6_next_links_with_different_fixes_stay_separate_works():
    table = chain(2)
    fixes = {
        (0, 1, 0): fix("High St", name="cycleway_in_spare"),
        (1, 2, 0): fix("High St", name="road_diet", lane=0.1),
    }
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 2)), fixes, WEIGHTS)
    assert [item["fix"] for item in ladder["works"]] == ["cycleway_in_spare", "road_diet"]


def test_fr17_6_a_link_with_no_fix_is_listed_by_street_and_never_becomes_all_ages():
    table = chain(3)
    table[1, 2, 0] = row(no_fix=True)
    table[2, 3, 0] = row(no_fix=True)
    fixes = {(0, 1, 0): fix("High St")}
    streets = {(1, 2, 0): "Hill Rd", (2, 3, 0): "Hill Rd"}
    ladder = build_ladder(
        table, sorted(table), people((1, 0), (2, 1), (3, 3)), fixes, WEIGHTS, streets=streets
    )
    assert ladder["no_fix"] == [
        {"street": "Hill Rd", "links": [(1, 2, 0), (2, 3, 0)], "km": pytest.approx(0.2)}
    ]
    last = ladder["steps"][-1]["totals"]
    assert last["km_all_ages"] == pytest.approx(0.1)
    assert last["safe_trips"] == 1
    assert last["km_by_level"][3] == pytest.approx(0.2)


def test_fr17_7_the_ladder_runs_in_hand_worked_order_with_running_totals():
    table = chain(3)
    fixes = {
        (0, 1, 0): fix("A St", parking=1),
        (1, 2, 0): fix("B St", parking=1),
        (2, 3, 0): fix("C St", parking=100),
    }
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 1), (3, 3)), fixes, WEIGHTS)
    assert [item["score"] for item in ladder["works"]] == [1.0, 1.0, 100.0]
    assert [step["works"] for step in ladder["steps"]] == [[], [0], [1, 2]]
    assert [step["totals"]["safe_trips"] for step in ladder["steps"]] == [0, 1, 3]
    assert [step["totals"]["trips"] for step in ladder["steps"]] == [3, 3, 3]
    assert [step["disruption"]["parking_spaces"] for step in ladder["steps"]] == [0, 1, 102]
    assert [step["disruption"]["score"] for step in ladder["steps"]] == [0.0, 1.0, 102.0]
    assert ladder["steps"][2]["totals"]["km_by_level"][1] == pytest.approx(0.3)
    assert ladder["steps"][2]["totals"]["places_safe"] == {"school": 3}


def test_fr17_7_a_step_can_add_several_works_when_one_alone_makes_no_trip_safe():
    table = chain(3)
    fixes = {
        (0, 1, 0): fix("A St", parking=5),
        (1, 2, 0): fix("B St", parking=1),
        (2, 3, 0): fix("C St", parking=1),
    }
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 1), (3, 3)), fixes, WEIGHTS)
    assert [step["works"] for step in ladder["steps"]] == [[], [0, 1, 2]]
    assert ladder["steps"][1]["totals"]["safe_trips"] == 3


def test_fr17_7_a_single_trip_that_needs_every_work_climbs_in_one_step():
    table = chain(3)
    fixes = {(i, i + 1, 0): fix(f"Street {i}") for i in range(3)}
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 3)), fixes, WEIGHTS)
    assert [step["works"] for step in ladder["steps"]] == [[], [0, 1, 2]]
    assert ladder["steps"][1]["totals"]["score"] == pytest.approx(100.0)


def test_fr17_7_a_trip_blocked_by_a_no_fix_link_is_never_taken():
    table = chain(2)
    table[1, 2, 0] = row(no_fix=True)
    fixes = {(0, 1, 0): fix("A St", parking=2)}
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 1), (3, 2)), fixes, WEIGHTS)
    assert [step["works"] for step in ladder["steps"]] == [[], [0]]
    assert [step["totals"]["safe_trips"] for step in ladder["steps"]] == [0, 1]


def test_fr17_7_ties_break_by_the_place_ids_of_the_trip():
    table = {(0, 1, 0): row(), (2, 3, 0): row()}
    fixes = {(0, 1, 0): fix("A St", parking=2), (2, 3, 0): fix("B St", parking=2)}
    joined = people((20, 0), (21, 1), (10, 2), (11, 3))
    ladder = build_ladder(table, sorted(table), joined, fixes, WEIGHTS)
    assert [step["works"] for step in ladder["steps"]] == [[], [1], [0]]


def test_fr17_7_every_step_makes_at_least_one_more_trip_safe():
    table = chain(3)
    fixes = {(i, i + 1, 0): fix(f"Street {i}", parking=i + 1) for i in range(3)}
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 1), (3, 3)), fixes, WEIGHTS)
    safe = [step["totals"]["safe_trips"] for step in ladder["steps"]]
    assert all(later > earlier for earlier, later in pairwise(safe))
    assert safe[-1] == 3


def test_fr17_7_an_option_with_nothing_to_fix_has_only_step_zero():
    table = {(0, 1, 0): row(level=1, all_ages=True)}
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 1)), {}, WEIGHTS)
    assert len(ladder["steps"]) == 1
    assert ladder["steps"][0]["totals"]["safe_trips"] == 1
    assert ladder["works"] == []


def fix_graph():
    graph = nx.MultiDiGraph(points=[])
    for node in range(3):
        graph.add_node(node, x=node * 100, y=0)
    roads = [
        (0, 1, {"name": "Park Rd", "parking:right": "lane", "parking:left": "no"}),
        (1, 2, {"name": ["Hill Rd", "Hill Lane"], "speed_kmh": 60, "adt": 9000}),
    ]
    for u, v, extra in roads:
        data = {
            "segment_id": f"s{u}{v}",
            "bike_ok": True,
            "bike_facility": "none",
            "highway": "secondary",
            "length_m": 100.0,
            "lanes_total": 2,
            "lanes_dir": 1,
            "oneway": False,
            "speed_kmh": 50,
            "speed_source": "tag",
            "adt": 6000,
            "adt_source": "observed",
        } | extra
        for a, b in ((u, v), (v, u)):
            graph.add_edge(a, b, 0, **data)
    return graph


def test_fr17_6_link_fixes_count_the_disruption_of_the_least_disruptive_fix_per_link():
    graph = fix_graph()
    fits = {
        "s01": {"status": "fix", "fix": "cycleway_parking_one_side"},
        "s12": {"status": "no_fit"},
    }
    ratings = model_ratings(graph, score_edges(graph, PROFILE), fits)
    table = link_table(graph, ratings)
    assert table[0, 1, 0]["all_ages"] is False
    found = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    assert set(found) == {(0, 1, 0)}
    assert found[0, 1, 0]["street"] == "Park Rd"
    assert found[0, 1, 0]["fix"] == "cycleway_parking_one_side"
    assert found[0, 1, 0]["parking_spaces"] == 12
    assert found[0, 1, 0]["lane_km"] == 0.0


def test_fr17_6_link_fixes_name_a_street_from_a_list_of_names_and_skip_no_fit():
    graph = fix_graph()
    fits = {
        "s01": {"status": "no_fit"},
        "s12": {"status": "fix", "fix": "road_diet"},
    }
    ratings = model_ratings(graph, score_edges(graph, PROFILE), fits)
    table = link_table(graph, ratings)
    found = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    assert set(found) == {(1, 2, 0)}
    assert found[1, 2, 0]["street"] == "Hill Rd"
    assert found[1, 2, 0]["lane_km"] == pytest.approx(0.1)
    assert found[1, 2, 0]["parking_spaces"] == 0


def test_fr17_6_link_streets_name_every_link_and_fall_back_for_unnamed_roads():
    graph = fix_graph()
    graph.remove_edges_from([(1, 2, 0), (2, 1, 0)])
    graph.add_edge(1, 2, 0, bike_ok=True, length_m=100.0, highway="residential")
    graph.add_edge(2, 1, 0, bike_ok=True, length_m=100.0, highway="residential")
    assert link_streets(graph) == {(0, 1, 0): "Park Rd", (1, 2, 0): "unnamed residential road"}
