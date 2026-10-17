from pathlib import Path

import pytest
from shapely.geometry import box

from bikeplan.config import ConfigError, Network, load_profile
from bikeplan.corridors import indicative_routes
from bikeplan.options import join_places
from tests.option_helpers import place, street_graph
from tests.route_helpers import ORIGIN
from tests.test_corridors import LINE_NODES, LINE_ROADS, absolute, corridor_file

MAIN_NODES = {n: (n * 100, 200) for n in range(7)}
MAIN_ROADS = [(n, n + 1, 100.0, 1, False, False) for n in range(6)]
ISLAND_NODES = {10: (300, 120), 11: (320, 120), 12: (340, 120)}
ISLAND_ROADS = [(10, 11, 20.0, 1, False, False), (11, 12, 20.0, 1, False, False)]
BOXES = [None, box(-50, 100, 700, 250)]


def network(**changes):
    found = load_profile("au-nsw").network
    return Network(**{**found.__dict__, "boundary_buffer_m": 0.0, **changes})


def island_graph(area):
    graph, _ = street_graph(MAIN_NODES | ISLAND_NODES, [*MAIN_ROADS, *ISLAND_ROADS])
    if area is not None:
        graph.graph["boundary"] = area
    return graph


def test_fr17_1_snap_max_m_defaults_to_300_and_reads_from_the_profile(tmp_path):
    assert load_profile("au-nsw").network.snap_max_m == 300.0
    text = Path("profiles/au-nsw.yaml").read_text()
    (tmp_path / "au-nsw.yaml").write_text(
        text.replace("network:\n", "network:\n  snap_max_m: 120\n", 1)
    )
    assert load_profile("au-nsw", tmp_path).network.snap_max_m == 120.0
    (tmp_path / "au-nsw.yaml").write_text(
        text.replace("network:\n", "network:\n  snap_max_m: 0\n", 1)
    )
    with pytest.raises(ConfigError, match=r"network\.snap_max_m"):
        load_profile("au-nsw", tmp_path)


@pytest.mark.parametrize("area", BOXES)
def test_fr17_1_a_place_next_to_an_island_joins_the_main_part_through_the_next_node(area):
    result = join_places(island_graph(area), [place("node/1", "school", 300, 140)], [], network())
    assert [(item["id"], item["node"]) for item in result.joined] == [("node/1", 3)]
    assert result.unjoined == []


@pytest.mark.parametrize("area", BOXES)
def test_fr17_1_a_place_400_m_from_the_main_part_is_unjoined_with_the_limit_in_the_reason(area):
    found = [place("node/1", "school", 300, 600)]
    result = join_places(island_graph(area), found, [], network(snap_max_m=300.0))
    assert result.joined == []
    assert [(item["id"], item["reason"]) for item in result.unjoined] == [
        ("node/1", "no bike-legal node within 300 m")
    ]


def test_fr17_1_snap_max_m_limits_the_snap():
    found = [place("node/1", "school", 300, 140)]
    tight = join_places(island_graph(None), found, [], network(snap_max_m=50.0))
    assert [item["reason"] for item in tight.unjoined] == ["no bike-legal node within 50 m"]
    wide = join_places(island_graph(None), found, [], network(snap_max_m=60.0))
    assert [item["node"] for item in wide.joined] == [3]


def end_graph():
    graph, _ = street_graph(
        absolute(LINE_NODES | {90: (0, 30), 91: (20, 30), 92: (40, 30)}),
        [*LINE_ROADS, (90, 91, 20.0, 2, False, False), (91, 92, 20.0, 2, False, False)],
    )
    graph.graph["crs"] = 32756
    graph.graph["boundary"] = box(ORIGIN[0] - 50, ORIGIN[1] - 50, ORIGIN[0] + 250, ORIGIN[1] + 50)
    for u, v, data in graph.edges(data=True):
        data["bike_ok"] = {u, v} != {0, 5}
    return graph


def test_fr19_2_a_corridor_end_beside_an_island_routes_from_the_main_part(tmp_path):
    corridors = corridor_file(tmp_path, {"S1": (("West", (0, 20)), ("East", (480, -10)))})
    (route,) = indicative_routes(end_graph(), corridors)
    assert route.nodes == [0, 1, 2, 3, 4, 5]


def test_fr19_2_a_corridor_end_beyond_snap_max_m_has_no_route(tmp_path):
    corridors = corridor_file(tmp_path, {"S1": (("West", (0, 400)), ("East", (480, -10)))})
    (route,) = indicative_routes(end_graph(), corridors, 300.0)
    assert route.nodes == []
    (route,) = indicative_routes(end_graph(), corridors, 500.0)
    assert route.nodes == [0, 1, 2, 3, 4, 5]
