import json
from pathlib import Path

import pytest
import yaml
from pyproj import Transformer

from bikeplan import main
from bikeplan.config import load_region
from tests.route_helpers import corner_route, lonlat, write_gpx_track

TO_METRES = Transformer.from_crs(4326, 32756, always_xy=True)


def run(tmp_path, route, extra=()):
    return main(
        ["region", "corridor", str(route), "--id", "ride", "--out", str(tmp_path / "out"), *extra]
    )


def test_fr14_2_region_boundary_holds_the_route_and_the_buffer(tmp_path):
    route = write_gpx_track(tmp_path / "r.gpx", lonlat(corner_route()))
    assert run(tmp_path, route, ["--like", "regions/test-grid.yaml"]) == 0
    region = load_region(tmp_path / "out" / "ride.yaml")
    assert region.id == "ride"
    assert region.analysis_buffer_m == 500
    boundary = json.loads((tmp_path / "out" / "ride.geojson").read_text())
    ring = boundary["geometry"]["coordinates"][0]
    xs, ys = zip(*[TO_METRES.transform(lon, lat) for lon, lat in ring], strict=True)
    ox, oy = TO_METRES.transform(151.15, -33.95)
    assert min(xs) - ox == pytest.approx(-500, abs=2)
    assert max(xs) - ox == pytest.approx(900, abs=2)
    assert min(ys) - oy == pytest.approx(-500, abs=2)
    assert max(ys) - oy == pytest.approx(900, abs=2)
    assert region.boundary.geojson == str(tmp_path / "out" / "ride.geojson")


def test_fr14_2_corridor_region_keeps_the_other_settings(tmp_path):
    route = write_gpx_track(tmp_path / "r.gpx", lonlat(corner_route()))
    run(tmp_path, route, ["--like", "regions/test-grid.yaml"])
    made = yaml.safe_load((tmp_path / "out" / "ride.yaml").read_text())
    base = yaml.safe_load(Path("regions/test-grid.yaml").read_text())
    assert made["profile"] == base["profile"]
    assert made["access"] == base["access"]
    assert "osm_relation" not in made["boundary"]


def test_fr14_2_area_over_300_km2_is_refused_with_a_split_message(tmp_path, capsys):
    long_route = [(0, 0), (0, 350000)]
    route = write_gpx_track(tmp_path / "long.gpx", lonlat(long_route))
    assert run(tmp_path, route, ["--like", "regions/test-grid.yaml"]) == 1
    err = capsys.readouterr().err
    assert "300 km" in err
    assert "split" in err
    assert not (tmp_path / "out" / "ride.yaml").exists()
