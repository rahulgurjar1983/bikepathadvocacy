import networkx as nx
import pytest

from bikeplan.config import load_profile
from bikeplan.stress import score_edges

PROFILE = load_profile("au-nsw")


def path_graph(width=3.0, access="yes"):
    graph = nx.MultiDiGraph(points=[])
    graph.add_node(1, x=0, y=0)
    graph.add_node(2, x=100, y=0)
    graph.add_edge(
        1,
        2,
        0,
        segment_id="path",
        bike_ok=True,
        bike_facility="off_road",
        highway="path",
        lanes_total=0,
        width_tag_m=width,
        bicycle=access,
    )
    return graph


def crossing_graph(signal=False, refuge=False):
    graph = path_graph()
    graph.add_node(3, x=100, y=100)
    graph.add_node(4, x=100, y=-100)
    graph.add_node(5, x=200, y=0)
    graph.add_edge(
        2,
        5,
        0,
        **graph[1][2][0],
    )
    for u, v in [(3, 2), (2, 4)]:
        graph.add_edge(
            u,
            v,
            0,
            segment_id=f"road-{u}-{v}",
            bike_ok=True,
            bike_facility="none",
            highway="primary",
            lanes_total=4,
            lanes_dir=2,
            oneway=False,
            speed_kmh=40,
            speed_source="tag",
            adt=15000,
            adt_source="observed",
        )
    graph.graph["points"] = [{"x": 100, "y": 5, "signal": signal, "refuge": refuge}]
    return graph


@pytest.mark.parametrize("width,access", [(None, "yes"), (3.0, None)])
def test_fr15_5_path_missing_width_or_access_is_unknown(width, access):
    graph = path_graph(width, access)
    score = score_edges(graph, PROFILE)[1, 2, 0]
    assert score["all_ages_status"] == "unknown"
    assert not score["confirmed_aaa"]
    assert "unknown" in score["safety_reason"]


def test_fr15_5_signal_on_another_approach_does_not_confirm_a_movement():
    graph = crossing_graph(signal=True)
    score = score_edges(graph, PROFILE)[1, 2, 0]
    assert score["all_ages_status"] == "unknown"
    assert not score["confirmed_aaa"]
    assert "phase" in score["safety_reason"]


def test_fr15_5_refuge_with_no_usable_width_is_unknown():
    graph = crossing_graph(refuge=True)
    score = score_edges(graph, PROFILE)[1, 2, 0]
    assert score["all_ages_status"] == "unknown"
    assert "refuge width" in score["safety_reason"]


def test_fr15_5_verified_crossing_is_specific_to_the_movement():
    graph = crossing_graph(signal=True)
    graph.graph["safety_evidence"] = {
        "movements": [
            {
                "incoming": [1, 2, 0],
                "outgoing": [2, 5, 0],
                "source": "signal plan",
                "date": "2026-10-01",
                "protected_phase": True,
                "turning_conflicts": "protected",
                "bicycle_access": True,
            }
        ]
    }
    score = score_edges(graph, PROFILE)[1, 2, 0]
    movement = next(item for item in score["movements"] if item["outgoing"] == [2, 5, 0])
    assert movement["status"] == "confirmed"
    assert movement["source"] == "signal plan"
    other = score_edges(graph, PROFILE)[2, 4, 0]
    assert not other["confirmed_aaa"]


def test_fr15_5_conflicting_turns_do_not_confirm_a_protected_phase():
    graph = crossing_graph(signal=True)
    graph.graph["safety_evidence"] = {
        "movements": [
            {
                "incoming": [1, 2, 0],
                "outgoing": [2, 5, 0],
                "source": "signal plan",
                "date": "2026-10-01",
                "protected_phase": True,
                "turning_conflicts": "permitted",
                "bicycle_access": True,
            }
        ]
    }
    score = score_edges(graph, PROFILE)[1, 2, 0]
    movement = next(item for item in score["movements"] if item["outgoing"] == [2, 5, 0])
    assert movement["status"] == "unknown"
    assert "turning" in movement["reason"]


def test_fr15_5_confirmed_and_assumptions_routes_differ():
    from bikeplan.access import reach
    from bikeplan.stress import eligible_links

    graph = path_graph()
    graph[1][2][0]["length_m"] = 100.0
    graph[1][2][0].update(
        bike_facility="none",
        highway="residential",
        lanes_total=2,
        lanes_dir=1,
        oneway=False,
        speed_kmh=30,
        speed_source="default",
        adt=750,
        adt_source="default",
    )
    scores = score_edges(graph, PROFILE)
    confirmed = reach(graph, [2], 200, 1.25, eligible_links(scores))
    assumed = reach(graph, [2], 200, 1.25, eligible_links(scores, assumptions=True))
    assert 1 not in confirmed[0].safe
    assert 1 in assumed[0].safe
    assert scores[1, 2, 0]["all_ages_status"] == "assumed"


def test_fr15_5_default_access_excludes_assumed_links_in_real_snapshot(tmp_path):
    import json

    from bikeplan import main

    region = "tests/fixtures/test-grid/region.yaml"
    snapshot = "tests/fixtures/test-grid/snapshot"
    confirmed = tmp_path / "confirmed"
    assumed = tmp_path / "assumed"
    assert main(["access", region, "--snapshot", snapshot, "--out", str(confirmed)]) == 0
    assert (
        main(["access", region, "--snapshot", snapshot, "--out", str(assumed), "--assumptions"])
        == 0
    )
    baseline = json.loads((confirmed / "access_summary.json").read_text())
    scenario = json.loads((assumed / "access_summary.json").read_text())
    assert baseline["safety_scenario"] == "confirmed"
    assert baseline["score"] == 0
    assert scenario["safety_scenario"] == "assumptions"
    assert scenario["score"] > baseline["score"]


def test_fr15_5_default_picks_exclude_a_path_with_no_width():
    from bikeplan.config import load_region
    from bikeplan.propose import confirmed_planning, planning_network
    from shapely.geometry import box

    graph = path_graph(width=None)
    graph.graph.update(crs="EPSG:32756", boundary=box(-10, -10, 110, 10))
    graph[1][2][0]["length_m"] = 100.0
    region = load_region("regions/test-grid.yaml")
    model = planning_network(graph, PROFILE, region)
    assert (1, 2, 0) in model.edges
    confirmed = confirmed_planning(graph, PROFILE, model)
    assert (1, 2, 0) not in confirmed.edges
