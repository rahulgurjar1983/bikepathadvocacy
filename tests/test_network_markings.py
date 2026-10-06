import gzip
import json
from pathlib import Path

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from tests.test_network_sides import BOUNDARY

FIXTURE = Path("tests/fixtures/network/markings.osm")


def test_fr4_1_lane_markings_tag_is_kept_on_the_edge(tmp_path):
    (tmp_path / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (tmp_path / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    region = load_region("regions/au-nsw-bayside.yaml")
    graph = build(tmp_path, region, load_profile(region.profile))
    found = {d["osm_way"]: d.get("lane_markings") for _, _, d in graph.edges(data=True)}
    assert found == {701: "no", 702: None}
