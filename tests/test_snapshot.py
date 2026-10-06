import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs

import pytest

from bikeplan.snapshot import OverpassClient, OverpassError


@pytest.fixture
def overpass_replay_server():
    state = {"requests": [], "statuses": []}
    response_body = b'{"elements":[]}'

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            form = parse_qs(body.decode())
            state["requests"].append(
                {"query": form["data"][0], "user_agent": self.headers.get("User-Agent")}
            )
            status = state["statuses"].pop(0) if state["statuses"] else 200
            content = state.get("body", response_body) if status == 200 else b"temporary failure"
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
        yield f"http://127.0.0.1:{server.server_port}/api/interpreter", state, response_body
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def fetch(client, output):
    return client.fetch(
        "[out:json];node(1);out;",
        "2026-10-01T00:00:00Z",
        output,
        licence="ODbL 1.0",
        attribution="© OpenStreetMap contributors",
    )


def test_fr2_2_overpass_query_pins_date_and_manifest_request(overpass_replay_server, tmp_path):
    endpoint, state, _ = overpass_replay_server
    output = tmp_path / "network.json"
    client = OverpassClient(endpoint)
    entry = fetch(client, output)

    expected = '[out:json][date:"2026-10-01T00:00:00Z"];node(1);out;'
    assert state["requests"][0]["query"] == expected
    assert entry.request == expected


def test_fr2_4_overpass_request_retries_twice_then_succeeds(overpass_replay_server, tmp_path):
    endpoint, state, response_body = overpass_replay_server
    state["statuses"] = [503, 503, 200]
    output = tmp_path / "network.json"
    client = OverpassClient(endpoint)
    entry = fetch(client, output)

    assert len(state["requests"]) == 3
    assert output.read_bytes() == response_body
    assert entry.sha256


def test_fr2_4_overpass_retries_use_growing_waits(overpass_replay_server, tmp_path, monkeypatch):
    endpoint, state, _ = overpass_replay_server
    state["statuses"] = [503, 503, 503, 200]
    waits = []
    monkeypatch.setattr("bikeplan.snapshot.time.sleep", waits.append)
    client = OverpassClient(endpoint)

    fetch(client, tmp_path / "network.json")

    assert len(state["requests"]) == 4
    assert waits == [0.1, 0.2, 0.4]


def test_fr2_4_overpass_request_fails_after_three_retries(overpass_replay_server, tmp_path):
    endpoint, state, _ = overpass_replay_server
    state["statuses"] = [503, 503, 503, 503]
    output = tmp_path / "network.json"
    client = OverpassClient(endpoint)
    with pytest.raises(OverpassError):
        fetch(client, output)

    assert len(state["requests"]) == 4
    assert not output.exists()


def test_fr2_10_overpass_request_sends_project_and_contact(overpass_replay_server, tmp_path):
    endpoint, state, _ = overpass_replay_server
    client = OverpassClient(endpoint)
    fetch(client, tmp_path / "network.json")

    user_agent = state["requests"][0]["user_agent"]
    assert "bikeplan" in user_agent.lower()
    assert "contact:" in user_agent.lower()


def test_nfr4_snapshot_manifest_entry_has_source_metadata_and_digest(
    overpass_replay_server, tmp_path
):
    endpoint, _, response_body = overpass_replay_server
    output = tmp_path / "network.json"
    client = OverpassClient(endpoint)
    entry = fetch(client, output).as_dict()

    assert entry["url"] == endpoint
    assert entry["licence"] == "ODbL 1.0"
    assert entry["retrieved_at"].endswith("Z")
    assert entry["sha256"] == hashlib.sha256(response_body).hexdigest()
    assert entry["bytes"] == len(response_body)


def relation_response(members):
    return {
        "elements": [
            {
                "type": "relation",
                "id": 42,
                "members": [
                    {
                        "type": "way",
                        "role": role,
                        "geometry": [{"lat": lat, "lon": lon} for lon, lat in points],
                    }
                    for role, points in members
                ],
            }
        ]
    }


SQUARE_HALVES = [
    ("outer", [(0, 0), (4, 0), (4, 4)]),
    ("outer", [(4, 4), (0, 4), (0, 0)]),
]


def test_fr2_3_closed_relation_becomes_one_polygon():
    from bikeplan.snapshot import boundary_geojson

    geometry = boundary_geojson(relation_response(SQUARE_HALVES))["geometry"]

    assert geometry["type"] == "Polygon"
    ring = geometry["coordinates"][0]
    assert ring[0] == ring[-1]
    assert {tuple(point) for point in ring} == {(0, 0), (4, 0), (4, 4), (0, 4)}


def test_fr2_3_reversed_ways_still_close_into_one_ring():
    from bikeplan.snapshot import boundary_geojson

    members = [SQUARE_HALVES[0], ("outer", [(0, 0), (0, 4), (4, 4)])]
    geometry = boundary_geojson(relation_response(members))["geometry"]

    assert geometry["type"] == "Polygon"
    assert len(geometry["coordinates"][0]) == 5


def test_fr2_3_two_outer_rings_become_a_multipolygon():
    from bikeplan.snapshot import boundary_geojson

    far = ("outer", [(10, 10), (12, 10), (12, 12), (10, 12), (10, 10)])
    geometry = boundary_geojson(relation_response([*SQUARE_HALVES, far]))["geometry"]

    assert geometry["type"] == "MultiPolygon"
    assert len(geometry["coordinates"]) == 2


def test_fr2_3_inner_ring_becomes_a_hole_of_its_outer_ring():
    from bikeplan.snapshot import boundary_geojson

    hole = ("inner", [(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)])
    geometry = boundary_geojson(relation_response([*SQUARE_HALVES, hole]))["geometry"]

    assert geometry["type"] == "Polygon"
    assert len(geometry["coordinates"]) == 2


def test_fr2_3_open_relation_fails_the_fetch():
    from bikeplan.snapshot import boundary_geojson

    with pytest.raises(OverpassError):
        boundary_geojson(relation_response([SQUARE_HALVES[0]]))


def test_fr2_3_missing_relation_fails_the_fetch():
    from bikeplan.snapshot import boundary_geojson

    with pytest.raises(OverpassError):
        boundary_geojson({"elements": []})


def test_fr2_3_boundary_fetch_asks_for_the_relation_at_the_pinned_date(
    overpass_replay_server, tmp_path
):
    import json

    from bikeplan.snapshot import fetch_boundary

    endpoint, state, _ = overpass_replay_server
    state["body"] = json.dumps(relation_response(SQUARE_HALVES)).encode()
    output = tmp_path / "boundary.geojson"

    entry = fetch_boundary(OverpassClient(endpoint), 42, "2026-10-01T00:00:00Z", output)

    assert "relation(42)" in state["requests"][0]["query"]
    assert '[date:"2026-10-01T00:00:00Z"]' in state["requests"][0]["query"]
    assert json.loads(output.read_text())["geometry"]["type"] == "Polygon"
    assert entry.request == state["requests"][0]["query"]


def test_fr2_3_open_boundary_fetch_leaves_no_file(overpass_replay_server, tmp_path):
    import json

    from bikeplan.snapshot import fetch_boundary

    endpoint, state, _ = overpass_replay_server
    state["body"] = json.dumps(relation_response([SQUARE_HALVES[0]])).encode()
    output = tmp_path / "boundary.geojson"

    with pytest.raises(OverpassError):
        fetch_boundary(OverpassClient(endpoint), 42, "2026-10-01T00:00:00Z", output)

    assert not output.exists()


BOX = (-34.0, 151.0, -33.9, 151.1)


def test_fr2_1_network_query_lists_every_highway_value_and_crossing_nodes():
    from bikeplan.snapshot import network_query

    query = network_query(BOX)

    for value in (
        "primary_link",
        "tertiary_link",
        "unclassified",
        "residential",
        "living_street",
        "service",
        "cycleway",
        "path",
        "footway",
        "pedestrian",
        "track",
        "bridleway",
        "steps",
        "trunk",
        "trunk_link",
    ):
        assert value in query
    assert '"highway"="traffic_signals"' in query
    assert '"highway"="crossing"' in query
    assert '["crossing"]' in query
    assert "-34.0,151.0,-33.9,151.1" in query


def test_fr7_10_places_query_holds_every_place_tag_shop_and_out_center_tags():
    from bikeplan.snapshot import places_query

    query = places_query(BOX)

    for tag in (
        "amenity=school",
        "amenity=college",
        "amenity=university",
        "amenity=nursing_home",
        "amenity=social_facility",
        "amenity=library",
        "railway=station",
        "railway=halt",
        "public_transport=station",
        "amenity=ferry_terminal",
        "railway=tram_stop",
    ):
        assert tag.replace("=", '"="') in query
    assert '["shop"]' in query
    assert "out center tags" in query
    assert "-34.0,151.0,-33.9,151.1" in query
    assert query.count("nwr[") == 12


def test_fr7_10_places_query_keeps_the_date_line_when_fetched(overpass_replay_server, tmp_path):
    from bikeplan.snapshot import places_query

    endpoint, state, _ = overpass_replay_server
    fetch_client = OverpassClient(endpoint)
    fetch_client.fetch(
        places_query(BOX),
        "2026-10-01T00:00:00Z",
        tmp_path / "places.json",
        licence="ODbL 1.0",
        attribution="© OpenStreetMap contributors",
    )

    sent = state["requests"][0]["query"]
    assert sent.startswith("[out:json][timeout:")
    assert '[date:"2026-10-01T00:00:00Z"]' in sent
    assert "out center tags" in sent


NETWORK_XML = b'<?xml version="1.0"?><osm version="0.6"><node id="1" lat="0" lon="0"/></osm>'
PLACES_JSON = b'{"elements":[{"type":"node","id":7,"lat":1,"lon":1,"tags":{"amenity":"school"}}]}'


@pytest.fixture
def routed_overpass_server():
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from urllib.parse import parse_qs

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            query = parse_qs(body.decode())["data"][0]
            requests.append(query)
            if "relation(" in query:
                content = json.dumps(relation_response(SQUARE_HALVES)).encode()
            elif "[out:xml]" in query:
                content = NETWORK_XML
            else:
                content = PLACES_JSON
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
        yield f"http://127.0.0.1:{server.server_port}/api/interpreter", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def bayside_without_adapters(tmp_path, adapters="[]"):
    text = Path("regions/au-nsw-bayside.yaml").read_text()
    text = text.replace("adapters: [kontur_population]", f"adapters: {adapters}")
    path = tmp_path / "region.yaml"
    path.write_text(text)
    return path


def test_fr2_1_snapshot_fetch_writes_every_file_and_the_manifest(routed_overpass_server, tmp_path):
    import gzip
    import json

    from bikeplan import main

    endpoint, _ = routed_overpass_server
    out = tmp_path / "snap"
    region = bayside_without_adapters(tmp_path)

    code = main(["snapshot", "fetch", str(region), "--out", str(out), "--endpoint", endpoint])

    assert code == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["region"] == "au-nsw-bayside"
    assert manifest["snapshot_id"] == "2026-10-01"
    assert manifest["osm_date"] == "2026-10-01T00:00:00Z"
    assert manifest["config_hash"]
    assert manifest["created_at"].endswith("Z")
    names = [entry["name"] for entry in manifest["files"]]
    assert names == ["boundary.geojson", "network.osm.gz", "places.json"]
    assert gzip.decompress((out / "network.osm.gz").read_bytes()) == NETWORK_XML
    assert (out / "places.json").read_bytes() == PLACES_JSON
    assert json.loads((out / "boundary.geojson").read_text())["geometry"]["type"] == "Polygon"
    for entry in manifest["files"]:
        content = (out / entry["path"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        assert entry["bytes"] == len(content)
        assert entry["request"].startswith("[out:")
        assert entry["licence"]
        assert entry["attribution"]
        assert entry["retrieved_at"].endswith("Z")


def test_fr2_1_snapshot_fetch_queries_the_box_grown_by_the_buffer(routed_overpass_server, tmp_path):
    from bikeplan import main

    endpoint, requests = routed_overpass_server
    region = bayside_without_adapters(tmp_path)

    main(
        ["snapshot", "fetch", str(region), "--out", str(tmp_path / "snap"), "--endpoint", endpoint]
    )

    network = next(query for query in requests if "[out:xml]" in query)
    places = next(query for query in requests if "out center" in query)
    for query in (network, places):
        south, west, north, east = (
            float(value) for value in query.rsplit("(", 1)[1].split(")")[0].split(",")
        )
        assert south == pytest.approx(-2680 / 111320, abs=1e-5)
        assert north == pytest.approx(4 + 2680 / 111320, abs=1e-5)
        assert west == pytest.approx(-2680 / 111320, abs=1e-3)
        assert east == pytest.approx(4 + 2680 / 111320, abs=1e-3)


def test_fr2_1_snapshot_fetch_fails_on_an_adapter_it_cannot_run(routed_overpass_server, tmp_path):
    from bikeplan import main

    endpoint, _ = routed_overpass_server
    out = tmp_path / "snap"
    region = bayside_without_adapters(tmp_path, "[no_such_adapter]")

    code = main(["snapshot", "fetch", str(region), "--out", str(out), "--endpoint", endpoint])

    assert code != 0
    assert not (out / "manifest.json").exists()
