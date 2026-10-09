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
    from shapely.geometry import box

    from bikeplan.config import load_region
    from bikeplan.propose import confirmed_planning, planning_network

    graph = path_graph(width=None)
    graph.graph.update(crs="EPSG:32756", boundary=box(-10, -10, 110, 10))
    graph[1][2][0]["length_m"] = 100.0
    region = load_region("regions/test-grid.yaml")
    model = planning_network(graph, PROFILE, region)
    assert (1, 2, 0) in model.edges
    confirmed = confirmed_planning(graph, PROFILE, model)
    assert (1, 2, 0) not in confirmed.edges


def test_fr15_5_public_page_qualifies_all_ages_status():
    import json
    from html.parser import HTMLParser

    from bikeplan.config import load_region
    from bikeplan.report import figure_list, page, segments_text

    class Text(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    region = load_region("regions/test-grid.yaml")
    map_text = json.dumps({"segments": [], "projects": {}, "places": [], "boundary": {}})
    figures = figure_list(segments_text([]), map_text)
    rendered = page(region, figures, map_text, "", "")
    parser = Text()
    parser.feed(rendered)
    visible = " ".join(parser.parts).lower()
    assert "meets the model's all-ages criteria" in visible
    assert "does not guarantee child safety" in visible
    assert "safe for a child to ride alone" not in visible
    assert "street that is safe for a child or an older rider" not in visible


def test_fr15_5_assumptions_do_not_override_recorded_turning_conflicts():
    graph = crossing_graph(signal=True)
    graph.graph["safety_evidence"] = {
        "movements": [
            {
                "incoming": [1, 2, 0],
                "outgoing": [2, 5, 0],
                "source": "test signal plan",
                "date": "2026-10-01",
                "protected_phase": True,
                "turning_conflicts": "permitted",
                "bicycle_access": True,
            }
        ]
    }
    score = score_edges(graph, PROFILE, assumptions=True)[1, 2, 0]
    movement = next(item for item in score["movements"] if item["outgoing"] == [2, 5, 0])
    assert movement["status"] == "unknown"
    assert not score["confirmed_aaa"]


def test_fr15_5_stress_export_does_not_count_unknown_paths_as_confirmed():
    from shapely.geometry import box

    from bikeplan.stress import stress_features, stress_summary

    graph = path_graph(width=None)
    graph.graph.update(crs="EPSG:32756", boundary=box(-10, -10, 110, 10))
    graph[1][2][0]["length_m"] = 100.0
    scores = score_edges(graph, PROFILE)
    properties = stress_features(graph, scores)[0]["properties"]
    assert properties["aaa"] is False
    assert properties["model_aaa"] is True
    assert properties["all_ages_status"] == "unknown"
    assert stress_summary(graph, scores)["km_aaa"] == 0


def test_fr15_5_public_map_rows_use_confirmed_links():
    from shapely.geometry import box

    from bikeplan.report import segment_rows

    graph = path_graph(width=None)
    graph.graph.update(crs="EPSG:32756", boundary=box(-10, -10, 110, 10))
    graph[1][2][0]["length_m"] = 100.0
    rows = segment_rows(graph, PROFILE, {})
    assert rows[0][3] == 0


def test_fr15_5_route_crossing_names_unverified_phase(tmp_path):
    from bikeplan.config import load_region
    from bikeplan.network import build
    from bikeplan.review import route_figures
    from bikeplan.route import read_route
    from tests.route_helpers import REGION, SNAPSHOT, densify, lonlat, write_gpx_track

    region = load_region(REGION)
    graph = build(SNAPSHOT, region, PROFILE)
    route = write_gpx_track(tmp_path / "route.gpx", lonlat(densify([(200, 600), (600, 600)])))
    result = route_figures(graph, PROFILE, read_route(route))["total"]
    crossing = result["crossings"][0]
    assert crossing["all_ages_status"] == "unknown"
    assert "phase" in crossing["safety_reason"]
    assert result["km_aaa"] == 0


def test_fr15_5_sourced_street_observations_confirm_only_matching_values():
    graph = path_graph()
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
    graph.graph["safety_evidence"] = {
        "streets": [
            {
                "edge": [1, 2, 0],
                "source": "explicit toy traffic survey",
                "date": "2026-10-01",
                "speed_kmh": 30,
                "adt": 750,
            }
        ]
    }
    assert score_edges(graph, PROFILE)[1, 2, 0]["confirmed_aaa"]
    graph.graph["safety_evidence"]["streets"][0]["adt"] = 3000
    assert not score_edges(graph, PROFILE)[1, 2, 0]["confirmed_aaa"]


def test_fr15_5_planned_phase_is_not_existing_crossing_evidence():
    from bikeplan.safety import movement_status

    record = {
        "stage": "proposed",
        "source": "explicit toy signal design",
        "date": "2026-10-01",
        "protected_phase": True,
        "turning_conflicts": "protected",
        "bicycle_access": True,
    }
    status, reason = movement_status(record, {"signal": True, "refuge": False}, None, None)
    assert status == "unknown"
    assert "proposed" in reason


def test_fr15_5_default_junction_pick_requires_sourced_proposed_movements():
    from bikeplan.propose import Planning, confirmed_planning

    graph = crossing_graph()
    planning = Planning(
        {(1, 2, 0): {"cost": 100, "needs": ("junction:2",)}},
        {"junction:2": {"kind": "junction", "fix": "signals", "junction": 2}},
    )
    assert not confirmed_planning(graph, PROFILE, planning).edges
    graph.graph["safety_evidence"] = {
        "movements": [
            {
                "incoming": [1, 2, 0],
                "outgoing": [2, 5, 0],
                "stage": "proposed",
                "fix": "signals",
                "source": "explicit toy signal design",
                "date": "2026-10-01",
                "protected_phase": True,
                "turning_conflicts": "protected",
                "bicycle_access": True,
            }
        ]
    }
    assert (1, 2, 0) in confirmed_planning(graph, PROFILE, planning).edges
    assert not score_edges(graph, PROFILE)[1, 2, 0]["confirmed_aaa"]
