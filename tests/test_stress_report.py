import gzip
import json
from pathlib import Path

import pytest

from bikeplan import main
from bikeplan.config import load_profile, load_region
from bikeplan.stress import edge_reason

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
STREET = {
    "oneway": False,
    "lanes_total": 2,
    "lanes_dir": 1,
    "lanes": None,
    "highway": "residential",
    "speed_kmh": 50.0,
    "speed_source": "default",
    "adt": 750,
    "adt_source": "default",
    "bike_facility": "none",
    "bike_lane_width_m": None,
    "parking": "no",
    "bike_ok": True,
}


@pytest.fixture(scope="module")
def profile():
    return load_profile(load_region(REGION).profile)


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    folder = tmp_path_factory.mktemp("snapshot")
    (folder / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (folder / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    out = tmp_path_factory.mktemp("out")
    assert main(["stress", REGION, "--snapshot", str(folder), "--out", str(out)]) == 0
    return out


def test_fr4_7_reason_names_table_row_speed_adt_and_aaa_verdict(profile):
    assert edge_reason(STREET, profile, 2, 2, None) == (
        "mixed traffic, type A, 50 km/h (default), ADT 750 (default) -> LTS 2;"
        " not AAA: 50 km/h is above 30"
    )


def test_fr4_7_reason_says_why_an_edge_is_aaa(profile):
    data = {**STREET, "speed_kmh": 30.0, "speed_source": "tag"}
    assert edge_reason(data, profile, 1, 1, None) == (
        "mixed traffic, type A, 30 km/h (tag), ADT 750 (default) -> LTS 1;"
        " AAA: 30 km/h is within 30 and ADT 750 is within 2000"
    )


def test_fr4_7_reason_names_the_crossing_that_raised_the_lts(profile):
    data = {**STREET, "speed_kmh": 30.0, "speed_source": "tag"}
    crossing = {"junction": 8100, "lts": 3, "speed_kmh": 60.0, "lanes": 4, "refuge": False}
    reason = edge_reason(data, profile, 1, 3, crossing)
    assert "-> LTS 1; raised to LTS 3 by crossing at junction 8100" in reason
    assert "main street 60 km/h, 4 lanes, no refuge" in reason
    assert reason.endswith("not AAA: LTS is 3")


def test_fr4_7_painted_lane_reason_names_table_and_lane_width(profile):
    data = {**STREET, "bike_facility": "painted_lane", "bike_lane_width_m": 1.5}
    reason = edge_reason(data, profile, 2, 2, None)
    assert reason.startswith(
        "painted lane, table 2, 1 lane each way, lane 1.5 m, 50 km/h (default)"
    )
    assert reason.endswith("not AAA: painted lanes do not count as AAA")


def test_fr4_7_off_road_reason_says_why_it_is_lts_1(profile):
    data = {**STREET, "bike_facility": "off_road"}
    assert edge_reason(data, profile, 1, 1, None) == (
        "off-road path -> LTS 1; AAA: off-road paths and protected lanes are AAA"
    )


def test_fr4_7_every_edge_of_a_real_run_keeps_a_reason(output):
    features = json.loads((output / "stress.geojson").read_text())["features"]
    assert features
    for feature in features:
        assert (
            "-> LTS" in feature["properties"]["reason"]
            or "LTS 1" in feature["properties"]["reason"]
        )


def test_fr4_8_geojson_has_one_feature_per_edge_with_lts_aaa_and_reason(output):
    collection = json.loads((output / "stress.geojson").read_text())
    assert collection["type"] == "FeatureCollection"
    for feature in collection["features"]:
        assert feature["geometry"]["type"] == "LineString"
        longitude, latitude = feature["geometry"]["coordinates"][0]
        assert 151.0 < longitude < 151.2 and -34.0 < latitude < -33.8
        assert set(feature["properties"]) >= {"lts", "aaa", "reason"}
        assert feature["properties"]["lts"] in {1, 2, 3, 4}
        assert isinstance(feature["properties"]["aaa"], bool)


def test_fr4_8_summary_km_match_the_features(output):
    features = json.loads((output / "stress.geojson").read_text())["features"]
    summary = json.loads((output / "stress_summary.json").read_text())
    bike = [f["properties"] for f in features if f["properties"]["bike_ok"]]
    for lts in (1, 2, 3, 4):
        expected = sum(p["length_m"] for p in bike if p["lts"] == lts) / 1000
        assert summary["km_by_lts"][str(lts)] == pytest.approx(expected, abs=1e-3)
    assert summary["km_aaa"] == pytest.approx(
        sum(p["length_m"] for p in bike if p["aaa"]) / 1000, abs=1e-3
    )
    assert sum(summary["km_by_lts"].values()) > 0


def test_fr4_8_summary_splits_km_by_road_class(output):
    summary = json.loads((output / "stress_summary.json").read_text())
    by_class = summary["by_road_class"]
    assert by_class
    for lts in ("1", "2", "3", "4"):
        assert sum(c["km_by_lts"][lts] for c in by_class.values()) == pytest.approx(
            summary["km_by_lts"][lts], abs=1e-3
        )
    assert sum(c["km_aaa"] for c in by_class.values()) == pytest.approx(summary["km_aaa"], abs=1e-3)


def test_fr4_8_a_crossing_edge_is_raised_in_the_files(output):
    features = json.loads((output / "stress.geojson").read_text())["features"]
    raised = [f for f in features if f["properties"]["osm_way"] == 8120]
    assert raised
    assert {f["properties"]["lts"] for f in raised} == {3}
    assert all("raised to LTS 3 by crossing" in f["properties"]["reason"] for f in raised)
