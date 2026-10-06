import gzip
import json
from pathlib import Path

import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.network import build

FIXTURE = Path("tests/fixtures/network/sides.osm")
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


@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    snapshot = tmp_path_factory.mktemp("snapshot")
    (snapshot / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (snapshot / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    region = load_region("regions/au-nsw-bayside.yaml")
    return build(snapshot, region, load_profile(region.profile))


def by_direction(graph, way):
    found = {d["reversed"]: d for _, _, d in graph.edges(data=True) if d["osm_way"] == way}
    assert set(found) == {False, True}
    return found


@pytest.mark.parametrize(
    ("way", "forward", "backward"),
    [
        (501, "off_road", "off_road"),
        (502, "off_road", "off_road"),
        (503, "off_road", "off_road"),
        (504, "protected", "protected"),
        (505, "protected", "none"),
        (506, "painted_lane", "painted_lane"),
        (507, "protected", "none"),
        (508, "shared", "shared"),
        (509, "shared", "shared"),
        (510, "none", "none"),
        (511, "painted_lane", "painted_lane"),
        (513, "protected", "protected"),
        (514, "painted_lane", "painted_lane"),
    ],
)
def test_fr3_6_bike_facility_per_side(graph, way, forward, backward):
    sides = by_direction(graph, way)
    assert sides[False]["bike_facility"] == forward
    assert sides[True]["bike_facility"] == backward


def test_fr3_6_lane_width_kept_on_its_side(graph):
    sides = by_direction(graph, 512)
    assert sides[False]["bike_lane_width_m"] == pytest.approx(1.5)
    assert sides[True]["bike_lane_width_m"] is None


@pytest.mark.parametrize(
    ("way", "forward", "backward"),
    [
        (521, "yes", "yes"),
        (522, "no", "yes"),
        (523, "yes", "yes"),
        (524, "no", "yes"),
        (525, "no", "no"),
        (526, "no", "no"),
        (527, "unknown", "unknown"),
        (528, "no", "no"),
    ],
)
def test_fr3_7_parking_per_side(graph, way, forward, backward):
    sides = by_direction(graph, way)
    assert sides[False]["parking"] == forward
    assert sides[True]["parking"] == backward


@pytest.mark.parametrize(
    ("way", "metres"),
    [(541, 7.0), (542, 7.5), (543, 7.0104), (544, 7.0104), (547, 6.0), (549, None)],
)
def test_fr3_8_width_parses_metres_and_feet(graph, way, metres):
    for data in by_direction(graph, way).values():
        assert data["width_tag_m"] == (pytest.approx(metres) if metres else None)


@pytest.mark.parametrize(
    ("way", "reason"),
    [(545, "out_of_range"), (546, "out_of_range"), (548, "unreadable"), (549, None)],
)
def test_fr3_8_bad_width_dropped_with_reason(graph, way, reason):
    for data in by_direction(graph, way).values():
        assert data["width_tag_m"] is None
        assert data["width_drop_reason"] == reason
