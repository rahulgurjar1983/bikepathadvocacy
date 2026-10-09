import json
from pathlib import Path

import networkx as nx
import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.propose import Planning
from bikeplan.run import build_all
from bikeplan.trips import complete_trips, snapshot_trip_inputs


def town():
    graph = nx.MultiDiGraph()
    links = {}
    for u, v in ((0, 1), (1, 2), (10, 11), (11, 12)):
        for a, b in ((u, v), (v, u)):
            graph.add_edge(a, b, 0, bike_ok=True, length_m=100.0, highway="residential")
            links[(a, b, 0)] = {"status": "confirmed", "source": "test survey"}
    movements = {
        (incoming, outgoing): {"status": "confirmed", "source": "test movement survey"}
        for incoming in links
        for outgoing in links
        if incoming[1] == outgoing[0]
    }
    destinations = [
        {
            "id": f"site-{node}",
            "model_node": node,
            "entrances": [
                {
                    "id": f"gate-{node}",
                    "node": node,
                    "bike_accessible": True,
                    "status": "confirmed",
                    "source": "test gate survey",
                }
            ],
        }
        for node in (2, 12)
    ]
    return graph, links, movements, destinations


def trips(data, selected=(), reach_m=2680.0, detour_max=1.25, first_leg_m=0.0):
    graph, links, movements, destinations = data
    return complete_trips(
        graph,
        {0: 100.0, 10: 50.0},
        destinations,
        links,
        movements,
        set(selected),
        reach_m,
        detour_max,
        first_leg_m,
    )


def test_fr16_3_separate_islands_have_directed_witnesses_and_no_network_claim():
    result = trips(town())
    assert len(result["strict"]) == 2
    assert len(result["groups"]) == 2
    assert result["continuous_network"] is False
    witness = result["strict"][0]
    assert witness["origin"] == 0
    assert witness["destination"] == "site-2"
    assert witness["entrance"] == "gate-2"
    assert witness["outbound"]["edges"] == [[0, 1, 0], [1, 2, 0]]
    assert witness["return"]["edges"] == [[2, 1, 0], [1, 0, 0]]
    assert witness["outbound"]["distance_m"] == 200.0
    assert witness["outbound"]["movements"][0]["status"] == "confirmed"
    assert witness["evidence_status"] == "confirmed"
    assert "field safety" in result["limit"]


def test_fr16_3_a_one_way_route_cannot_claim_a_return_trip():
    data = town()
    data[0].remove_edge(2, 1, 0)
    result = trips(data)
    assert [item["destination"] for item in result["strict"]] == ["site-12"]
    assert any(item["reason"] == "no_return_route" for item in result["gaps"])


@pytest.mark.parametrize("change", ["missing", "centroid", "no_bike_access", "no_source"])
def test_fr16_3_a_snap_cannot_replace_a_known_bike_entrance(change):
    data = town()
    entrance = data[3][0]["entrances"][0]
    if change == "missing":
        data[3][0]["entrances"] = []
    elif change == "centroid":
        entrance["status"] = "unknown"
    elif change == "no_source":
        entrance.pop("source")
    else:
        entrance["bike_accessible"] = False
    result = trips(data)
    assert [item["destination"] for item in result["strict"]] == ["site-12"]
    assert any(item["destination"] == "site-2" for item in result["gaps"])


@pytest.mark.parametrize("status", ["unsafe", "unknown", "assumed"])
def test_fr16_3_crossing_movements_must_be_confirmed_in_each_direction(status):
    data = town()
    data[2][((2, 1, 0), (1, 0, 0))]["status"] = status
    result = trips(data)
    assert [item["destination"] for item in result["strict"]] == ["site-12"]
    gap = next(item for item in result["gaps"] if item.get("direction") == "return")
    assert gap["movements"][0]["status"] == status


def test_fr16_3_dependent_link_and_crossing_fixes_only_help_together():
    data = town()
    for key in ((0, 1, 0), (1, 0, 0)):
        data[1][key].update(status="unsafe", after_status="confirmed", needs=["link"])
    for key in (((0, 1, 0), (1, 2, 0)), ((2, 1, 0), (1, 0, 0))):
        data[2][key].update(status="unsafe", after_status="confirmed", needs=["crossing"])
    for selected in ((), ("link",), ("crossing",)):
        result = trips(data, selected)
        assert [item["destination"] for item in result["strict"]] == ["site-12"]
        assert result["later_work"]
    result = trips(data, ("link", "crossing"))
    assert len(result["strict"]) == 2
    assert result["strict"][0]["required_elements"] == ["crossing", "link"]


@pytest.mark.parametrize("direction", ["outbound", "return"])
def test_fr16_3_reach_and_detour_apply_to_both_directions(direction):
    data = town()
    u, v = (0, 2) if direction == "outbound" else (2, 0)
    data[0].add_edge(u, v, 1, bike_ok=True, length_m=100.0)
    data[1][(u, v, 1)] = {"status": "unsafe", "source": "test survey"}
    result = trips(data)
    assert [item["destination"] for item in result["strict"]] == ["site-12"]
    assert any(item["reason"] == "detour_limit" for item in result["gaps"])
    data[0].edges[(u, v, 1)]["length_m"] = 5000.0
    data[0].edges[(1, 2, 0) if direction == "outbound" else (2, 1, 0)]["length_m"] = 2700.0
    result = trips(data)
    assert any(item["reason"] == "reach_limit" for item in result["gaps"])


def test_fr16_3_calm_first_leg_is_only_a_model_score_assumption():
    data = town()
    for key in ((0, 1, 0), (1, 0, 0)):
        data[1][key].update(status="assumed", lts=2, aaa=False)
    result = trips(data, first_leg_m=200.0)
    assert [item["destination"] for item in result["strict"]] == ["site-12"]
    assert {"origin": 0, "destination": "site-2"} in result["first_leg_model"]
    assert "assumption" in result["first_leg_limit"]


def test_fr16_3_joined_routes_record_confirmed_directed_joins():
    data = town()
    data[3].append({**data[3][0], "id": "library", "entrances": [data[3][0]["entrances"][0]]})
    result = trips(data)
    assert len(result["strict"]) == 3
    assert len(result["groups"]) == 2
    assert result["joins"]
    assert result["joins"][0]["status"] == "confirmed"
    assert result["continuous_network"] is False


def test_fr16_3_unsourced_links_do_not_enter_strict_claims():
    data = town()
    data[1][(1, 2, 0)].pop("source")
    assert [item["destination"] for item in trips(data)["strict"]] == ["site-12"]


def test_fr16_3_every_saved_package_has_trip_proof_and_visible_limits():
    _, outputs, files, _ = build_all(
        load_region("tests/fixtures/test-grid/region.yaml"),
        load_profile("au-nsw"),
        Path("tests/fixtures/test-grid/snapshot"),
    )
    frontier = json.loads(files["frontier.json"])
    for curve in frontier["scenarios"]:
        assert len(curve["trip_packages"]) == len(curve["picks"])
        for rank, package in enumerate(curve["trip_packages"]):
            assert package["package"] == {"scenario": curve["id"], "rank": rank}
            assert package["strict"] == []
            assert package["gaps"]
            assert package["continuous_network"] is False
    assert "Complete trips and route groups" in outputs["report.html"].decode()
    assert "known bike entrance" in outputs["report.html"].decode()


def test_fr16_3_a_missing_movement_is_a_gap_even_between_confirmed_links():
    data = town()
    data[2].pop(((0, 1, 0), (1, 2, 0)))
    result = trips(data)
    assert [item["destination"] for item in result["strict"]] == ["site-12"]
    assert any(
        movement["status"] == "unknown"
        for gap in result["gaps"]
        for movement in gap.get("movements", [])
    )


def test_fr16_3_joins_need_valid_movements_in_both_directions():
    data = town()
    graph, links, movements, destinations = data
    for u, v in ((1, 20), (20, 21)):
        for a, b in ((u, v), (v, u)):
            graph.add_edge(a, b, 0, bike_ok=True, length_m=100.0, highway="residential")
            links[(a, b, 0)] = {"status": "confirmed", "source": "test survey"}
    for incoming, outgoing in (((1, 20, 0), (20, 21, 0)), ((21, 20, 0), (20, 1, 0))):
        movements[incoming, outgoing] = {"status": "confirmed", "source": "test survey"}
    destinations.append(
        {
            "id": "branch",
            "entrances": [
                {
                    "id": "branch-gate",
                    "node": 21,
                    "status": "confirmed",
                    "source": "test survey",
                    "bike_accessible": True,
                }
            ],
        }
    )
    people = {0: 10.0, 1: 10.0, 10: 10.0}
    before = complete_trips(graph, people, destinations, links, movements, set(), 2680, 1.25)
    assert len(before["groups"]) == 3
    assert not any(join.get("movements") for join in before["joins"])
    for incoming, outgoing in (((2, 1, 0), (1, 20, 0)), ((20, 1, 0), (1, 2, 0))):
        movements[incoming, outgoing] = {"status": "confirmed", "source": "test survey"}
    after = complete_trips(graph, people, destinations, links, movements, set(), 2680, 1.25)
    assert len(after["groups"]) == 2
    assert any(join.get("movements") for join in after["joins"])


def test_fr16_3_prohibited_bike_turns_are_not_shortest_route_shortcuts():
    data = town()
    data[0].add_edge(0, 2, 1, bike_ok=True, length_m=10.0)
    data[1][(0, 2, 1)] = {"status": "unsafe", "legal": False}
    result = trips(data)
    assert len(result["strict"]) == 2
    assert result["strict"][0]["outbound"]["shortest_m"] == 200.0


def test_fr16_3_zero_population_and_unknown_entrances_do_not_create_claims():
    data = town()
    result = complete_trips(data[0], {0: 0.0}, data[3], data[1], data[2], set(), 2680, 1.25)
    assert result["strict"] == []
    assert result["continuous_network"] is False
    for place in data[3]:
        place["entrances"] = []
    result = trips(data, first_leg_m=200)
    assert result["strict"] == []
    assert result["first_leg_model"] is None
    assert result["first_leg_status"] == "unknown_entrance_links"


def test_fr16_3_witnesses_are_stable_with_reversed_input_order():
    data = town()
    expected = trips(data)
    graph = nx.MultiDiGraph()
    for u, v, key, attrs in reversed(list(data[0].edges(keys=True, data=True))):
        graph.add_edge(u, v, key, **attrs)
    actual = trips((graph, dict(reversed(list(data[1].items()))), data[2], data[3][::-1]))
    assert actual == expected


def test_fr16_3_snapshot_evidence_cannot_confirm_a_failed_changed_graph(tmp_path):
    data = town()
    raw = {
        "trip_evidence": {
            "entrances": [{**data[3][0]["entrances"][0], "destination": "site-2"}],
            "links": [{"edge": list(key), **value} for key, value in data[1].items()],
            "movements": [
                {"incoming": list(i), "outgoing": list(o), **value}
                for (i, o), value in data[2].items()
            ],
        }
    }
    (tmp_path / "places.json").write_text(json.dumps(raw))
    planning = Planning({key: {"needs": ()} for key in data[1]}, {})
    scores = {key: {"aaa": True, "lts": 1} for key in data[1]}
    kept = [{"osm_id": "site-2", "name": "Test school"}]
    destinations, links, movements = snapshot_trip_inputs(
        tmp_path, kept, [2], data[0], scores, planning
    )
    result = complete_trips(data[0], {0: 100}, destinations, links, movements, set(), 2680, 1.25)
    assert len(result["strict"]) == 1
    planning = Planning({key: {"needs": ("later-link",)} for key in data[1]}, {})
    destinations, links, movements = snapshot_trip_inputs(
        tmp_path, kept, [2], data[0], scores, planning
    )
    result = complete_trips(data[0], {0: 100}, destinations, links, movements, set(), 2680, 1.25)
    assert result["strict"] == []
    assert "later-link" in result["later_work"]


def test_fr16_3_a_prohibited_movement_cannot_join_route_groups():
    from bikeplan.trips import route_groups

    witnesses = [
        {"outbound": {"edges": [[0, 1, 0]]}, "return": {"edges": [[1, 0, 0]]}},
        {"outbound": {"edges": [[1, 2, 0]]}, "return": {"edges": [[2, 1, 0]]}},
    ]
    movements = {
        ((0, 1, 0), (1, 2, 0)): {"status": "confirmed", "legal": False},
        ((2, 1, 0), (1, 0, 0)): {"status": "confirmed", "legal": True},
    }
    groups, joins = route_groups(witnesses, movements)
    assert len(groups) == 2
    assert joins == []


def test_fr16_3_witnesses_name_the_selected_changed_graph_dependencies():
    data = town()
    for key in ((0, 1, 0), (1, 0, 0)):
        data[1][key]["model_needs"] = ["link-work"]
    before = trips(data)
    assert [item["destination"] for item in before["strict"]] == ["site-12"]
    after = trips(data, selected=("link-work",))
    assert len(after["strict"]) == 2
    assert after["strict"][0]["required_elements"] == ["link-work"]
