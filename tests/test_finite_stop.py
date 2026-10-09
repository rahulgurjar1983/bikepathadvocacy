import json
import re

import pytest

from bikeplan.change import change_figures, change_section, frontier_data
from bikeplan.propose import greedy_picks, planning_network, recommended_stop
from bikeplan.run import dump
from tests.test_propose_frontier import curve, region_with
from tests.test_propose_network import BUSY, PROFILE, REGION
from tests.test_propose_picks import DETOUR, REACH_M, WEIGHTS, limits, project_id, star


@pytest.mark.parametrize(
    ("values", "ratio", "stop"),
    [
        ([(1, 0), (10, 1)], 0.25, 2),
        ([(1, 0), (10, 1), (1, 1), (3, 1)], 0.25, 4),
        ([(2, 0), (4, 1)], 1.0, 2),
    ],
    ids=["free-then-paid", "late-recovery", "equal-ratios"],
)
def test_fr15_1_finite_ratios_include_the_current_pick(values, ratio, stop):
    picks = [
        {"rank": rank, "gain": gain, "cost": cost} for rank, (gain, cost) in enumerate(values, 1)
    ]
    assert recommended_stop(picks, ratio) == stop


@pytest.mark.parametrize("people,stop", [({1: 100, 2: 1, 3: 1}, 1), ({1: 10, 2: 10, 3: 10}, 2)])
def test_fr15_1_cap_is_separate_from_stop(people, stop):
    found = curve(star([(400, BUSY)] * 3), people, region_with(frontier_max_projects=2))
    assert found["recommended_stop"] == stop
    assert found["termination_reason"] == "project_cap"
    assert found["evaluated_projects"] == 2
    assert found["truncated"] is True
    assert found["cap_reached"] is True


def test_fr15_1_positive_pool_exhaustion_keeps_stable_ties():
    found = curve(star([(400, BUSY)] * 3), {1: 10, 2: 10, 3: 10})
    assert found["termination_reason"] == "candidate_pool_exhausted"
    assert found["evaluated_projects"] == 3
    assert found["truncated"] is False
    assert all(pick["gain"] > 0 for pick in found["picks"])
    assert [pick["id"] for pick in found["picks"]] == sorted(
        project_id([f"segment:s{index}"]) for index in (1, 2, 3)
    )


def test_fr15_1_no_gain_is_not_an_empty_pool():
    graph = star([(400, BUSY)])
    stats = {}
    found = greedy_picks(
        graph,
        planning_network(graph, PROFILE, REGION),
        [("school", 0)],
        {1: 1},
        WEIGHTS,
        limits(min_gain=101),
        REACH_M,
        DETOUR,
        stats=stats,
    )
    assert found == []
    assert stats["candidates"] == 1
    assert stats["termination_reason"] == "no_gain"


@pytest.mark.parametrize("small", [1e-7, 1e-10])
def test_fr8_14_positive_gains_survive_curve_and_report_json(small):
    found = curve(star([(400, BUSY)] * 2), {1: 100, 2: small})
    assert len(found["picks"]) == 2
    expected = 100 * small / (100 + small)
    assert found["picks"][1]["gain"] == pytest.approx(expected, rel=1e-14, abs=0)
    raw = {"scenarios": [found]}
    saved = json.loads(dump(frontier_data(raw, 0, ["school"], {})))
    assert saved["scenarios"][0]["picks"][2]["gain"] == expected


def report_section(people):
    found = curve(star([(400, BUSY)] * 3), people, region_with(frontier_max_projects=2))
    data = frontier_data({"scenarios": [found]}, 0, ["school"], {})
    figures = {item["id"]: item for item in change_figures(data, json.dumps(data))}
    return change_section(data, figures)


def test_fr15_1_report_explains_the_finite_best_so_far_rule():
    section = report_section({1: 100, 2: 1, 3: 1})
    text = re.sub("<[^>]+>", " ", section)
    assert "cost plus one" in text
    assert "best ratio so far" in text
    assert "including this pick" in text
    assert "0.25" in text
    assert "last rank" in text
    assert "first project gained" not in text


def test_fr8_14_report_discloses_cap_after_an_earlier_stop():
    section = report_section({1: 100, 2: 1, 3: 1})
    note = re.search(r'id="change-capped".*?</p>', section, re.S)
    assert note is not None
    assert "cap" in note.group()
    assert "2" in note.group()
    assert "stop was still on its last project" not in note.group()


def test_fr15_1_figure_method_matches_the_stop_rule():
    found = curve(star([(400, BUSY)] * 3), {1: 100, 2: 1, 3: 1})
    data = frontier_data({"scenarios": [found]}, 0, ["school"], {})
    figure = next(item for item in change_figures(data, json.dumps(data)) if item["id"] == "F13")
    assert "cost plus one" in figure["method"]
    assert "best ratio so far" in figure["method"]
    assert "including this pick" in figure["method"]
    assert "full precision" in figure["method"]
    assert "first project" not in figure["method"]


def test_fr15_1_ratio_links_to_the_stop_figure_method():
    found = curve(star([(400, BUSY)] * 3), {1: 100, 2: 1, 3: 1})
    data = frontier_data({"scenarios": [found]}, 0, ["school"], {})
    figures = {item["id"]: item for item in change_figures(data, json.dumps(data))}
    section = change_section(data, figures)
    assert '<a href="#F13">0.25</a>' in section
    assert "0.25" in figures["F13"]["method"]
