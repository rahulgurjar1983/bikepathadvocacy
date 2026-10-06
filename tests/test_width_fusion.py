import gzip
import json
from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import LineString, box

from bikeplan import main
from bikeplan.config import load_profile
from bikeplan.width import check_links, fuse, width_summary

PROFILE = load_profile("au-nsw", "profiles")
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
STREET = {"highway": "residential", "lanes_total": 2, "lanes_dir": 1, "parking:both": "no"}


def test_fr5_5_adapter_beats_every_other_source():
    data = {**STREET, "width_measured_m": 9.2, "width_tag_m": 8.0}
    found = fuse(data, PROFILE, reserve_m=20.0, spread_m=0.0)
    assert found["width_source"] == "adapter"
    assert found["width_confidence"] == "high"
    assert found["width_m"] == pytest.approx(9.2)
    assert found["width_low_m"] < 9.2 < found["width_high_m"]
    assert [item.source for item in found["estimates"]] == [
        "adapter",
        "osm_tag",
        "reserve",
        "lanes",
    ]


def test_fr5_5_tag_beats_reserve_and_lanes():
    found = fuse({**STREET, "width_tag_m": 8.0}, PROFILE, reserve_m=20.0, spread_m=0.0)
    assert (found["width_source"], found["width_confidence"]) == ("osm_tag", "medium")
    assert found["width_m"] == pytest.approx(8.0)
    assert (found["width_low_m"], found["width_high_m"]) == pytest.approx((7.5, 8.5))


def test_fr5_5_reserve_beats_lanes_and_is_kept_as_reserve_m():
    found = fuse(STREET, PROFILE, reserve_m=20.0, spread_m=0.0)
    assert found["width_source"] == "reserve"
    assert found["width_m"] == pytest.approx(13.0)
    assert found["reserve_m"] == pytest.approx(20.0)
    assert [item.source for item in found["estimates"]] == ["reserve", "lanes"]


def test_fr5_5_only_lanes_uses_the_lane_estimate():
    found = fuse(STREET, PROFILE)
    assert found["width_source"] == "lanes"
    assert found["width_m"] == pytest.approx(6.6)
    assert found["reserve_m"] is None
    assert len(found["estimates"]) == 1


def test_fr5_5_no_source_gives_no_width():
    found = fuse({"highway": "path"}, PROFILE)
    assert found["width_m"] is None
    assert found["width_source"] is None
    assert found["estimates"] == []


def test_fr5_7_dropped_tag_falls_to_the_next_source():
    found = fuse({**STREET, "width_tag_m": 2.5}, PROFILE)
    assert found["width_source"] == "lanes"
    assert found["dropped"][0][0] == "osm_tag"


def test_fr5_6_links_hold_the_midpoint_in_order():
    links = check_links(-33.9, 151.1)
    assert links["street_view"] == (
        "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=-33.9,151.1"
    )
    assert links["mapillary"] == "https://www.mapillary.com/app/?lat=-33.9&lng=151.1&z=18"


def graph_of(streets):
    graph = nx.MultiDiGraph(crs="EPSG:32756", boundary=box(0, -1000, 2000, 1000))
    for index, (length, extra) in enumerate(streets):
        u, v = 2 * index, 2 * index + 1
        graph.add_node(u, x=334000.0, y=6246000.0 + index * 50)
        graph.add_node(v, x=334000.0 + length, y=6246000.0 + index * 50)
        graph.add_edge(
            u,
            v,
            0,
            geometry=LineString(
                [(334000.0, 6246000.0 + index * 50), (334000.0 + length, 6246000.0 + index * 50)]
            ),
            segment_id=f"s{index}",
            **{"bike_ok": True, **STREET, **extra},
        )
    return graph


def test_fr5_8_summary_counts_km_by_source_and_confidence():
    graph = graph_of(
        [(1000, {"width_tag_m": 8.0}), (500, {}), (250, {"highway": "path", "lanes_total": 0})]
    )
    graph.graph["boundary"] = box(333000, 6245000, 336000, 6247000)
    found = width_summary(graph, PROFILE)
    assert found == pytest.approx(
        {("osm_tag", "medium"): 1.0, ("lanes", "low"): 0.5, ("none", "none"): 0.25}
    )


def test_fr5_8_summary_ignores_streets_bikes_cannot_use():
    graph = graph_of([(1000, {}), (500, {"bike_ok": False})])
    graph.graph["boundary"] = box(333000, 6245000, 336000, 6247000)
    assert width_summary(graph, PROFILE) == pytest.approx({("lanes", "low"): 1.0})


def test_fr5_8_cli_prints_a_line_per_source_and_confidence(tmp_path, capsys):
    (tmp_path / "network.osm.gz").write_bytes(gzip.compress(Path(FIXTURE).read_bytes(), mtime=0))
    (tmp_path / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    assert main(["width", "summary", REGION, "--snapshot", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    rows = [line.split() for line in lines]
    assert rows
    assert all(row[0] in {"adapter", "osm_tag", "reserve", "lanes", "none"} for row in rows)
    assert all(float(row[-1]) > 0 for row in rows)
