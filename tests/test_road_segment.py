import json
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import geopandas
import pytest
from bikeplan.adapters.nsw_road_segment import nsw_road_segment
from pyproj import Transformer
from shapely.geometry import LineString

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.snapshot import ADAPTERS, OverpassError

BOX = (-33.941, 151.1065, -33.919, 151.1335)
LIMIT = 2000
CLUSTER = 2500
GRID = Path("tests/fixtures/test-grid/snapshot")
FUNCTIONS = {
    "PrimaryRoad",
    "ArterialRoad",
    "DistributorRoad",
    "LocalRoad",
    "UrbanServiceLane",
    "AccessWay",
}


def pieces(count):
    found = []
    for index in range(count):
        west = 151.1070 + (index % 50) * 0.00004
        south = -33.9400 + (index // 50) * 0.00004
        found.append((index + 1, [(west, south), (west + 0.00002, south + 0.00002)]))
    return found


@pytest.fixture
def segment_server():
    state = {"requests": [], "lines": pieces(CLUSTER), "reply": None}

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
                            "functionhi": "5",
                            "function": "DistributorRoad",
                            "lanecount": "2",
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
        yield f"http://127.0.0.1:{server.server_port}/MapServer/0", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def bayside():
    return load_region("regions/au-nsw-bayside.yaml")


def test_fr10_3_full_tile_is_split_and_every_segment_is_stored(segment_server, tmp_path):
    endpoint, state = segment_server

    nsw_road_segment(bayside(), BOX, tmp_path, endpoint)

    stored = geopandas.read_file(tmp_path / "road_segments.gpkg")
    assert len(stored) == CLUSTER
    assert stored["objectid"].is_unique
    widths = {
        round(
            float(r["query"]["geometry"][0].split(",")[2])
            - float(r["query"]["geometry"][0].split(",")[0]),
            6,
        )
        for r in state["requests"]
    }
    assert len(widths) > 1
    assert all(r["path"].endswith("/MapServer/0/query") for r in state["requests"])


def test_fr10_3_segments_keep_function_level_and_lane_count_as_lines_in_degrees(
    segment_server, tmp_path
):
    endpoint, state = segment_server
    state["lines"] = pieces(10)

    nsw_road_segment(bayside(), BOX, tmp_path, endpoint)

    stored = geopandas.read_file(tmp_path / "road_segments.gpkg")
    assert len(stored) == 10
    assert len(state["requests"]) == 9
    assert stored.crs.to_epsg() == 4326
    assert set(stored.geometry.geom_type) == {"LineString"}
    assert not stored.geometry.has_z.any()
    assert set(stored["function"]) == {"DistributorRoad"}
    assert set(stored["functionhi"]) == {"5"}
    assert set(stored["lanecount"]) == {"2"}


def test_fr10_3_adapter_is_registered():
    assert ADAPTERS["nsw_road_segment"] is nsw_road_segment


def test_fr10_8_road_segment_service_error_fails_the_snapshot(segment_server, tmp_path):
    endpoint, state = segment_server
    state["reply"] = {"error": {"code": 500, "message": "boom", "details": []}}

    with pytest.raises(OverpassError, match="boom"):
        nsw_road_segment(bayside(), BOX, tmp_path, endpoint)


def test_fr10_8_road_segment_manifest_entry_has_every_field(segment_server, tmp_path):
    endpoint, _ = segment_server

    entries = nsw_road_segment(bayside(), BOX, tmp_path, endpoint)

    assert [entry.name for entry in entries] == ["road_segments.gpkg"]
    fields = entries[0].as_dict()
    assert all(fields[name] not in ("", 0, None) for name in fields)
    assert fields["licence"] == "CC BY 4.0"
    assert json.loads(fields["request"])["segments"] == CLUSTER


def test_fr10_3_profile_maps_every_function_to_a_sourced_adt():
    profile = load_profile("au-nsw")

    assert set(profile.road_functions) == FUNCTIONS
    assert all(item.value > 0 and item.source for item in profile.road_functions.values())
    assert profile.road_functions["PrimaryRoad"].value > profile.road_functions["LocalRoad"].value


def test_fr10_3_generic_profile_has_no_function_map():
    assert load_profile("generic").road_functions == {}


def grid_with_segments(tmp_path, lines, functions):
    folder = tmp_path / "snapshot"
    shutil.copytree(GRID, folder)
    origin = Transformer.from_crs(4326, 32756, always_xy=True).transform(151.15, -33.95)
    east0, north0 = round(origin[0]), round(origin[1])
    back = Transformer.from_crs(32756, 4326, always_xy=True)
    shifted = [
        LineString([back.transform(east0 + x, north0 + y) for x, y in line]) for line in lines
    ]
    frame = geopandas.GeoDataFrame(
        {
            "objectid": list(range(1, len(lines) + 1)),
            "functionhi": ["5"] * len(lines),
            "function": functions,
            "lanecount": ["2"] * len(lines),
        },
        geometry=shifted,
        crs=4326,
    )
    frame.to_file(folder / "road_segments.gpkg", driver="GPKG")
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


def test_fr10_3_matched_edge_takes_the_function_adt_and_source(tmp_path):
    profile = load_profile("au-nsw")
    folder, east0, north0 = grid_with_segments(tmp_path, [[(5, -50), (5, 650)]], ["ArterialRoad"])

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 0, -1, 601)
    assert along
    for data in along:
        assert data["adt"] == profile.road_functions["ArterialRoad"].value
        assert data["adt_source"] == "nsw_road_segment"
        assert data["road_function"] == "ArterialRoad"


def test_fr10_3_edges_with_no_segment_keep_the_class_default(tmp_path):
    folder, east0, north0 = grid_with_segments(tmp_path, [[(5, -50), (5, 650)]], ["ArterialRoad"])

    graph = build_grid(folder)

    far = edges_at(graph, east0, north0, 400, -1, 601)
    assert far
    assert all(d["adt_source"] == "default" and d["adt"] == 750 for d in far)


def test_fr10_3_a_segment_at_a_right_angle_does_not_match(tmp_path):
    folder, east0, north0 = grid_with_segments(
        tmp_path, [[(-300, 100), (300, 100)]], ["ArterialRoad"]
    )

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 0, -1, 201)
    assert along
    assert all(d["adt_source"] == "default" for d in along)


def test_fr10_3_a_segment_30_m_off_the_edge_does_not_match(tmp_path):
    folder, east0, north0 = grid_with_segments(tmp_path, [[(30, -50), (30, 650)]], ["ArterialRoad"])

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 0, -1, 601)
    assert all(d["adt_source"] == "default" for d in along)


def test_fr10_3_a_segment_over_less_than_half_the_edge_does_not_match(tmp_path):
    folder, east0, north0 = grid_with_segments(tmp_path, [[(5, 0), (5, 80)]], ["ArterialRoad"])

    graph = build_grid(folder)

    edge = edges_at(graph, east0, north0, 0, -1, 201)
    assert edge
    assert all(d["adt_source"] == "default" for d in edge)


def test_fr10_3_a_segment_over_more_than_half_the_edge_matches(tmp_path):
    folder, east0, north0 = grid_with_segments(tmp_path, [[(5, 0), (5, 120)]], ["LocalRoad"])

    graph = build_grid(folder)

    edge = edges_at(graph, east0, north0, 0, -1, 201)
    assert edge
    assert all(d["adt_source"] == "nsw_road_segment" for d in edge)


def test_fr10_3_the_longest_overlap_wins_between_two_segments(tmp_path):
    folder, east0, north0 = grid_with_segments(
        tmp_path,
        [[(5, 0), (5, 110)], [(-5, 0), (-5, 200)]],
        ["PrimaryRoad", "LocalRoad"],
    )
    profile = load_profile("au-nsw")

    graph = build_grid(folder)

    edge = edges_at(graph, east0, north0, 0, -1, 201)
    assert edge
    assert all(d["adt"] == profile.road_functions["LocalRoad"].value for d in edge)


def test_fr10_3_an_unmapped_function_keeps_the_default(tmp_path):
    folder, east0, north0 = grid_with_segments(
        tmp_path, [[(5, -50), (5, 650)]], ["DedicatedBusWay"]
    )

    graph = build_grid(folder)

    along = edges_at(graph, east0, north0, 0, -1, 601)
    assert all(d["adt_source"] == "default" and d["adt"] == 750 for d in along)


def test_fr10_3_snapshot_without_segments_keeps_every_default():
    graph = build_grid(GRID)

    assert all(d["adt_source"] == "default" for _, _, d in graph.edges(data=True))
