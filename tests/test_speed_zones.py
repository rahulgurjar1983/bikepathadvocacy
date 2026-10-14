import gzip
import json
import re
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import geopandas
import pytest
from pyproj import Transformer
from shapely.geometry import LineString

from bikeplan.adapters.tfnsw_speed_zones import tfnsw_speed_zones
from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.snapshot import ADAPTERS, OverpassError

BOX = (-33.941, 151.1065, -33.919, 151.1335)
LIMIT = 1000
CLUSTER = 1300
GRID = Path("tests/fixtures/test-grid/snapshot")


def pieces(count):
    found = []
    for index in range(count):
        west = 151.1070 + (index % 50) * 0.00004
        south = -33.9400 + (index // 50) * 0.00004
        found.append((index + 1, [(west, south), (west + 0.00002, south + 0.00002)]))
    return found


@pytest.fixture
def zone_server():
    state = {
        "requests": [],
        "lines": pieces(CLUSTER),
        "reply": None,
        "kind": "Ordinary Permanent",
        "kinds": {},
    }

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
                    (number, line)
                    for number, line in state["lines"]
                    if max(x for x, _ in line) >= west
                    and min(x for x, _ in line) <= east
                    and max(y for _, y in line) >= south
                    and min(y for _, y in line) <= north
                ][:LIMIT]
                features = [
                    {
                        "type": "Feature",
                        "id": number,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[x, y, -1000] for x, y in line],
                        },
                        "properties": {
                            "objectid": number,
                            "type": state["kinds"].get(number, state["kind"]),
                            "status": "Existing",
                            "direction": "Both Directions",
                            "speed": "50 km/h",
                        },
                    }
                    for number, line in hits
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
        yield f"http://127.0.0.1:{server.server_port}/FeatureServer/0", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def bayside():
    return load_region("regions/au-nsw-bayside.yaml")


def test_fr10_4_full_tile_is_split_and_every_zone_is_stored(zone_server, tmp_path):
    endpoint, state = zone_server

    tfnsw_speed_zones(bayside(), BOX, tmp_path, endpoint)

    stored = geopandas.read_file(tmp_path / "speed_zones.gpkg")
    assert len(stored) == CLUSTER
    assert stored["objectid"].is_unique
    assert len(state["requests"]) > 1
    assert all(r["path"].endswith("/FeatureServer/0/query") for r in state["requests"])


def test_fr10_4_zones_keep_a_numeric_speed_as_lines_in_degrees(zone_server, tmp_path):
    endpoint, state = zone_server
    state["lines"] = pieces(10)

    tfnsw_speed_zones(bayside(), BOX, tmp_path, endpoint)

    stored = geopandas.read_file(tmp_path / "speed_zones.gpkg")
    assert len(stored) == 10
    assert stored.crs.to_epsg() == 4326
    assert set(stored.geometry.geom_type) == {"LineString"}
    assert not stored.geometry.has_z.any()
    assert set(stored["speed_kmh"]) == {50.0}
    assert set(stored["speed_source"]) == {"zone"}


def test_fr10_4_only_permanent_posted_zones_are_kept(zone_server, tmp_path):
    endpoint, state = zone_server
    state["lines"] = pieces(6)
    state["kinds"] = {2: "School", 3: "Variable", 4: "Road Work", 5: "Wet Weather"}

    tfnsw_speed_zones(bayside(), BOX, tmp_path, endpoint)

    stored = geopandas.read_file(tmp_path / "speed_zones.gpkg")
    assert sorted(stored["objectid"]) == [1, 6]


def test_fr10_4_a_second_run_reads_the_tile_cache(zone_server, tmp_path):
    endpoint, state = zone_server
    state["lines"] = pieces(10)
    tfnsw_speed_zones(bayside(), BOX, tmp_path, endpoint)
    first = len(state["requests"])

    tfnsw_speed_zones(bayside(), BOX, tmp_path, endpoint)

    assert first > 0
    assert len(state["requests"]) == first


def test_fr10_4_adapter_is_registered_and_bayside_turns_it_on():
    assert ADAPTERS["tfnsw_speed_zones"] is tfnsw_speed_zones
    assert "tfnsw_speed_zones" in bayside().snapshot.adapters


def test_fr10_8_speed_zone_service_error_fails_the_snapshot(zone_server, tmp_path):
    endpoint, state = zone_server
    state["reply"] = {"error": {"code": 500, "message": "boom", "details": []}}

    with pytest.raises(OverpassError, match="boom"):
        tfnsw_speed_zones(bayside(), BOX, tmp_path, endpoint)


def test_fr10_8_speed_zone_manifest_entry_has_every_field(zone_server, tmp_path):
    endpoint, _ = zone_server

    entries = tfnsw_speed_zones(bayside(), BOX, tmp_path, endpoint)

    assert [entry.name for entry in entries] == ["speed_zones.gpkg"]
    fields = entries[0].as_dict()
    assert all(fields[name] not in ("", 0, None) for name in fields)
    assert fields["licence"] == "CC BY 4.0"
    assert json.loads(fields["request"])["zones"] == CLUSTER


@pytest.mark.parametrize("code", [498, 499])
def test_fr10_9_a_key_error_names_the_sign_up_step(zone_server, tmp_path, code):
    endpoint, state = zone_server
    state["reply"] = {"error": {"code": code, "message": "Token Required", "details": []}}

    with pytest.raises(OverpassError, match="needs a key.*sign up"):
        tfnsw_speed_zones(bayside(), BOX, tmp_path, endpoint)


def untag_first_way(folder):
    path = folder / "network.osm.gz"
    text = gzip.decompress(path.read_bytes()).decode()
    way = re.search(r'<way id="2000">.*?</way>', text, re.S)
    stripped = re.sub(r'<tag k="maxspeed"[^>]*/>\n?', "", way[0])
    path.write_bytes(gzip.compress(text.replace(way[0], stripped).encode()))


def grid_with_zones(tmp_path, lines, speeds):
    folder = tmp_path / "snapshot"
    shutil.copytree(GRID, folder)
    untag_first_way(folder)
    origin = Transformer.from_crs(4326, 32756, always_xy=True).transform(151.15, -33.95)
    east0, north0 = round(origin[0]), round(origin[1])
    back = Transformer.from_crs(32756, 4326, always_xy=True)
    shifted = [
        LineString([back.transform(east0 + x, north0 + y) for x, y in line]) for line in lines
    ]
    frame = geopandas.GeoDataFrame(
        {
            "objectid": list(range(1, len(lines) + 1)),
            "type": ["Ordinary Permanent"] * len(lines),
            "direction": ["Both Directions"] * len(lines),
            "speed_kmh": speeds,
            "speed_source": ["zone"] * len(lines),
        },
        geometry=shifted,
        crs=4326,
    )
    frame.to_file(folder / "speed_zones.gpkg", driver="GPKG")
    return folder, east0, north0


def edges_at(graph, east0, north0, x_offset, low, high):
    return [
        data
        for u, v, data in graph.edges(data=True)
        if abs(graph.nodes[u]["x"] - east0 - x_offset) < 1
        and abs(graph.nodes[v]["x"] - east0 - x_offset) < 1
        and low <= graph.nodes[u]["y"] - north0 <= high
        and low <= graph.nodes[v]["y"] - north0 <= high
    ]


def build_grid(folder):
    return build(folder, load_region("regions/test-grid.yaml"), load_profile("au-nsw"))


def test_fr10_4_an_untagged_edge_takes_the_zone_speed(tmp_path):
    folder, east0, north0 = grid_with_zones(tmp_path, [[(5, -50), (5, 650)]], [40.0])

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 0, -1, 601)
    assert along
    for data in along:
        assert data["speed_kmh"] == 40.0
        assert data["speed_source"] == "zone"


def test_fr10_4_a_tagged_edge_keeps_its_tag(tmp_path):
    folder, east0, north0 = grid_with_zones(tmp_path, [[(205, -50), (205, 650)]], [40.0])

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 200, -1, 601)
    assert along
    for data in along:
        assert data["speed_kmh"] == 30.0
        assert data["speed_source"] == "tag"


def test_fr10_4_an_untagged_edge_with_no_zone_keeps_the_default(tmp_path):
    folder, east0, north0 = grid_with_zones(tmp_path, [[(405, -50), (405, 650)]], [40.0])

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 0, -1, 601)
    assert along
    assert all(d["speed_source"] == "default" for d in along)


def test_fr10_4_a_zone_at_a_right_angle_does_not_match(tmp_path):
    folder, east0, north0 = grid_with_zones(tmp_path, [[(-300, 100), (300, 100)]], [40.0])

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 0, -1, 201)
    assert along
    assert all(d["speed_source"] == "default" for d in along)


def test_fr10_4_a_zone_30_m_off_the_edge_does_not_match(tmp_path):
    folder, east0, north0 = grid_with_zones(tmp_path, [[(30, -50), (30, 650)]], [40.0])

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 0, -1, 601)
    assert all(d["speed_source"] == "default" for d in along)


def test_fr10_4_the_longest_overlap_wins_between_two_zones(tmp_path):
    folder, east0, north0 = grid_with_zones(
        tmp_path, [[(5, 0), (5, 110)], [(-5, 0), (-5, 200)]], [60.0, 30.0]
    )

    graph = build_grid(folder)

    edge = edges_at(graph, east0, north0, 0, -1, 201)
    assert edge
    assert all(d["speed_kmh"] == 30.0 and d["speed_source"] == "zone" for d in edge)


def test_fr10_9_without_zones_the_generic_path_keeps_every_default(tmp_path):
    folder = tmp_path / "snapshot"
    shutil.copytree(GRID, folder)
    untag_first_way(folder)

    graph = build_grid(folder)

    assert all(d["speed_source"] != "zone" for _, _, d in graph.edges(data=True))
    assert any(d["speed_source"] == "default" for _, _, d in graph.edges(data=True))
