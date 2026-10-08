import dataclasses
import hashlib
import shutil
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import numpy
import pytest
import rasterio
from bikeplan.adapters.copernicus_glo30 import copernicus_glo30
from rasterio.transform import from_origin

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.review import route_figures
from bikeplan.route import read_route
from bikeplan.snapshot import OverpassError
from bikeplan.stress import score_edges
from tests.route_helpers import ORIGIN, REGION, SNAPSHOT, densify, lonlat, write_gpx_track

RISE_PER_M = 0.08
TILE_PIXELS = 1000


def tile_name(south, west):
    ns = f"S{-south:02d}" if south < 0 else f"N{south:02d}"
    ew = f"W{-west:03d}" if west < 0 else f"E{west:03d}"
    return f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"


def write_tile(root, south, west):
    folder = root / tile_name(south, west)
    folder.mkdir(parents=True)
    step = 1 / TILE_PIXELS
    lat = south + 1 - (numpy.arange(TILE_PIXELS) + 0.5) * step
    lon = west + (numpy.arange(TILE_PIXELS) + 0.5) * step
    data = (100 * (lon[None, :] - 151) + 10 * (lat[:, None] + 34)).astype("float32")
    with rasterio.open(
        folder / f"{tile_name(south, west)}.tif",
        "w",
        driver="GTiff",
        width=TILE_PIXELS,
        height=TILE_PIXELS,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(west, south + 1, step, step),
    ) as target:
        target.write(data, 1)


@pytest.fixture
def tiles(tmp_path):
    root = tmp_path / "tiles"
    root.mkdir()
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *args: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield root, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def sample(path, lon, lat):
    with rasterio.open(path) as source:
        return next(source.sample([(lon, lat)]))[0]


def test_fr14_9_adapter_cuts_the_tile_and_pins_it_by_sha256(tiles, tmp_path):
    root, url = tiles
    write_tile(root, -34, 151)
    out = tmp_path / "snap"
    box = (-33.96, 151.14, -33.94, 151.16)
    entries = copernicus_glo30(load_region(REGION), box, out, endpoint=url)
    assert [e.name for e in entries] == ["elevation.tif"]
    content = (out / "elevation.tif").read_bytes()
    assert entries[0].sha256 == hashlib.sha256(content).hexdigest()
    assert entries[0].bytes == len(content)
    assert "Copernicus" in entries[0].source
    assert "Copernicus" in entries[0].attribution
    assert tile_name(-34, 151) in entries[0].url
    expected = 100 * 0.15 + 10 * 0.05
    assert sample(out / "elevation.tif", 151.15, -33.95) == pytest.approx(expected, abs=0.1)
    with rasterio.open(out / "elevation.tif") as source:
        assert source.bounds.left <= 151.14 and source.bounds.right >= 151.16
        assert source.bounds.bottom <= -33.96 and source.bounds.top >= -33.94
        assert source.width < 100


def test_fr14_9_adapter_joins_two_tiles_across_a_tile_edge(tiles, tmp_path):
    root, url = tiles
    write_tile(root, -34, 150)
    write_tile(root, -34, 151)
    out = tmp_path / "snap"
    entries = copernicus_glo30(load_region(REGION), (-33.96, 150.99, -33.94, 151.01), out, url)
    assert tile_name(-34, 150) in entries[0].url
    assert tile_name(-34, 151) in entries[0].url
    assert sample(out / "elevation.tif", 150.995, -33.95) == pytest.approx(0.0, abs=0.1)
    assert sample(out / "elevation.tif", 151.005, -33.95) == pytest.approx(1.0, abs=0.1)


def test_fr14_9_adapter_fails_hard_when_a_tile_is_missing(tiles, tmp_path):
    _, url = tiles
    with pytest.raises(OverpassError):
        copernicus_glo30(load_region(REGION), (-33.96, 151.14, -33.94, 151.16), tmp_path / "s", url)


def grid_ramp(snapshot, tmp_path, rise_per_m=RISE_PER_M):
    folder = tmp_path / "snapshot"
    shutil.copytree(snapshot, folder)
    west, north = ORIGIN[0] - 200, ORIGIN[1] + 1600
    rows = numpy.arange(180)
    northing = north - (rows + 0.5) * 10
    data = numpy.tile((rise_per_m * (northing - ORIGIN[1])).astype("float32")[:, None], (1, 180))
    with rasterio.open(
        folder / "elevation.tif",
        "w",
        driver="GTiff",
        width=180,
        height=180,
        count=1,
        dtype="float32",
        crs="EPSG:32756",
        transform=from_origin(west, north, 10, 10),
    ) as target:
        target.write(data, 1)
    return folder


@pytest.fixture(scope="module")
def profile():
    return load_profile(load_region(REGION).profile, "profiles")


@pytest.fixture
def ramp_graph(tmp_path, profile):
    return build(grid_ramp(SNAPSHOT, tmp_path), load_region(REGION), profile)


def route(tmp_path, points):
    return read_route(write_gpx_track(tmp_path / "r.gpx", lonlat(densify(points))))


def test_fr14_9_edge_grade_matches_the_hand_worked_ramp(ramp_graph):
    for _, _, data in ramp_graph.edges(data=True):
        assert "grade_pct" in data
    north_south = [
        d
        for u, v, d in ramp_graph.edges(data=True)
        if abs(ramp_graph.nodes[u]["x"] - ramp_graph.nodes[v]["x"]) < 1
        and abs(ramp_graph.nodes[u]["x"] - (ORIGIN[0] + 0)) < 1
    ]
    assert north_south
    for data in north_south:
        u_to_v_rise = data["rise_m"]
        assert abs(data["grade_pct"]) == pytest.approx(8.0, abs=0.1)
        assert u_to_v_rise == pytest.approx(data["grade_pct"] / 100 * data["length_m"], abs=0.01)


def test_fr14_9_east_west_edges_on_the_ramp_are_flat(ramp_graph):
    flat = [
        d
        for u, v, d in ramp_graph.edges(data=True)
        if abs(ramp_graph.nodes[u]["y"] - ramp_graph.nodes[v]["y"]) < 1
    ]
    assert flat
    for data in flat:
        assert data["grade_pct"] == pytest.approx(0.0, abs=0.1)


def test_fr14_9_steep_stretch_is_flagged_with_length_and_grade(ramp_graph, profile, tmp_path):
    total = route_figures(ramp_graph, profile, route(tmp_path, [(0, 0), (0, 400)]))["total"]
    assert len(total["steep"]) == 1
    stretch = total["steep"][0]
    assert stretch["length_m"] == pytest.approx(400, abs=1)
    assert stretch["grade_pct"] == pytest.approx(8.0, abs=0.1)
    assert stretch["lonlat"] == pytest.approx(lonlat([(0, 0)])[0], abs=5e-3)


def test_fr14_9_downhill_stretch_is_flagged_with_a_negative_grade(ramp_graph, profile, tmp_path):
    total = route_figures(ramp_graph, profile, route(tmp_path, [(0, 400), (0, 0)]))["total"]
    assert [round(s["grade_pct"]) for s in total["steep"]] == [-8]


def test_fr14_9_flat_route_has_no_steep_stretch(ramp_graph, profile, tmp_path):
    total = route_figures(ramp_graph, profile, route(tmp_path, [(0, 0), (400, 0)]))["total"]
    assert total["steep"] == []


def test_fr14_9_stretch_shorter_than_the_minimum_length_is_not_flagged(
    ramp_graph, profile, tmp_path
):
    longer = dataclasses.replace(
        profile,
        grade=dataclasses.replace(
            profile.grade, min_length_m=dataclasses.replace(profile.grade.min_length_m, value=500)
        ),
    )
    total = route_figures(ramp_graph, longer, route(tmp_path, [(0, 0), (0, 400)]))["total"]
    assert total["steep"] == []


def test_fr14_9_gentle_slope_is_not_flagged(tmp_path, profile):
    folder = grid_ramp(SNAPSHOT, tmp_path, rise_per_m=0.03)
    graph = build(folder, load_region(REGION), profile)
    total = route_figures(graph, profile, route(tmp_path, [(0, 0), (0, 400)]))["total"]
    assert total["steep"] == []


def test_fr14_9_figures_give_the_limits_with_their_sources(ramp_graph, profile, tmp_path):
    total = route_figures(ramp_graph, profile, route(tmp_path, [(0, 0), (0, 400)]))["total"]
    assert total["grade_limits"] == {
        "steep_pct": {
            "value": profile.grade.steep_pct.value,
            "source": profile.grade.steep_pct.source,
        },
        "min_length_m": {
            "value": profile.grade.min_length_m.value,
            "source": profile.grade.min_length_m.source,
        },
    }


def test_fr14_9_grade_does_not_change_the_stress_level(ramp_graph, profile):
    flat = build(SNAPSHOT, load_region(REGION), profile)
    assert score_edges(ramp_graph, profile) == score_edges(flat, profile)


@pytest.mark.parametrize("name", ["generic", "au-nsw"])
def test_fr14_9_every_profile_sets_the_steep_limits_with_sources(name):
    grade = load_profile(name, "profiles").grade
    assert grade.steep_pct.value > 0 and grade.steep_pct.source.strip()
    assert grade.min_length_m.value > 0 and grade.min_length_m.source.strip()
