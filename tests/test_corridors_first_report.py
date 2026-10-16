import importlib
import json
import shutil

import pytest
from shapely.geometry import LineString, box

from bikeplan import main
from bikeplan.propose import Corridors
from tests.test_edition import REGION, SNAPSHOT
from tests.test_propose_corridor import OPEN, RAIL, corridor_files, loop_graph

propose = importlib.import_module("bikeplan.propose")


def test_fr18_6_a_rail_side_candidate_is_listed_with_its_nodes_length_and_label():
    found = propose.corridor_candidates(loop_graph(), Corridors([("railway", RAIL)], OPEN))
    assert len(found) == 1
    assert (found[0]["a"], found[0]["b"], found[0]["label"]) == (0, 1, "railway")
    assert found[0]["length_m"] == pytest.approx(1000.0, rel=0.05)


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
