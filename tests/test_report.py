import gzip
import hashlib
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from bikeplan import main

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
FILES = ["figures.json", "report.html", "segments.csv"]


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    folder = tmp_path_factory.mktemp("snapshot")
    (folder / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (folder / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    return folder


@pytest.fixture(scope="module")
def output(snapshot, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    real = socket.socket.connect

    def blocked(*args):
        raise AssertionError("network call")

    socket.socket.connect = blocked
    try:
        assert main(["report", REGION, "--snapshot", str(snapshot), "--out", str(out)]) == 0
    finally:
        socket.socket.connect = real
    return out


def test_fr13_1_writes_every_file_and_sha256sums_matches(output):
    for name in [*FILES, "SHA256SUMS"]:
        assert (output / name).is_file()
    lines = (output / "SHA256SUMS").read_text().splitlines()
    assert [line.split("  ")[1] for line in lines] == sorted(FILES)
    for line in lines:
        digest, name = line.split("  ")
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest


def test_fr13_1_figures_are_sorted_with_every_field(output):
    figures = json.loads((output / "figures.json").read_text())
    assert [item["id"] for item in figures] == ["F1", "F2", "F3"]
    for item in figures:
        assert set(item) == {
            "id",
            "label",
            "value",
            "unit",
            "spec",
            "method",
            "inputs",
            "sources",
            "recipe",
        }
        assert (
            item["inputs"][0]["sha256"]
            == hashlib.sha256((output / item["inputs"][0]["name"]).read_bytes()).hexdigest()
        )


def test_fr13_1_each_recipe_prints_its_value_from_the_release_files(output):
    for item in json.loads((output / "figures.json").read_text()):
        shown = subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=output,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert float(shown) == pytest.approx(item["value"])


def test_fr13_1_a_stage_the_code_lacks_gives_one_plain_line(output):
    html = (output / "report.html").read_text()
    for stage in ("access", "propose"):
        assert html.count(f"The {stage} stage is not built yet.") == 1


def test_fr13_1_the_report_holds_the_stage_figures_as_links(output):
    html = (output / "report.html").read_text()
    for figure in ("F1", "F2", "F3"):
        assert f'href="#{figure}"' in html
        assert f'id="{figure}"' in html


def test_fr13_1_same_inputs_give_the_same_bytes(snapshot, output, tmp_path):
    assert main(["report", REGION, "--snapshot", str(snapshot), "--out", str(tmp_path)]) == 0
    for name in [*FILES, "SHA256SUMS"]:
        assert (tmp_path / name).read_bytes() == (output / name).read_bytes()


def test_fr1_10_the_report_names_the_author_of_the_region_file(output):
    assert "Rahul Gurjar, Kogarah" in (output / "report.html").read_text()


def test_fr1_10_a_missing_author_fails_and_names_the_key(snapshot, tmp_path, capsys):
    code = main(
        ["report", "regions/test-grid.yaml", "--snapshot", str(snapshot), "--out", str(tmp_path)]
    )
    assert code == 1
    assert "report.author" in capsys.readouterr().err
    assert not (tmp_path / "report.html").exists()
