import networkx as nx
import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.fit import disruption_score, parking_spaces
from bikeplan.ladder import build_ladder, link_fixes
from tests.test_option_ladder import people, row

PROFILE = load_profile("au-nsw")
WEIGHTS = load_region("regions/test-grid.yaml").proposals.disruption_weights
TFNSW = "Transport for NSW"


def road(segment, **extra):
    return {
        "segment_id": segment,
        "bike_ok": True,
        "highway": "residential",
        "lanes_total": 2,
        "speed_kmh": 50,
        "name": segment,
        **extra,
    }


def add_road(graph, a, b, segment, **extra):
    for u, v in ((a, b), (b, a)):
        graph.add_edge(u, v, 0, **road(segment, **extra))


def crossing_world(function=None, lanes=2, speed=50, parking="no"):
    graph = nx.MultiDiGraph()
    for node, xy in {0: (0, 0), 1: (-100, 0), 2: (100, 0), 3: (0, -60)}.items():
        graph.add_node(node, x=xy[0], y=xy[1])
    main = {"lanes_total": lanes, "speed_kmh": speed, "highway": "secondary"}
    main |= {"parking:both": parking, "length_m": 100.0}
    if function:
        main["road_function"] = function
    add_road(graph, 1, 0, "main-w", **main)
    add_road(graph, 0, 2, "main-e", **main)
    add_road(graph, 0, 3, "side", length_m=60.0)
    graph.graph["points"] = []
    table = {(0, 3, 0): row(length=60.0)}
    fits = {"side": {"status": "aaa"}}
    return graph, table, fits


def fixes_for(world):
    graph, table, fits = world
    return link_fixes(graph, table, fits, PROFILE, WEIGHTS)


def test_fr20_2_a_route_across_a_two_lane_50_street_gets_a_raised_zebra_crossing():
    found = fixes_for(crossing_world())[0, 3, 0]
    assert found["fix"] == "raised_zebra_crossing"
    assert found["spot"] is True
    assert found["owner"] is None
    assert found["path_km"] == 0.0


def test_fr20_2_a_route_across_a_two_lane_arterial_gets_signals_owned_by_the_state():
    found = fixes_for(crossing_world("ArterialRoad"))[0, 3, 0]
    assert found["fix"] == "bike_walk_signals"
    assert found["owner"] == TFNSW


def test_fr20_2_a_route_across_a_four_lane_street_gets_signals():
    found = fixes_for(crossing_world(lanes=4))[0, 3, 0]
    assert found["fix"] == "bike_walk_signals"
    assert found["owner"] is None


def test_fr20_2_a_route_across_a_60_street_gets_signals():
    assert fixes_for(crossing_world(speed=60))[0, 3, 0]["fix"] == "bike_walk_signals"


def test_fr20_2_a_zebra_removes_the_rule_172_parking_on_each_parked_kerb():
    found = fixes_for(crossing_world(parking="yes"))[0, 3, 0]
    assert found["parking_spaces"] == parking_spaces(30.0, 2, PROFILE) == 8
    one = crossing_world(parking="yes")
    for _, _, data in one[0].edges(data=True):
        data["parking:left"] = "no"
        data["parking:right"] = "yes"
    assert fixes_for(one)[0, 3, 0]["parking_spaces"] == 4
    assert fixes_for(crossing_world())[0, 3, 0]["parking_spaces"] == 0


def test_fr20_2_signals_label_the_parking_count_assumed_and_a_zebra_does_not():
    assert fixes_for(crossing_world("ArterialRoad", parking="yes"))[0, 3, 0]["assumed"] is True
    assert fixes_for(crossing_world(parking="yes"))[0, 3, 0]["assumed"] is False


def test_fr20_2_the_spot_record_holds_its_disruption_score():
    found = fixes_for(crossing_world(parking="yes"))[0, 3, 0]
    assert found["least"] == pytest.approx(disruption_score(found, WEIGHTS))
    assert found["least"] > 0


def test_fr20_2_a_signalled_junction_needs_no_spot():
    graph, table, fits = crossing_world()
    assert (0, 3, 0) in link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    graph.graph["points"] = [{"x": 0, "y": 3, "signal": True, "refuge": False}]
    assert (0, 3, 0) not in link_fixes(graph, table, fits, PROFILE, WEIGHTS)


def along_world(length, width=None):
    graph = nx.MultiDiGraph()
    for node, x in enumerate((-80, 0, length, length + 80)):
        graph.add_node(node, x=x, y=0)
    extra = {} if width is None else {"footpath_width_m": width}
    busy = {"highway": "secondary", "lanes_total": 4, "speed_kmh": 60, "length_m": length}
    busy |= {"parking:both": "yes", "road_function": "ArterialRoad"} | extra
    add_road(graph, 1, 2, "busy", **busy)
    add_road(graph, 0, 1, "calm-w", length_m=80.0)
    add_road(graph, 2, 3, "calm-e", length_m=80.0)
    graph.graph["points"] = []
    table = {
        (0, 1, 0): row(all_ages=True, length=80.0),
        (1, 2, 0): row(no_fix=True, length=length),
        (2, 3, 0): row(all_ages=True, length=80.0),
    }
    fits = {"busy": {"status": "no_fit"}, "calm-w": None, "calm-e": None}
    return graph, table, fits


def test_fr20_2_80_m_of_a_busy_road_gets_a_short_path_and_crossing():
    found = fixes_for(along_world(80.0, 2.5))[1, 2, 0]
    assert found["fix"] == "short_path_crossing"
    assert found["spot"] is True
    assert found["path_km"] == pytest.approx(0.08)
    assert found["owner"] == TFNSW
    assert found["parking_spaces"] == parking_spaces(30.0, 2, PROFILE)
    assert found["site_check"] is False


def test_fr20_2_150_m_of_a_busy_road_stays_a_blocker():
    assert (1, 2, 0) in fixes_for(along_world(100.0, 2.5))
    assert (1, 2, 0) not in fixes_for(along_world(150.0, 2.5))


def test_fr20_2_a_short_path_with_unknown_footpath_width_needs_a_site_check():
    assert fixes_for(along_world(80.0))[1, 2, 0]["site_check"] is True


def test_fr20_2_a_short_piece_not_between_two_calm_links_stays_a_blocker():
    graph, table, fits = along_world(80.0, 2.5)
    assert (1, 2, 0) in link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    table[2, 3, 0] = row(all_ages=False, no_fix=True, length=80.0)
    assert (1, 2, 0) not in link_fixes(graph, table, fits, PROFILE, WEIGHTS)


def test_fr20_2_spots_join_the_ladder_with_their_disruption_and_owner():
    graph, table, fits = along_world(80.0, 2.5)
    fixes = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    joined = people((1, 0), (2, 3))
    ladder = build_ladder(table, sorted(table), joined, fixes, WEIGHTS)
    (work,) = ladder["works"]
    assert work["fix"] == "short_path_crossing"
    assert work["owner"] == TFNSW
    assert work["spot"] is True
    assert work["path_km"] == pytest.approx(0.08)
    assert work["score"] == pytest.approx(disruption_score(fixes[1, 2, 0], WEIGHTS))
    assert ladder["steps"][-1]["totals"]["score"] > ladder["steps"][0]["totals"]["score"]
    assert ladder["steps"][-1]["disruption"]["path_km"] == pytest.approx(0.08)
    assert ladder["blockers"] == []


def test_fr20_2_two_spots_on_one_street_stay_two_works():
    graph, table, fits = crossing_world()
    graph.add_node(4, x=0, y=60)
    add_road(graph, 0, 4, "side2", length_m=60.0, name="side")
    table[0, 4, 0] = row(length=60.0)
    fits["side2"] = {"status": "aaa"}
    fixes = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    works = build_ladder(table, sorted(table), people((1, 0), (2, 3)), fixes, WEIGHTS)["works"]
    assert [work["fix"] for work in works] == ["raised_zebra_crossing"] * 2
    assert [len(work["links"]) for work in works] == [1, 1]


def test_fr20_2_a_short_piece_beside_a_link_a_work_fixes_becomes_a_spot():
    graph, table, fits = along_world(80.0, 2.5)
    table[2, 3, 0] = row(all_ages=False, length=80.0)
    fits["calm-e"] = {"status": "fix", "fix": "road_diet"}
    fixes = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    assert fixes[2, 3, 0]["fix"] == "road_diet"
    assert fixes[1, 2, 0]["fix"] == "short_path_crossing"
    assert fixes[1, 2, 0]["spot"] is True


def test_fr20_2_a_short_piece_beside_a_no_fix_link_stays_a_blocker():
    graph, table, fits = along_world(80.0, 2.5)
    table[0, 1, 0] = row(all_ages=False, length=80.0)
    table[2, 3, 0] = row(all_ages=False, no_fix=True, length=80.0)
    fits["calm-w"] = {"status": "fix", "fix": "road_diet"}
    assert (1, 2, 0) not in link_fixes(graph, table, fits, PROFILE, WEIGHTS)


def test_fr20_2_the_ladder_reaches_the_full_score_once_a_work_and_its_spot_are_both_built():
    graph, table, fits = along_world(80.0, 2.5)
    table[2, 3, 0] = row(all_ages=False, length=80.0)
    fits["calm-e"] = {"status": "fix", "fix": "road_diet"}
    fixes = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 3)), fixes, WEIGHTS)
    assert ladder["blockers"] == []
    assert {work["fix"] for work in ladder["works"]} == {"road_diet", "short_path_crossing"}
