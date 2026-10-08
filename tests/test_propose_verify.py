import json

from bikeplan.access import last_legs, reach
from bikeplan.propose import greedy_picks, planning_network, update_reach
from tests.test_access_last_leg import town
from tests.test_propose_big import LOCAL
from tests.test_propose_network import PROFILE, REGION
from tests.test_propose_picks import DETOUR, REACH_M, WEIGHTS, limits, star
from tests.test_run import COMMITTED, run_command


def test_fr8_12_the_picker_reports_how_many_candidates_it_saw():
    graph = star([(400, LOCAL), (400, LOCAL), (400, LOCAL)])
    planning = planning_network(graph, PROFILE, REGION)
    stats = {}
    picked = greedy_picks(
        graph,
        planning,
        [("school", 0)],
        {1: 10, 2: 10, 3: 10},
        WEIGHTS,
        limits(min_gain=500.0),
        REACH_M,
        DETOUR,
        stats=stats,
    )
    assert picked == []
    assert stats["candidates"] == 3


def test_fr8_12_the_run_summary_holds_the_candidate_count(tmp_path):
    assert run_command(COMMITTED, tmp_path / "out") == 0
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["candidates"] >= summary["projects"] >= 1


def test_fr8_12_a_refresh_keeps_the_last_leg_allowance():
    graph, table = town(150, cross=2)
    aaa = {key for key, item in table.items() if item["aaa"]}
    legs = last_legs(graph, table, [0], 200)
    before = reach(graph, [2], 2000.0, 1.25, aaa, legs=legs)
    assert 0 in before[0].safe
    after, redone = update_reach(
        graph, [2], before, 2000.0, 1.25, aaa, aaa | {(1, 9, 0)}, legs=legs
    )
    assert redone == [0]
    assert 0 in after[0].safe
