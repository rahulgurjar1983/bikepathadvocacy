import csv
import json
import re

import pytest

from bikeplan import main
from bikeplan.report import merge_pieces
from tests.test_report import COMMITTED, REGION

FIELDS = {"name", "highway", "lts", "aaa", "fix", "lines"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("small")
    assert main(["report", REGION, "--snapshot", str(COMMITTED), "--out", str(out)]) == 0
    return out


def piece(lines, lts=1, aaa=True, fix=None, name="High Street"):
    return {
        "name": name,
        "highway": "residential",
        "lts": lts,
        "aaa": aaa,
        "fix": fix,
        "lines": lines,
    }


def test_fr13_13_each_map_feature_keeps_only_the_five_fields(built):
    data = json.loads((built / "map.json").read_text())
    assert data["segments"]
    for feature in data["segments"]:
        assert set(feature) == FIELDS


def test_fr13_13_coordinates_have_at_most_five_decimals(built):
    data = json.loads((built / "map.json").read_text())
    for feature in data["segments"]:
        for line in feature["lines"]:
            for point in line:
                for value in point:
                    assert round(value, 5) == value


def test_fr13_13_touching_pieces_with_the_same_class_become_one_line():
    first = piece([[[0.0, 0.0], [0.0, 0.001]]])
    second = piece([[[0.0, 0.001], [0.0, 0.002]]])
    merged = merge_pieces([first, second])
    assert len(merged) == 1
    assert merged[0]["lines"] == [[[0.0, 0.0], [0.0, 0.001], [0.0, 0.002]]]


def test_fr13_13_a_change_of_level_safety_fix_or_name_stops_the_merge():
    base = [[[0.0, 0.0], [0.0, 0.001]]]
    other = [[[0.0, 0.001], [0.0, 0.002]]]
    for change in ({"lts": 3}, {"aaa": False}, {"fix": "signals"}, {"name": "Low Street"}):
        assert len(merge_pieces([piece(base), piece(other, **change)])) == 2


def test_fr13_13_pieces_that_do_not_touch_stay_apart():
    first = piece([[[0.0, 0.0], [0.0, 0.001]]])
    second = piece([[[0.0, 0.01], [0.0, 0.011]]])
    assert len(merge_pieces([first, second])) == 2


def test_fr13_13_the_page_data_leaves_out_the_full_network(built):
    html = (built / "report.html").read_text()
    inline = re.search(r'<script type="application/json" id="page-data">(.*?)</script>', html, re.S)
    assert set(json.loads(inline.group(1))) == {"project_shapes", "projects", "summary"}


def test_fr13_13_the_archive_keeps_the_detail_the_recipes_read(built):
    with open(built / "segments.csv") as handle:
        rows = list(csv.DictReader(handle))
    assert {"segment_id", "length_m", "lts", "aaa", "width_source", "fix"} <= set(rows[0])
    segments = json.loads((built / "map.json").read_text())["segments"]
    text = json.dumps(segments)
    assert "length_m" not in text
    assert "width_source" not in text
