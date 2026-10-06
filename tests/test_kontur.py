import gzip
import hashlib
import json
import math
import sqlite3
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from bikeplan.config import load_region
from bikeplan.snapshot import OverpassError, kontur_population

FIXTURES = Path("tests/fixtures/kontur")
SOURCE_HOST = "https://geodata-eu-central-1-kontur-public.s3.amazonaws.com"
LATEST = "/kontur_datasets/kontur_population_AU_20231101.gpkg.gz"
BOX = (-33.941, 151.1065, -33.919, 151.1335)
EARTH_RADIUS = 6378137


@pytest.fixture
def hdx_replay_server():
    state = {"requests": [], "statuses": [], "search": None}
    archive = (FIXTURES / "kontur_population_AU_20231101.gpkg.gz").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parts = urlsplit(self.path)
            state["requests"].append(
                {
                    "path": parts.path,
                    "query": parse_qs(parts.query),
                    "user_agent": self.headers.get("User-Agent"),
                }
            )
            base = f"http://127.0.0.1:{self.server.server_port}"
            status = state["statuses"].pop(0) if state["statuses"] else 200
            if status != 200:
                content = b"temporary failure"
            elif parts.path == "/api/3/action/package_search":
                text = state["search"] or (FIXTURES / "package_search_AU.json").read_text()
                content = text.replace(SOURCE_HOST, base).encode()
            elif parts.path == LATEST:
                content = archive
            else:
                status, content = 404, b"not found"
            self.send_response(status)
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
        yield f"http://127.0.0.1:{server.server_port}/api/3/action/package_search", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def mercator(lon, lat):
    x = EARTH_RADIUS * math.radians(lon)
    y = EARTH_RADIUS * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def source_rows():
    connection = sqlite3.connect(":memory:")
    database = gzip.decompress((FIXTURES / "kontur_population_AU_20231101.gpkg.gz").read_bytes())
    connection.deserialize(database)
    return connection.execute("select h3, population, geom from population").fetchall()


def hexagon_ring(blob):
    count = struct.unpack("<I", blob[49:53])[0]
    return [struct.unpack("<2d", blob[53 + 16 * index : 69 + 16 * index]) for index in range(count)]


def inside_ring(point, ring):
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def touching_hexagons():
    south, west, north, east = BOX
    min_x, min_y = mercator(west, south)
    max_x, max_y = mercator(east, north)
    corners = [(min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)]
    kept = set()
    for h3, _, blob in source_rows():
        ring = hexagon_ring(blob)
        vertex_in_box = any(min_x <= x <= max_x and min_y <= y <= max_y for x, y in ring)
        if vertex_in_box or any(inside_ring(corner, ring) for corner in corners):
            kept.add(h3)
    return kept


def bayside():
    return load_region("regions/au-nsw-bayside.yaml")


def cut_rows(path):
    connection = sqlite3.connect(path)
    return connection.execute("select h3, population from population").fetchall()


def test_fr2_8_cut_keeps_only_hexagons_that_touch_the_box(hdx_replay_server, tmp_path):
    endpoint, _ = hdx_replay_server
    expected = touching_hexagons()

    kontur_population(bayside(), BOX, tmp_path, endpoint)

    kept = {h3 for h3, _ in cut_rows(tmp_path / "population.gpkg")}
    assert 0 < len(expected) < len(source_rows())
    assert kept == expected


def test_fr2_8_cut_population_sum_matches_source_rows_kept(hdx_replay_server, tmp_path):
    endpoint, _ = hdx_replay_server

    kontur_population(bayside(), BOX, tmp_path, endpoint)

    rows = cut_rows(tmp_path / "population.gpkg")
    kept = {h3 for h3, _ in rows}
    source = sum(population for h3, population, _ in source_rows() if h3 in kept)
    assert len(rows) == len(kept)
    assert sum(population for _, population in rows) == source
    assert source > 0


def test_fr2_8_cut_is_a_geopackage_with_a_population_column(hdx_replay_server, tmp_path):
    endpoint, _ = hdx_replay_server

    kontur_population(bayside(), BOX, tmp_path, endpoint)

    connection = sqlite3.connect(tmp_path / "population.gpkg")
    assert connection.execute("pragma application_id").fetchone()[0] == 0x47504B47
    contents = connection.execute("select table_name, data_type, srs_id from gpkg_contents")
    assert contents.fetchall() == [("population", "features", 3857)]
    geometry = connection.execute("select table_name, column_name from gpkg_geometry_columns")
    assert geometry.fetchall() == [("population", "geom")]
    columns = [row[1] for row in connection.execute("pragma table_info(population)")]
    assert "population" in columns
    blobs = [row[0] for row in connection.execute("select geom from population")]
    assert all(blob[:2] == b"GP" for blob in blobs)


def test_fr2_8_adapter_finds_the_country_dataset_and_its_latest_geopackage(
    hdx_replay_server, tmp_path
):
    endpoint, state = hdx_replay_server

    entries = kontur_population(bayside(), BOX, tmp_path, endpoint)

    search = state["requests"][0]
    assert search["path"] == "/api/3/action/package_search"
    assert "kontur_population_AU_" in search["query"]["fq"][0]
    assert [request["path"] for request in state["requests"][1:]] == [LATEST]
    [entry] = entries
    content = (tmp_path / "population.gpkg").read_bytes()
    assert entry.name == "population.gpkg"
    assert entry.path == "population.gpkg"
    assert entry.sha256 == hashlib.sha256(content).hexdigest()
    assert entry.bytes == len(content)
    assert entry.url.endswith(LATEST)
    assert "kontur-population-australia" in entry.request
    assert entry.licence == "CC BY 4.0"
    assert "Kontur" in entry.attribution
    assert entry.retrieved_at.endswith("Z")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["population.gpkg"]


def test_fr2_8_country_without_a_dataset_fails_the_fetch(hdx_replay_server, tmp_path):
    endpoint, state = hdx_replay_server
    state["search"] = json.dumps({"success": True, "result": {"count": 0, "results": []}})

    with pytest.raises(OverpassError):
        kontur_population(bayside(), BOX, tmp_path, endpoint)

    assert list(tmp_path.iterdir()) == []


def test_fr2_8_snapshot_fetch_runs_the_kontur_population_adapter(
    hdx_replay_server, tmp_path, monkeypatch
):
    from bikeplan.snapshot import ADAPTERS

    endpoint, _ = hdx_replay_server
    monkeypatch.setattr("bikeplan.snapshot.HDX_ENDPOINT", endpoint)

    entries = ADAPTERS["kontur_population"](bayside(), BOX, tmp_path)

    assert [entry.name for entry in entries] == ["population.gpkg"]
    assert (tmp_path / "population.gpkg").exists()


def test_fr2_4_hdx_requests_retry_twice_then_succeed(hdx_replay_server, tmp_path, monkeypatch):
    endpoint, state = hdx_replay_server
    state["statuses"] = [503, 503]
    monkeypatch.setattr("bikeplan.snapshot.time.sleep", lambda seconds: None)

    kontur_population(bayside(), BOX, tmp_path, endpoint)

    assert len(state["requests"]) == 4
    assert (tmp_path / "population.gpkg").exists()


def test_fr2_4_hdx_download_fails_after_three_retries(hdx_replay_server, tmp_path, monkeypatch):
    endpoint, state = hdx_replay_server
    state["statuses"] = [200, 503, 503, 503, 503]
    monkeypatch.setattr("bikeplan.snapshot.time.sleep", lambda seconds: None)

    with pytest.raises(OverpassError):
        kontur_population(bayside(), BOX, tmp_path, endpoint)

    assert len(state["requests"]) == 5
    assert list(tmp_path.iterdir()) == []


def test_fr2_10_hdx_requests_send_project_and_contact(hdx_replay_server, tmp_path):
    endpoint, state = hdx_replay_server

    kontur_population(bayside(), BOX, tmp_path, endpoint)

    for request in state["requests"]:
        assert "bikeplan" in request["user_agent"].lower()
        assert "contact:" in request["user_agent"].lower()
