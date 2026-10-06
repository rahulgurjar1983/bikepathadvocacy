import gzip
import json
from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import LineString, box

from bikeplan import main
from bikeplan.stress import stress_summary

FIXTURE = Path("tests/fixtures/network/clip.osm")
REGION = "regions/au-nsw-bayside.yaml"
BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [151.10, -33.95],
                [151.121, -33.95],
                [151.121, -33.88],
                [151.10, -33.88],
                [151.10, -33.95],
            ]
        ],
    },
}
INSIDE_KM = (92.4 + 46.2) / 1000


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    folder = tmp_path_factory.mktemp("snapshot")
    (folder / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (folder / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    return folder


def test_fr3_13_network_summary_counts_each_segment_once_inside_the_boundary(snapshot, capsys):
    assert main(["network", "summary", REGION, "--snapshot", str(snapshot)]) == 0
    lines = dict(line.split() for line in capsys.readouterr().out.splitlines())
    assert float(lines["bike_km"]) == pytest.approx(INSIDE_KM, rel=0.02)


def test_fr3_13_stress_summary_counts_each_segment_once_inside_the_boundary(snapshot, tmp_path):
    assert main(["stress", REGION, "--snapshot", str(snapshot), "--out", str(tmp_path)]) == 0
    summary = json.loads((tmp_path / "stress_summary.json").read_text())
    assert sum(summary["km_by_lts"].values()) == pytest.approx(INSIDE_KM, rel=0.02)
    assert sum(c["km_aaa"] for c in summary["by_road_class"].values()) == pytest.approx(
        summary["km_aaa"], abs=1e-6
    )


def two_way_graph():
    graph = nx.MultiDiGraph(boundary=box(0, -10, 100, 10))
    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=200.0, y=0.0)
    line = LineString([(0, 0), (200, 0)])
    for u, v in ((1, 2), (2, 1)):
        graph.add_edge(
            u,
            v,
            0,
            segment_id="s",
            length_m=200.0,
            bike_ok=True,
            highway="residential",
            geometry=line,
        )
    return graph


def test_fr3_13_segment_takes_the_higher_lts_and_aaa_needs_every_direction():
    graph = two_way_graph()
    scores = {
        (1, 2, 0): {"lts": 1, "aaa": True},
        (2, 1, 0): {"lts": 3, "aaa": False},
    }
    summary = stress_summary(graph, scores)
    assert summary["km_by_lts"]["3"] == pytest.approx(0.1)
    assert summary["km_by_lts"]["1"] == 0
    assert summary["km_aaa"] == 0


def test_fr3_13_segment_is_aaa_when_every_direction_is_aaa():
    graph = two_way_graph()
    scores = {(1, 2, 0): {"lts": 1, "aaa": True}, (2, 1, 0): {"lts": 1, "aaa": True}}
    summary = stress_summary(graph, scores)
    assert summary["km_aaa"] == pytest.approx(0.1)
    assert summary["km_by_lts"]["1"] == pytest.approx(0.1)
