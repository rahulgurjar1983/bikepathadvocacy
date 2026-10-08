import json
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import geopandas
import pytest
from pyproj import Transformer
from shapely.geometry import box as rectangle

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.snapshot import ADAPTERS, OverpassError, nsw_cadastre
from bikeplan.width import fuse

BOX = (-33.941, 151.1065, -33.919, 151.1335)
LIMIT = 1000
CLUSTER = 1500
STEP = 0.00005
SIZE = 0.00003
GRID = Path("tests/fixtures/test-grid/snapshot")


def lots(count):
    found = []
    for index in range(count):
        west = 151.1070 + (index % 40) * STEP
        south = -33.9400 + (index // 40) * STEP
        found.append((index + 1, (west, south, west + SIZE, south + SIZE)))
    return found


@pytest.fixture
def cadastre_server():
    state = {"requests": [], "lots": lots(CLUSTER), "reply": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            state["requests"].append({"path": parts.path, "query": query})
            if state["reply"] is not None:
                content = json.dumps(state["reply"]).encode()
            else:
                west, south, east, north = map(float, query["geometry"][0].split(","))
                hits = [
                    (number, extent)
                    for number, extent in state["lots"]
                    if extent[0] <= east
                    and extent[2] >= west
                    and extent[1] <= north
                    and extent[3] >= south
                ][:LIMIT]
                features = [
                    {
                        "type": "Feature",
                        "id": number,
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [list(rectangle(*extent).exterior.coords)],
                        },
                        "properties": {"objectid": number, "lotidstring": f"{number}//DP1"},
                    }
                    for number, extent in hits
                ]
                content = json.dumps({"type": "FeatureCollection", "features": features}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/MapServer/9", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def bayside():
    return load_region("regions/au-nsw-bayside.yaml")


def envelope_width(request):
    west, _, east, _ = map(float, request["query"]["geometry"][0].split(","))
    return east - west


def test_fr10_1_full_tile_is_split_and_every_parcel_is_stored(cadastre_server, tmp_path):
    endpoint, state = cadastre_server

    nsw_cadastre(bayside(), BOX, tmp_path, endpoint)

    stored = geopandas.read_file(tmp_path / "parcels.gpkg")
    assert len(stored) == CLUSTER
    assert stored["objectid"].is_unique
    widths = {round(envelope_width(request), 6) for request in state["requests"]}
    assert len(widths) > 1
    assert all(request["path"].endswith("/MapServer/9/query") for request in state["requests"])


def test_fr10_1_tile_under_the_limit_is_fetched_once(cadastre_server, tmp_path):
    endpoint, state = cadastre_server
    state["lots"] = lots(10)

    nsw_cadastre(bayside(), BOX, tmp_path, endpoint)

    stored = geopandas.read_file(tmp_path / "parcels.gpkg")
    widths = {round(envelope_width(request), 6) for request in state["requests"]}
    assert len(stored) == 10
    assert len(widths) == 1


def test_fr10_1_parcels_are_stored_as_polygons_in_degrees(cadastre_server, tmp_path):
    endpoint, _ = cadastre_server

    nsw_cadastre(bayside(), BOX, tmp_path, endpoint)

    stored = geopandas.read_file(tmp_path / "parcels.gpkg")
    assert stored.crs.to_epsg() == 4326
    assert set(stored.geometry.geom_type) == {"Polygon"}


def test_fr10_1_adapter_is_registered_and_bayside_turns_it_on():
    assert ADAPTERS["nsw_cadastre"] is nsw_cadastre
    assert "nsw_cadastre" in bayside().snapshot.adapters


def test_fr10_8_service_error_fails_the_snapshot(cadastre_server, tmp_path):
    endpoint, state = cadastre_server
    state["reply"] = {"error": {"code": 500, "message": "boom", "details": []}}

    with pytest.raises(OverpassError, match="boom"):
        nsw_cadastre(bayside(), BOX, tmp_path, endpoint)


def test_fr10_8_manifest_entry_has_every_field(cadastre_server, tmp_path):
    endpoint, _ = cadastre_server

    entries = nsw_cadastre(bayside(), BOX, tmp_path, endpoint)

    assert [entry.name for entry in entries] == ["parcels.gpkg"]
    fields = entries[0].as_dict()
    assert all(fields[name] not in ("", 0, None) for name in fields)
    assert fields["licence"] == "CC BY 4.0"
    assert "Spatial Services" in fields["attribution"]
    assert json.loads(fields["request"])["parcels"] == CLUSTER


def grid_with_parcels(tmp_path):
    folder = tmp_path / "snapshot"
    shutil.copytree(GRID, folder)
    origin = Transformer.from_crs(4326, 32756, always_xy=True).transform(151.15, -33.95)
    east0, north0 = round(origin[0]), round(origin[1])
    blocks = [rectangle(10, -300, 40, 900), rectangle(-40, -300, -10, 900)]
    shifted = [
        rectangle(
            east0 + b.bounds[0], north0 + b.bounds[1], east0 + b.bounds[2], north0 + b.bounds[3]
        )
        for b in blocks
    ]
    frame = geopandas.GeoDataFrame({"objectid": [1, 2]}, geometry=shifted, crs=32756)
    frame.to_crs(4326).to_file(folder / "parcels.gpkg", driver="GPKG")
    return folder, east0


def test_fr10_2_segment_between_saved_parcel_rows_gets_the_measured_reserve(tmp_path):
    folder, east0 = grid_with_parcels(tmp_path)
    profile = load_profile("au-nsw")
    region = load_region("regions/test-grid.yaml")

    graph = build(folder, region, profile)

    along = [
        data
        for u, v, data in graph.edges(data=True)
        if abs(graph.nodes[u]["x"] - east0) < 1 and abs(graph.nodes[v]["x"] - east0) < 1
    ]
    assert along
    found = fuse(along[0], profile)
    assert found["reserve_m"] == pytest.approx(20.0, abs=0.1)
    assert found["width_source"] == "reserve"
    assert found["width_m"] == pytest.approx(
        20.0 - 2 * profile.widths_m.verge_default.value, abs=0.1
    )


def test_fr10_2_segment_far_from_any_parcel_has_no_reserve(tmp_path):
    folder, east0 = grid_with_parcels(tmp_path)
    profile = load_profile("au-nsw")
    region = load_region("regions/test-grid.yaml")

    graph = build(folder, region, profile)

    far = [
        data
        for u, v, data in graph.edges(data=True)
        if abs(graph.nodes[u]["x"] - east0 - 400) < 1 and abs(graph.nodes[v]["x"] - east0 - 400) < 1
    ]
    assert far
    assert fuse(far[0], profile)["reserve_m"] is None


def test_fr10_2_snapshot_without_parcels_builds_with_no_reserve():
    profile = load_profile("au-nsw")
    region = load_region("regions/test-grid.yaml")

    graph = build(GRID, region, profile)

    assert all(fuse(data, profile)["reserve_m"] is None for _, _, data in graph.edges(data=True))
