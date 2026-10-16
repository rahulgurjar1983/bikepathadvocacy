import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from bikeplan import main
from bikeplan.config import load_region


def match(osm_type, osm_id, name, level, country, state_code, state):
    return {
        "osm_type": osm_type,
        "osm_id": osm_id,
        "category": "boundary",
        "name": name,
        "display_name": f"{name}, {state}",
        "address": {
            "state": state,
            "ISO3166-2-lvl4": state_code,
            "country_code": country.lower(),
        },
        "extratags": {"admin_level": str(level)},
    }


REPLY = [
    match("node", 5, "Bayside", 8, "AU", "AU-NSW", "New South Wales"),
    match("relation", 7038238, "Bayside Council", 6, "AU", "AU-NSW", "New South Wales"),
    match("relation", 295355, "Cambridge", 8, "GB", "GB-CAM", "Cambridgeshire"),
    match("relation", 1, "New South Wales", 4, "AU", "AU-NSW", "Australia"),
]


@pytest.fixture
def nominatim():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            seen.append({"q": query["q"][0], "user_agent": self.headers.get("User-Agent")})
            body = json.dumps(REPLY).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/search", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def new(endpoint, tmp_path, *extra):
    return main(
        ["region", "new", "Bayside", "--endpoint", endpoint, "--out", str(tmp_path / "out"), *extra]
    )


def test_fr1_11_lists_council_and_city_matches_with_admin_level(nominatim, tmp_path, capsys):
    endpoint, seen = nominatim
    assert new(endpoint, tmp_path) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("1.") and "Bayside Council" in lines[0]
    assert "admin level 6" in lines[0] and "7038238" in lines[0]
    assert lines[1].startswith("2.") and "Cambridge" in lines[1]
    assert "admin level 8" in lines[1]
    assert seen[0]["q"] == "Bayside"


def test_fr1_11_without_pick_writes_nothing(nominatim, tmp_path):
    endpoint, _ = nominatim
    new(endpoint, tmp_path)
    assert not (tmp_path / "out").exists()


def test_fr1_11_requests_carry_the_project_user_agent(nominatim, tmp_path):
    endpoint, seen = nominatim
    new(endpoint, tmp_path)
    assert seen[0]["user_agent"].startswith("bikeplan/")
    assert "contact:" in seen[0]["user_agent"]


def test_fr1_11_pick_writes_a_region_that_loads_with_the_country_profile(nominatim, tmp_path):
    endpoint, _ = nominatim
    assert new(endpoint, tmp_path, "--pick", "1") == 0
    found = load_region(tmp_path / "out" / "au-nsw-bayside.yaml")
    assert found.id == "au-nsw-bayside"
    assert found.name == "Bayside Council, New South Wales"
    assert found.boundary.osm_relation == 7038238
    assert found.country == "AU"
    assert found.subdivision == "AU-NSW"
    assert found.profile == "au-nsw"
    assert found.report.author is None


def test_fr1_11_a_country_with_no_profile_gets_generic(nominatim, tmp_path):
    endpoint, _ = nominatim
    assert new(endpoint, tmp_path, "--pick", "2") == 0
    found = load_region(tmp_path / "out" / "gb-cam-cambridge.yaml")
    assert found.profile == "generic"
    assert found.boundary.osm_relation == 295355
    assert found.snapshot.adapters == ["kontur_population"]


def test_fr1_11_pick_out_of_range_is_refused_and_writes_nothing(nominatim, tmp_path, capsys):
    endpoint, _ = nominatim
    assert new(endpoint, tmp_path, "--pick", "3") == 1
    assert "pick" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_fr1_11_like_copies_every_setting_but_the_place(nominatim, tmp_path):
    endpoint, _ = nominatim
    like = Path("regions/au-nsw-bayside.yaml")
    assert new(endpoint, tmp_path, "--pick", "2", "--like", str(like), "--id", "x-y") == 0
    made = yaml.safe_load((tmp_path / "out" / "x-y.yaml").read_text())
    base = yaml.safe_load(like.read_text())
    for key in ("id", "name", "boundary", "country", "subdivision"):
        made.pop(key)
        base.pop(key)
    assert made == base


def test_fr1_11_an_existing_file_is_not_overwritten(nominatim, tmp_path, capsys):
    endpoint, _ = nominatim
    new(endpoint, tmp_path, "--pick", "1")
    target = tmp_path / "out" / "au-nsw-bayside.yaml"
    target.write_text("keep")
    assert new(endpoint, tmp_path, "--pick", "1") == 1
    assert target.read_text() == "keep"
    assert "exists" in capsys.readouterr().err
