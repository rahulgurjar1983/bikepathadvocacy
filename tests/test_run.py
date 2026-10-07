import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from bikeplan import main

REGION = "regions/test-grid.yaml"
COMMITTED = Path("tests/fixtures/test-grid/snapshot")
RUN = "import sys\nfrom bikeplan import main\nsys.exit(main(sys.argv[1:]))\n"
FILES = [
    "access_homes.geojson",
    "network.geojson",
    "places.geojson",
    "projects.csv",
    "projects.geojson",
    "projects.json",
    "report.html",
    "summary.json",
]


def run_command(folder, out):
    return main(["run", REGION, "--snapshot", str(folder), "--out", str(out)])


def run_child(out, seed):
    args = ["run", REGION, "--snapshot", str(COMMITTED), "--out", str(out)]
    env = {**os.environ, "PYTHONHASHSEED": seed}
    done = subprocess.run(
        [sys.executable, "-c", RUN, *args], env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    return out


@pytest.fixture(scope="module")
def blocked_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("blocked") / "out"

    def refuse(*args, **kwargs):
        raise AssertionError("network access")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket, "socket", refuse)
        patch.setattr(socket, "create_connection", refuse)
        assert run_command(COMMITTED, out) == 0
    return out


@pytest.fixture(scope="module")
def children(tmp_path_factory):
    base = tmp_path_factory.mktemp("children")
    return run_child(base / "one", "1"), run_child(base / "two", "2")


def test_fr9_1_the_run_writes_every_file(blocked_out):
    for name in [*FILES, "outputs.sha256"]:
        assert (blocked_out / name).is_file(), name


def test_fr9_1_the_summary_names_the_run_and_the_scores(blocked_out):
    summary = json.loads((blocked_out / "summary.json").read_text())
    assert summary["region"] == "test-grid"
    assert summary["snapshot"] == "2026-10-01"
    assert len(summary["config_hash"]) == 64
    assert summary["code_version"]
    assert summary["score"] == {"before": 25.0, "after": 100.0}
    assert summary["not_snapped"] == {"places": 0, "people": 0}
    assert summary["km_by_fix"] == {}
    assert summary["disruption"]["signals"] == 1


def test_fr9_1_the_network_file_holds_each_edge_with_its_verdict(blocked_out):
    network = json.loads((blocked_out / "network.geojson").read_text())
    main_road = [
        item["properties"]
        for item in network["features"]
        if item["properties"].get("name") == "Main Road"
    ]
    assert main_road
    for item in main_road:
        assert item["lts"] == 4
        assert item["aaa"] is False
        assert item["fix"] is None
        assert item["reason"]
        assert "width_m" in item
        assert "width_source" in item


def test_fr9_1_the_hash_file_lists_every_file_sorted_by_name(blocked_out):
    lines = (blocked_out / "outputs.sha256").read_text().splitlines()
    names = [line.split("  ")[1] for line in lines]
    assert names == sorted(FILES)
    for line in lines:
        digest, name = line.split("  ")
        assert hashlib.sha256((blocked_out / name).read_bytes()).hexdigest() == digest


def test_fr9_1_a_changed_snapshot_byte_fails_the_run(tmp_path, capsys):
    folder = tmp_path / "snapshot"
    shutil.copytree(COMMITTED, folder)
    path = folder / "places.json"
    path.write_bytes(path.read_bytes() + b" ")
    assert run_command(folder, tmp_path / "out") == 1
    assert "places.json" in capsys.readouterr().err
    assert not (tmp_path / "out" / "summary.json").exists()


def test_fr11_6_the_run_with_sockets_blocked_succeeds(blocked_out):
    assert (blocked_out / "summary.json").is_file()


def test_nfr2_the_run_opens_no_connection(blocked_out):
    assert (blocked_out / "outputs.sha256").is_file()


def test_fr9_2_json_is_sorted_with_two_space_indent(blocked_out):
    for name in ("summary.json", "projects.json", "network.geojson", "places.geojson"):
        text = (blocked_out / name).read_text()
        assert text == json.dumps(json.loads(text), sort_keys=True, indent=2) + "\n", name


def test_fr9_2_numbers_are_rounded_to_fixed_places(blocked_out):
    projects = json.loads((blocked_out / "projects.json").read_text())
    for project in projects:
        assert project["gain"] == round(project["gain"], 1)
        assert project["score_after"] == round(project["score_after"], 1)
    summary = json.loads((blocked_out / "summary.json").read_text())
    for value in summary["km_by_lts"].values():
        assert value == round(value, 3)


def test_fr9_2_geojson_features_are_sorted_by_id_with_seven_place_coordinates(blocked_out):
    for name in ("network", "places", "projects", "access_homes"):
        data = json.loads((blocked_out / f"{name}.geojson").read_text())
        ids = [str(item["id"]) for item in data["features"]]
        assert ids == sorted(ids), name
        assert ids
        text = json.dumps(data["features"][0]["geometry"]["coordinates"])
        for number in text.replace("[", " ").replace("]", " ").replace(",", " ").split():
            assert len(number.split(".")[-1]) <= 7, name


def test_fr9_2_two_runs_give_the_same_bytes(children):
    one, two = children
    for name in [*FILES, "outputs.sha256"]:
        assert (one / name).read_bytes() == (two / name).read_bytes(), name


def test_fr11_5_two_test_grid_runs_give_the_same_hash_file(children):
    one, two = children
    assert (one / "outputs.sha256").read_text() == (two / "outputs.sha256").read_text()
