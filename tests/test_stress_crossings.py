import gzip
import json
from pathlib import Path

import networkx as nx
import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.stress import crossing_lts, edge_lts, junction_points, raise_for_crossings

FIXTURE = Path("tests/fixtures/network/junctions.osm")
REGION = "regions/au-nsw-bayside.yaml"
BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [151.10, -33.97],
                [151.14, -33.97],
                [151.14, -33.88],
                [151.10, -33.88],
                [151.10, -33.97],
            ]
        ],
    },
}
CELLS = {
    30.0: [1, 2, 4, 1, 1, 2],
    50.0: [1, 2, 4, 1, 2, 3],
    60.0: [2, 3, 4, 2, 3, 4],
    80.0: [3, 4, 4, 3, 4, 4],
}
LANES = [3, 5, 8]


@pytest.fixture(scope="module")
def profile():
    return load_profile(load_region(REGION).profile)


@pytest.fixture(scope="module")
def graph(tmp_path_factory, profile):
    folder = tmp_path_factory.mktemp("snapshot")
    (folder / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (folder / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    return build(folder, load_region(REGION), profile)


@pytest.fixture(scope="module")
def raised(graph, profile):
    own = {(u, v, k): edge_lts(d, profile) for u, v, k, d in graph.edges(keys=True, data=True)}
    return own, raise_for_crossings(graph, own, profile)[0]


def way_edges(graph, way):
    return [(u, v, k) for u, v, k, d in graph.edges(keys=True, data=True) if d["osm_way"] == way]


def test_fr4_4_signal_within_25_m_makes_a_signalised_junction(graph):
    flags = junction_points(graph)
    assert flags[8200]["signal"] is True
    assert flags[8200]["refuge"] is False


def test_fr4_4_signal_at_30_m_is_not_found(graph):
    flags = junction_points(graph)
    assert flags[8300]["signal"] is False
    assert flags[8100]["signal"] is False


def test_fr4_4_refuge_within_25_m_is_found_and_at_30_m_is_not(graph):
    flags = junction_points(graph)
    assert flags[8400]["refuge"] is True
    assert flags[8400]["signal"] is False
    assert flags[8500]["refuge"] is False


@pytest.mark.parametrize("speed", sorted(CELLS))
def test_fr4_5_every_cell_of_the_crossing_tables(speed):
    cells = CELLS[speed]
    for refuge in (False, True):
        for index, lanes in enumerate(LANES):
            assert crossing_lts(speed, lanes, refuge) == cells[index + 3 * refuge]


def test_fr4_5_speed_row_edges():
    assert crossing_lts(40.0, 4, False) == 2
    assert crossing_lts(40.1, 4, False) == 2
    assert crossing_lts(40.0, 8, False) == 4
    assert crossing_lts(50.0, 4, True) == 2
    assert crossing_lts(50.1, 4, True) == 3
    assert crossing_lts(60.0, 3, False) == 2
    assert crossing_lts(60.1, 3, False) == 3
    assert crossing_lts(60.1, 4, False) == 4


def test_fr4_5_side_street_meeting_4_lane_60_road_gets_lts_3(graph, raised):
    own, final = raised
    for key in way_edges(graph, 8120):
        assert final[key] == 3
        assert own[key] < 3


def test_fr4_5_signalised_junction_keeps_the_side_street_lts(graph, raised):
    own, final = raised
    for key in way_edges(graph, 8220):
        assert final[key] == own[key]


def test_fr4_5_signal_at_30_m_does_not_stop_the_crossing_stress(graph, raised):
    _, final = raised
    for key in way_edges(graph, 8320):
        assert final[key] == 3


def test_fr4_5_refuge_lowers_the_crossing_of_a_6_lane_road(graph, raised):
    _, final = raised
    assert {final[key] for key in way_edges(graph, 8420)} == {3}
    assert {final[key] for key in way_edges(graph, 8520)} == {4}


def test_fr4_5_the_main_street_is_not_raised(graph, raised):
    own, final = raised
    for way in (8110, 8210, 8310, 8410, 8510):
        for key in way_edges(graph, way):
            assert final[key] == own[key]


def test_fr4_5_reports_which_edges_a_crossing_raised(graph, profile):
    own = {(u, v, k): edge_lts(d, profile) for u, v, k, d in graph.edges(keys=True, data=True)}
    final, crossings = raise_for_crossings(graph, own, profile)
    keys = set(way_edges(graph, 8120))
    assert {key for key in crossings if crossings[key]["lts"] == 3} >= keys
    assert all(final[key] > own[key] for key in crossings)
    assert set(crossings) == {key for key in final if final[key] != own[key]}


def leg_graph(legs, centre=(0.0, 0.0)):
    graph = nx.MultiDiGraph()
    graph.graph["points"] = []
    graph.add_node(0, x=centre[0], y=centre[1])
    for index, (dx, dy, highway, lanes, speed) in enumerate(legs, 1):
        graph.add_node(index, x=dx, y=dy)
        data = {
            "highway": highway,
            "lanes_total": lanes,
            "speed_kmh": speed,
            "segment_id": f"s{index}",
        }
        graph.add_edge(index, 0, 0, **data)
        graph.add_edge(0, index, 0, **data)
    return graph


def lts_of(graph, value):
    return {(u, v, k): value for u, v, k in graph.edges(keys=True)}


def test_fr4_5_no_straight_pair_adds_no_crossing_stress(profile):
    graph = leg_graph(
        [
            (0, 100, "primary", 4, 80.0),
            (87, -50, "residential", 2, 50.0),
            (-87, -50, "residential", 2, 50.0),
        ]
    )
    own = lts_of(graph, 1)
    assert raise_for_crossings(graph, own, profile)[0] == own


def test_fr4_5_pair_beyond_30_degrees_of_straight_is_not_the_main_street(profile):
    graph = leg_graph(
        [
            (0, 100, "primary", 4, 80.0),
            (80, -60, "primary", 4, 80.0),
            (-80, -60, "residential", 2, 50.0),
        ]
    )
    own = lts_of(graph, 1)
    assert raise_for_crossings(graph, own, profile)[0] == own


def test_fr4_5_equal_lanes_pick_the_higher_road_class(profile):
    graph = leg_graph(
        [
            (0, 100, "secondary", 2, 80.0),
            (0, -100, "secondary", 2, 80.0),
            (100, 0, "primary", 2, 80.0),
            (-100, 0, "primary", 2, 80.0),
        ]
    )
    final = raise_for_crossings(graph, lts_of(graph, 1), profile)[0]
    for u, v, k in graph.edges(keys=True):
        assert final[(u, v, k)] == (3 if max(u, v) <= 2 else 1)


def test_fr4_5_more_lanes_beat_a_higher_class(profile):
    graph = leg_graph(
        [
            (0, 100, "residential", 4, 50.0),
            (0, -100, "residential", 4, 50.0),
            (100, 0, "primary", 2, 80.0),
            (-100, 0, "primary", 2, 80.0),
        ]
    )
    final = raise_for_crossings(graph, lts_of(graph, 1), profile)[0]
    for u, v, k in graph.edges(keys=True):
        assert final[(u, v, k)] == (1 if max(u, v) <= 2 else 2)


def test_fr4_5_a_leg_keeps_its_own_lts_when_higher(profile):
    graph = leg_graph(
        [
            (100, 0, "residential", 2, 30.0),
            (-100, 0, "residential", 2, 30.0),
            (0, -100, "residential", 2, 30.0),
        ]
    )
    own = lts_of(graph, 4)
    assert raise_for_crossings(graph, own, profile)[0] == own


def test_fr4_5_a_leg_with_lanes_but_no_speed_is_not_a_main_street(profile):
    graph = leg_graph(
        [
            (100, 0, "motorway", 4, None),
            (-100, 0, "motorway", 4, None),
            (0, -100, "residential", 2, 50.0),
        ]
    )
    for _, _, data in graph.edges(data=True):
        if data["speed_kmh"] is None:
            del data["speed_kmh"]
    own = lts_of(graph, 1)
    assert raise_for_crossings(graph, own, profile)[0] == own
