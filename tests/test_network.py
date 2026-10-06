import gzip
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import pytest
from bikeplan.network import build
from pyproj import CRS

from bikeplan.config import load_profile, load_region

FIXTURE = Path("tests/fixtures/network/cases.osm")
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
NO_BIKE = [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111]
BIKE_OK = [201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211]


@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    snapshot = tmp_path_factory.mktemp("snapshot")
    (snapshot / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (snapshot / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    region = load_region("regions/au-nsw-bayside.yaml")
    return build(snapshot, region, load_profile(region.profile))


def way_edges(graph, way):
    return [(u, v, d) for u, v, d in graph.edges(data=True) if d["osm_way"] == way]


def bike_directions(graph, way):
    start, end = way * 10 + 1, way * 10 + 2
    names = {(start, end): "fwd", (end, start): "rev"}
    return {names[(u, v)] for u, v, d in way_edges(graph, way) if d["bike_ok"]}


def test_fr3_1_crs_is_utm_zone_of_boundary_centre(graph):
    assert CRS(graph.graph["crs"]).to_epsg() == 32756


def test_fr3_1_lengths_match_known_distances(graph):
    lat = -33.9100 - 0.0006 * 8
    dlon = radians(151.1211 - 151.1200)
    a = cos(radians(lat)) ** 2 * sin(dlon / 2) ** 2
    known = 2 * 6371008.8 * asin(sqrt(a))
    edges = way_edges(graph, 104)
    assert edges
    for _, _, data in edges:
        assert data["length_m"] == pytest.approx(known, rel=0.01)


def test_fr3_1_nodes_are_in_metres(graph):
    x = [d["x"] for _, d in graph.nodes(data=True)]
    assert min(x) > 100000
    assert max(x) - min(x) < 1000


def test_fr3_1_all_parts_kept(graph):
    ways = {d["osm_way"] for _, _, d in graph.edges(data=True)}
    assert ways == set(NO_BIKE + BIKE_OK + list(range(301, 311)))


@pytest.mark.parametrize("way", NO_BIKE)
def test_fr3_2_excluded_ways_are_not_bike_ok(graph, way):
    edges = way_edges(graph, way)
    assert edges
    assert not any(d["bike_ok"] for _, _, d in edges)


@pytest.mark.parametrize("way", BIKE_OK)
def test_fr3_2_allowed_ways_are_bike_ok(graph, way):
    assert bike_directions(graph, way) == {"fwd", "rev"}


def test_fr3_3_oneway_street_carries_bikes_one_way(graph):
    assert bike_directions(graph, 301) == {"fwd"}
    assert bike_directions(graph, 310) == {"fwd"}


def test_fr3_3_reversed_oneway_follows_the_tag(graph):
    assert bike_directions(graph, 302) == {"rev"}


@pytest.mark.parametrize("way", [303, 304, 305, 306, 307])
def test_fr3_3_contraflow_tags_open_the_other_way(graph, way):
    assert bike_directions(graph, way) == {"fwd", "rev"}


@pytest.mark.parametrize("way", [308, 309])
def test_fr3_3_two_way_ways_run_both_ways(graph, way):
    assert bike_directions(graph, way) == {"fwd", "rev"}


def test_fr3_3_contraflow_keeps_motor_oneway(graph):
    assert all(d["oneway"] for _, _, d in way_edges(graph, 304))
    assert not any(d["oneway"] for _, _, d in way_edges(graph, 309))
