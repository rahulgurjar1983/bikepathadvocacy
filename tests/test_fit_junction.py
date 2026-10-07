import networkx as nx

from bikeplan.config import load_profile
from bikeplan.fit import junction_fixes

PROFILE = load_profile("au-nsw", "profiles")
ARM_M = 100.0


def road(segment_id, lanes, speed, adt=750, highway="residential"):
    return {
        "segment_id": segment_id,
        "highway": highway,
        "lanes_total": lanes,
        "lanes_dir": lanes // 2,
        "oneway": False,
        "parking:both": "no",
        "bike_ok": True,
        "bike_facility": "none",
        "bike_lane_width_m": None,
        "speed_kmh": speed,
        "adt": adt,
    }


def junction(main_lanes, main_speed, side_speed=30, side_adt=750, signal=False, refuge=False):
    graph = nx.MultiDiGraph(crs="EPSG:32756", points=[])
    for node, (x, y) in enumerate([(0, 0), (-ARM_M, 0), (ARM_M, 0), (0, ARM_M)]):
        graph.add_node(node, x=x, y=y)
    main = {"highway": "primary", "adt": 15000}
    graph.add_edge(1, 0, 0, **{**road("west", main_lanes, main_speed), **main})
    graph.add_edge(0, 2, 0, **{**road("east", main_lanes, main_speed), **main})
    graph.add_edge(3, 0, 0, **road("north", 2, side_speed, side_adt))
    if signal or refuge:
        graph.graph["points"].append({"x": 5.0, "y": 5.0, "signal": signal, "refuge": refuge})
    return graph


def test_fr6_8_four_lane_40_gets_a_refuge():
    found = junction_fixes(junction(4, 40), PROFILE)
    assert [(item["junction"], item["fix"]) for item in found] == [(0, "refuge")]
    assert found[0]["legs"] == ["north"]


def test_fr6_8_four_lane_60_gets_signals():
    found = junction_fixes(junction(4, 60), PROFILE)
    assert [item["fix"] for item in found] == ["signals"]


def test_fr6_8_two_lane_50_needs_no_fix():
    assert junction_fixes(junction(2, 50), PROFILE) == []


def test_fr6_8_junction_with_a_refuge_already_goes_to_signals():
    found = junction_fixes(junction(4, 40, refuge=True), PROFILE)
    assert [item["fix"] for item in found] == ["signals"]


def test_fr6_8_signalised_junction_needs_no_fix():
    assert junction_fixes(junction(4, 60, signal=True), PROFILE) == []


def test_fr6_8_side_street_not_aaa_on_its_own_gets_no_junction_fix():
    assert junction_fixes(junction(4, 40, side_speed=60), PROFILE) == []
    assert junction_fixes(junction(4, 40, side_adt=9000), PROFILE) == []


def test_fr6_8_disruption_is_one_refuge_or_one_signal():
    refuge = junction_fixes(junction(4, 40), PROFILE)[0]["disruption"]
    signals = junction_fixes(junction(4, 60), PROFILE)[0]["disruption"]
    assert refuge == {"refuges": 1, "signals": 0}
    assert signals == {"refuges": 0, "signals": 1}


def test_fr6_8_one_fix_covers_every_leg_held_back_at_the_junction():
    graph = junction(4, 40)
    graph.add_node(4, x=0.0, y=-ARM_M)
    graph.add_edge(4, 0, 0, **road("south", 2, 30))
    found = junction_fixes(graph, PROFILE)
    assert len(found) == 1
    assert sorted(found[0]["legs"]) == ["north", "south"]
