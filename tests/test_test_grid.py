import json
import math
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from bikeplan import main
from bikeplan.access import scene
from bikeplan.config import load_profile, load_region
from bikeplan.fit import segment_fit
from bikeplan.network import bike_segments, build
from bikeplan.snapshot import verify_snapshot
from bikeplan.stress import score_edges

REGION = "regions/test-grid.yaml"
COMMITTED = Path("tests/fixtures/test-grid/snapshot")
FILES = ["boundary.geojson", "network.osm.gz", "places.json", "population.gpkg"]
JUNCTIONS = (0, 200, 400, 600)


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    folder = tmp_path_factory.mktemp("grid") / "snapshot"
    subprocess.run(
        [sys.executable, "scripts/make_test_grid.py", str(folder)], check=True, capture_output=True
    )
    return folder


@pytest.fixture(scope="module")
def region():
    return load_region(REGION)


@pytest.fixture(scope="module")
def profile(region):
    return load_profile(region.profile)


@pytest.fixture(scope="module")
def graph(snapshot, region, profile):
    return build(snapshot, region, profile)


@pytest.fixture(scope="module")
def scores(graph, profile):
    return score_edges(graph, profile)


@pytest.fixture(scope="module")
def frame(graph):
    main_nodes = {
        node
        for u, v, data in graph.edges(data=True)
        if data.get("name") == "Main Road"
        for node in (u, v)
    }
    xs = [graph.nodes[n]["x"] for n in main_nodes]
    ys = [graph.nodes[n]["y"] for n in main_nodes]
    return sum(xs) / len(xs) - 400, min(ys) + 200


def rows_of(path, sql):
    database = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return database.execute(sql).fetchall()
    finally:
        database.close()


def place(graph, frame, x, y):
    wanted = (frame[0] + x, frame[1] + y)
    near = [n for n, d in graph.nodes(data=True) if math.dist((d["x"], d["y"]), wanted) < 1.0]
    assert len(near) == 1
    return near[0]


def is_main(data):
    return data.get("name") == "Main Road"


def test_fr11_3_the_generator_rebuilds_the_committed_snapshot(snapshot, region):
    passed, failed = verify_snapshot(COMMITTED)
    assert failed == []
    assert len(passed) == 4
    assert region.id == "test-grid"
    assert (
        Path(region.boundary.geojson).read_bytes() == (snapshot / "boundary.geojson").read_bytes()
    )
    for name in ["boundary.geojson", "network.osm.gz", "places.json"]:
        assert (snapshot / name).read_bytes() == (COMMITTED / name).read_bytes()
    made = json.loads((snapshot / "manifest.json").read_text())
    kept = json.loads((COMMITTED / "manifest.json").read_text())
    assert [item["name"] for item in kept["files"]] == FILES
    assert made["files"][:3] == kept["files"][:3]
    for key in ("region", "snapshot_id", "osm_date", "created_at", "tool_version"):
        assert made[key] == kept[key]
    rows = "select h3, population, geom from population"
    assert rows_of(snapshot / "population.gpkg", rows) == rows_of(
        COMMITTED / "population.gpkg", rows
    )


def test_fr11_3_main_road_edges_are_lts_4_and_not_aaa(graph, scores):
    keys = [(u, v, k) for u, v, k, d in graph.edges(keys=True, data=True) if is_main(d)]
    assert len(keys) == 10
    for key in keys:
        assert scores[key]["lts"] == 4
        assert scores[key]["aaa"] is False


def test_fr11_3_main_road_fit_is_no_fit(graph, profile, region):
    weights = region.proposals.disruption_weights
    found = [
        segment_fit(segment, profile, weights)
        for segment in bike_segments(graph).values()
        if is_main(segment["edges"][0][1])
    ]
    assert len(found) == 5
    for result in found:
        assert result["status"] == "no_fit"


def side_keys(graph, frame, y):
    centre = place(graph, frame, 400, y)
    return [
        (u, v, k)
        for u, v, k, d in graph.edges(keys=True, data=True)
        if not is_main(d) and centre in (u, v)
    ]


@pytest.mark.parametrize("y", [0, 200, 400])
def test_fr11_3_side_streets_at_unsignalised_main_road_junctions_are_lts_3(graph, scores, frame, y):
    keys = side_keys(graph, frame, y)
    assert len(keys) == 4
    for key in keys:
        assert scores[key]["lts"] == 3
        assert scores[key]["aaa"] is False


def test_fr11_3_side_streets_at_the_signals_are_lts_1_and_aaa(graph, scores, frame):
    keys = side_keys(graph, frame, 600)
    assert len(keys) == 4
    for key in keys:
        assert scores[key]["lts"] == 1
        assert scores[key]["aaa"] is True


def test_fr11_3_all_other_residential_edges_are_lts_1_and_aaa(graph, scores, frame):
    touched = {key for y in JUNCTIONS for key in side_keys(graph, frame, y)}
    others = [
        key
        for key, d in ((k, graph.edges[k]) for k in graph.edges(keys=True))
        if not is_main(d) and key not in touched
    ]
    assert len(others) == 26
    for key in others:
        assert scores[key]["lts"] == 1
        assert scores[key]["aaa"] is True


def test_fr11_3_the_1000_people_sit_on_8_nodes_with_125_each(graph, frame, snapshot, region):
    people = scene(graph, region, snapshot).resident.people
    wanted = {place(graph, frame, x, y): 125.0 for x in (0, 200) for y in JUNCTIONS}
    assert people == wanted


def test_fr11_3_the_school_snaps_to_the_junction_at_600_200(graph, frame, snapshot, region):
    found = scene(graph, region, snapshot)
    assert [kind for kind, _ in found.placed] == ["school"]
    assert found.placed[0][1] == place(graph, frame, 600, 200)


def test_fr11_3_the_baseline_region_score_is_25(snapshot, tmp_path):
    out = tmp_path / "access"
    assert main(["access", REGION, "--snapshot", str(snapshot), "--out", str(out)]) == 0
    summary = json.loads((out / "access_summary.json").read_text())
    assert summary["score"] == 25.0
    homes = json.loads((out / "access_homes.geojson").read_text())["features"]
    safe = sorted(f["properties"]["people"] for f in homes if f["properties"]["score"] > 0)
    assert safe == [125.0, 125.0]


def test_fr11_3_the_only_project_is_signals_at_the_junction_at_y_200(
    snapshot, graph, frame, tmp_path
):
    out = tmp_path / "propose"
    assert main(["propose", REGION, "--snapshot", str(snapshot), "--out", str(out)]) == 0
    projects = json.loads((out / "projects.json").read_text())
    assert len(projects) == 1
    project = projects[0]
    assert project["gain"] == 75.0
    assert project["score_after"] == 100.0
    junction = place(graph, frame, 400, 200)
    assert [item["id"] for item in project["elements"]] == [f"junction:{junction}"]
    assert project["elements"][0]["fix"] == "signals"
    assert all(
        item["street"] != "Main Road" or item["fix"] == "signals" for item in project["elements"]
    )
