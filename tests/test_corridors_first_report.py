import hashlib
import importlib
import json
import shutil

import pytest
from shapely.geometry import LineString, box

from bikeplan import main
from bikeplan.propose import Corridors
from tests.test_edition import REGION, SNAPSHOT
from tests.test_propose_corridor import OPEN, RAIL, corridor_files, loop_graph, way

propose = importlib.import_module("bikeplan.propose")


def test_fr18_6_a_rail_side_candidate_is_listed_with_its_nodes_length_and_label():
    found = propose.corridor_candidates(loop_graph(), Corridors([("railway", RAIL)], OPEN))
    assert len(found) == 1
    assert (found[0]["a"], found[0]["b"], found[0]["label"]) == (0, 1, "railway")
    assert found[0]["length_m"] == pytest.approx(1000.0, rel=0.1)


def test_fr18_6_no_candidate_is_listed_without_open_land_beside_the_line():
    land = box(-100, 500, 1100, 900)
    assert propose.corridor_candidates(loop_graph(), Corridors([("railway", RAIL)], land)) == []


def test_fr18_6_a_short_line_gives_no_candidate():
    short = LineString([(0, 30), (100, 30)])
    assert (
        propose.corridor_candidates(loop_graph(100.0), Corridors([("railway", short)], OPEN)) == []
    )


@pytest.fixture(scope="module")
def with_corridors(tmp_path_factory):
    base = tmp_path_factory.mktemp("corridors-first")
    folder = base / "snapshot"
    shutil.copytree(SNAPSHOT, folder)
    corridor_files(folder)
    out = base / "out"
    assert main(["report", REGION, "--snapshot", str(folder), "--out", str(out)]) == 0
    return out


def test_fr18_6_the_report_holds_corridors_first_as_a_fifth_option(with_corridors):
    data = json.loads((with_corridors / "options.json").read_text())
    ids = [item["id"] for item in data["options"]]
    assert ids[-1] == "corridors"
    assert len(ids) == 5
    assert "Corridors first" in (with_corridors / "report.html").read_text()


@pytest.fixture(scope="module")
def beside_the_grid(tmp_path_factory):
    base = tmp_path_factory.mktemp("corridors-grid")
    folder = base / "snapshot"
    shutil.copytree(SNAPSHOT, folder)
    ring = [(-33.9470, 151.1490), (-33.9470, 151.1580), (-33.9495, 151.1580), (-33.9495, 151.1490)]
    line = [(-33.9482, 151.1500), (-33.9482, 151.1566)]
    elements = [way({"railway": "rail"}, line), way({"landuse": "grass"}, [*ring, ring[0]])]
    (folder / "corridors.json").write_text(json.dumps({"elements": elements}))
    places = json.loads((folder / "places.json").read_text())
    places["elements"].append(
        {
            "type": "node",
            "id": 3001,
            "lat": -33.9482,
            "lon": 151.15,
            "tags": {"amenity": "school", "name": "West School"},
        }
    )
    raw = json.dumps(places).encode()
    (folder / "places.json").write_bytes(raw)
    manifest = json.loads((folder / "manifest.json").read_text())
    entry = next(item for item in manifest["files"] if item["name"] == "places.json")
    entry["sha256"], entry["bytes"] = hashlib.sha256(raw).hexdigest(), len(raw)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    out = base / "out"
    assert main(["report", REGION, "--snapshot", str(folder), "--out", str(out)]) == 0
    return out


def test_fr18_6_a_corridor_candidate_beside_the_grid_is_a_new_path_work(beside_the_grid):
    data = json.loads((beside_the_grid / "options.json").read_text())
    option = next(item for item in data["options"] if item["id"] == "corridors")
    kinds = {work["fix"] for work in option["works"]}
    assert "new_path" in kinds
