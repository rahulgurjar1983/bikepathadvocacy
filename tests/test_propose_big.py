from bikeplan.propose import big_projects, greedy_picks, planning_network, project_records
from bikeplan.run import project_summary
from tests.test_fit_summary import street
from tests.test_propose_network import BUSY, HEAVY, PROFILE, REGION, line
from tests.test_propose_picks import DETOUR, REACH_M, WEIGHTS, limits, star

LOCAL = street("residential", 2, 50, 1500, 10.0)


def names(*items):
    return frozenset(f"segment:{item}" for item in items)


def test_fr8_11_each_cell_between_main_roads_is_one_neighbourhood_project():
    graph = line([(300, LOCAL), (400, BUSY), (300, LOCAL)])
    planning = planning_network(graph, PROFILE, REGION)
    found = big_projects(graph, planning, PROFILE)
    assert found[names("s0")] == "neighbourhood"
    assert found[names("s2")] == "neighbourhood"


def test_fr8_11_a_run_of_main_road_between_two_cells_is_a_corridor_project():
    graph = line([(300, LOCAL), (400, BUSY), (400, BUSY), (300, LOCAL)])
    planning = planning_network(graph, PROFILE, REGION)
    found = big_projects(graph, planning, PROFILE)
    assert found[names("s1", "s2")] == "corridor"


def test_fr8_11_a_corridor_is_made_only_where_the_fix_fits():
    graph = line([(300, LOCAL), (400, BUSY), (400, HEAVY), (400, BUSY), (300, LOCAL)])
    planning = planning_network(graph, PROFILE, REGION)
    found = big_projects(graph, planning, PROFILE)
    assert "corridor" not in found.values()


def test_fr8_11_a_main_road_that_reaches_only_one_cell_is_not_a_corridor():
    graph = line([(300, LOCAL), (400, BUSY)])
    planning = planning_network(graph, PROFILE, REGION)
    found = big_projects(graph, planning, PROFILE)
    assert "corridor" not in found.values()


def pick_star(candidates, min_gain):
    graph = star([(400, LOCAL), (400, LOCAL), (400, LOCAL)])
    planning = planning_network(graph, PROFILE, REGION)
    found = candidates(graph, planning)
    return greedy_picks(
        graph,
        planning,
        [("school", 0)],
        {1: 10, 2: 10, 3: 10},
        WEIGHTS,
        limits(min_gain=min_gain),
        REACH_M,
        DETOUR,
        candidates=found,
    )


def test_fr8_11_a_neighbourhood_is_picked_when_no_single_route_fix_gains_enough():
    found = pick_star(lambda graph, planning: big_projects(graph, planning, PROFILE), 50.0)
    assert len(found) == 1
    assert found[0]["kind"] == "neighbourhood"
    assert found[0]["elements"] == ("segment:s1", "segment:s2", "segment:s3")
    assert found[0]["gain"] == 100.0


def test_fr8_11_without_the_neighbourhood_no_route_fix_gains_enough():
    assert pick_star(lambda graph, planning: {}, 50.0) == []


def test_fr8_11_route_fixes_keep_their_own_kind():
    found = pick_star(lambda graph, planning: {}, 1.0)
    assert {item["kind"] for item in found} == {"route"}


def test_fr8_11_the_summary_counts_projects_of_each_kind():
    records = [{"kind": "route"}, {"kind": "corridor"}, {"kind": "route"}]
    for record in records:
        record.update(
            {"totals": {"km_by_fix": {}, "parking_spaces": 0, "lane_km": 0, "speed_km": 0}}
        )
        record["totals"].update({"signals": 0, "refuges": 0})
        record["people"] = {"school": 1}
    found = project_summary(records, ["school"])
    assert found["projects_by_kind"] == {"corridor": 1, "neighbourhood": 0, "route": 2}


def test_fr8_11_records_carry_the_kind():
    graph = star([(400, LOCAL)])
    planning = planning_network(graph, PROFILE, REGION)
    pick = {
        "id": "x",
        "elements": ("segment:s1",),
        "gain": 1.0,
        "score_after": 1.0,
        "place": "School",
        "people": {"school": 1},
        "kind": "corridor",
    }
    assert project_records([pick], planning)[0]["kind"] == "corridor"
