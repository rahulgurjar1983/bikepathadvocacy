import gzip
import json
from pathlib import Path

import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.network import build

FIXTURE = Path("tests/fixtures/network/tags.osm")
BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [151.10, -33.95],
                [151.14, -33.95],
                [151.14, -33.91],
                [151.10, -33.91],
                [151.10, -33.95],
            ]
        ],
    },
}


@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    snapshot = tmp_path_factory.mktemp("snapshot")
    (snapshot / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (snapshot / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    region = load_region("regions/au-nsw-bayside.yaml")
    return build(snapshot, region, load_profile(region.profile))


def edges_of(graph, way):
    found = [d for _, _, d in graph.edges(data=True) if d["osm_way"] == way]
    assert found
    return found


@pytest.mark.parametrize(
    ("way", "speed", "source"),
    [
        (401, 40, "tag"),
        (402, 48.28032, "tag"),
        (403, 50, "implicit"),
        (404, 10, "tag"),
        (405, 60, "default"),
        (406, 50, "default"),
        (407, 50, "default"),
        (408, 50, "default"),
    ],
)
def test_fr3_4_speed_and_source(graph, way, speed, source):
    for data in edges_of(graph, way):
        assert data["speed_kmh"] == pytest.approx(speed)
        assert data["speed_source"] == source


@pytest.mark.parametrize(
    ("way", "total", "forward", "backward", "source"),
    [
        (411, 4, 2, 2, "tag"),
        (412, 3, 2, 1, "tag"),
        (413, 4, 3, 1, "tag"),
        (415, 4, 2, 2, "default"),
        (416, 2, 1, 1, "default"),
    ],
)
def test_fr3_5_two_way_lane_split(graph, way, total, forward, backward, source):
    by_direction = {d["reversed"]: d for d in edges_of(graph, way)}
    assert set(by_direction) == {False, True}
    assert by_direction[False]["lanes_dir"] == forward
    assert by_direction[True]["lanes_dir"] == backward
    for data in by_direction.values():
        assert data["lanes_total"] == total
        assert data["lanes_source"] == source


def test_fr3_5_oneway_lanes_all_in_motor_direction(graph):
    (data,) = edges_of(graph, 414)
    assert data["lanes_total"] == 2
    assert data["lanes_dir"] == 2
    assert data["lanes_source"] == "tag"


def test_fr3_5_contraflow_bike_edge_has_no_motor_lanes(graph):
    by_dir = sorted(edges_of(graph, 417), key=lambda d: d["lanes_dir"])
    assert [d["lanes_dir"] for d in by_dir] == [0, 1]
    assert all(d["lanes_total"] == 1 for d in by_dir)


@pytest.mark.parametrize(("way", "adt"), [(408, 750), (405, 12000), (415, 25000)])
def test_fr3_10_default_adt_from_class_table(graph, way, adt):
    for data in edges_of(graph, way):
        assert data["adt"] == adt
        assert data["adt_source"] == "default"
