import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
            content = response_body if status == 200 else b"temporary failure"
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
