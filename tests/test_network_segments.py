import gzip
import hashlib
import json
from pathlib import Path

import pytest

from bikeplan import main
from bikeplan.config import load_profile, load_region
from bikeplan.network import build

FIXTURE = Path("tests/fixtures/network/segments.osm")
REGION = "regions/au-nsw-bayside.yaml"
BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [151.10, -33.95],
                [151.14, -33.95],
                [151.14, -33.88],
                [151.10, -33.88],
                [151.10, -33.95],
            ]
        ],
    },
}
SPACING_M = 92.4


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    folder = tmp_path_factory.mktemp("snapshot")
    (folder / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (folder / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    return folder


def load(snapshot):
    region = load_region(REGION)
    return build(snapshot, region, load_profile(region.profile))


@pytest.fixture(scope="module")
def graph(snapshot):
    return load(snapshot)


def expected_id(way, first, second):
    return hashlib.sha256(f"{way}:{first}:{second}".encode()).hexdigest()[:16]


def test_fr3_9_segment_id_is_the_hash_of_way_and_sorted_nodes(graph):
    ids = {d["segment_id"] for _, _, d in graph.edges(data=True) if d["osm_way"] == 701}
    assert ids == {expected_id(701, 7011, 7013)}


def test_fr3_9_both_directions_share_the_id(graph):
    for way in (701, 702, 703, 704):
        edges = [d for _, _, d in graph.edges(data=True) if d["osm_way"] == way]
        assert {d["reversed"] for d in edges} == {False, True}
        assert len({d["segment_id"] for d in edges}) == 1


def test_fr3_9_ids_repeat_on_a_second_load(snapshot, graph):
    again = load(snapshot)
    first = sorted((u, v, d["segment_id"]) for u, v, d in graph.edges(data=True))
    second = sorted((u, v, d["segment_id"]) for u, v, d in again.edges(data=True))
    assert first == second
    assert len({d["segment_id"] for _, _, d in graph.edges(data=True)}) == 4


def points_by_id(graph):
    return {p["osm_id"]: p for p in graph.graph["points"]}


def test_fr3_11_simplified_signal_node_stays_in_the_point_layer(graph):
    assert 7012 not in graph.nodes
    point = points_by_id(graph)[7012]
    assert point["signal"] is True
    assert point["refuge"] is False
    ends = [graph.nodes[7011], graph.nodes[7013]]
    assert point["x"] == pytest.approx((ends[0]["x"] + ends[1]["x"]) / 2, abs=0.5)
    assert point["y"] == pytest.approx((ends[0]["y"] + ends[1]["y"]) / 2, abs=0.5)


def test_fr3_11_crossing_signals_and_islands_are_kept(graph):
    points = points_by_id(graph)
    assert 7042 not in graph.nodes
    assert points[7042]["signal"] is True
    assert points[7032]["refuge"] is True
    assert points[7032]["signal"] is False
    assert points[7033]["refuge"] is False
    assert points[7033]["signal"] is False


def test_fr3_11_untagged_nodes_are_not_points(graph):
    assert set(points_by_id(graph)) == {7012, 7032, 7033, 7042}


def summary(snapshot, capsys):
    assert main(["network", "summary", REGION, "--snapshot", str(snapshot)]) == 0
    out = capsys.readouterr().out
    return dict(line.split() for line in out.splitlines())


def test_fr3_12_summary_counts_edges_and_bike_km(snapshot, capsys):
    lines = summary(snapshot, capsys)
    assert lines["edges"] == "8"
    assert float(lines["bike_km"]) == pytest.approx(6 * SPACING_M / 1000, rel=0.02)


def test_fr3_12_summary_gives_tag_shares_of_length(snapshot, capsys):
    lines = summary(snapshot, capsys)
    assert float(lines["speed_tag_share"]) == pytest.approx(8 / 14, abs=0.01)
    assert float(lines["lanes_tag_share"]) == pytest.approx(8 / 14, abs=0.01)
    assert float(lines["parking_tag_share"]) == pytest.approx(10 / 14, abs=0.01)


def test_fr3_12_summary_reports_a_missing_snapshot(tmp_path, capsys):
    assert main(["network", "summary", REGION, "--snapshot", str(tmp_path)]) == 1
    assert capsys.readouterr().err.strip()
