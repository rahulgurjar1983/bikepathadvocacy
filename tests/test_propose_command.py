import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from bikeplan import main
from tests.test_access_scores import snapshot

REGION = "regions/au-nsw-bayside.yaml"
RUN = "import sys\nfrom bikeplan import main\nsys.exit(main(sys.argv[1:]))\n"


def run(folder, out):
    return main(["propose", REGION, "--snapshot", str(folder), "--out", str(out)])


def test_fr8_8_the_command_writes_the_three_files(tmp_path):
    folder = snapshot(tmp_path / "snap")
    out = tmp_path / "out"
    assert run(folder, out) == 0
    projects = json.loads((out / "projects.json").read_text())
    assert len(projects) >= 1
    assert [item["rank"] for item in projects] == list(range(1, len(projects) + 1))
    rows = list(csv.DictReader((out / "projects.csv").open()))
    assert [row["id"] for row in rows] == [item["id"] for item in projects]
    assert {"rank", "id", "name", "gain", "score_after"} <= set(rows[0])
    shapes = json.loads((out / "projects.geojson").read_text())
    assert shapes["type"] == "FeatureCollection"
    count = sum(len(item["elements"]) for item in projects)
    assert len(shapes["features"]) == count
    ids = {item["id"]: item["rank"] for item in projects}
    for feature in shapes["features"]:
        assert ids[feature["properties"]["project"]] == feature["properties"]["rank"]
        assert feature["geometry"]["type"] in {"LineString", "MultiLineString", "Point"}


def test_fr8_8_the_command_fails_hard_without_a_places_file(tmp_path, capsys):
    folder = snapshot(tmp_path / "snap")
    (folder / "places.json").unlink()
    assert run(folder, tmp_path / "o") == 1
    assert "places.json" in capsys.readouterr().err


def test_fr8_10_two_runs_give_byte_identical_files(tmp_path):
    folder = snapshot(tmp_path / "snap")
    outs = []
    for seed in ("1", "2"):
        out = tmp_path / f"out{seed}"
        env = {**os.environ, "PYTHONHASHSEED": seed}
        args = ["propose", REGION, "--snapshot", str(folder), "--out", str(out)]
        done = subprocess.run(
            [sys.executable, "-c", RUN, *args], env=env, capture_output=True, text=True
        )
        assert done.returncode == 0, done.stderr
        outs.append(out)
    for name in ("projects.json", "projects.csv", "projects.geojson"):
        assert (outs[0] / name).read_bytes() == (outs[1] / name).read_bytes()
    assert Path(outs[0] / "projects.json").stat().st_size > 2
