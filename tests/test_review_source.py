import hashlib
import json
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import yaml

from bikeplan import main


@pytest.fixture
def source_server():
    body = b'<html><script>const routes={"type":"FeatureCollection","features":[]};</script></html>'
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.headers.get("User-Agent"))
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", body, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def fetch_args(url, out):
    return [
        "snapshot",
        "review-source",
        url,
        "--out",
        str(out),
        "--licence",
        "CC BY 4.0",
        "--credit",
        "Test plan author",
    ]


def test_fr18_7_snapshot_saves_exact_source_with_credit_date_and_hash(
    tmp_path, monkeypatch, source_server
):
    monkeypatch.chdir(tmp_path)
    url, body, requests = source_server
    out = tmp_path / "data/private/plan"
    assert main(fetch_args(url, out)) == 0
    assert (out / "source").read_bytes() == body
    manifest = json.loads((out / "source-manifest.json").read_text())
    assert manifest["url"] == url
    assert manifest["licence"] == "CC BY 4.0"
    assert manifest["attribution"] == "Test plan author"
    assert manifest["sha256"] == hashlib.sha256(body).hexdigest()
    assert manifest["bytes"] == len(body)
    assert manifest["path"] == "source"
    assert datetime.fromisoformat(manifest["retrieved_at"]).utcoffset().total_seconds() == 0
    assert requests and "bikeplan/" in requests[0]
    assert yaml.safe_load((out / "review.yaml").read_text()) == {"public": False}


def test_fr18_7_source_capture_refuses_to_replace_a_saved_review(
    tmp_path, monkeypatch, source_server, capsys
):
    monkeypatch.chdir(tmp_path)
    url, body, requests = source_server
    out = tmp_path / "data/private/plan"
    assert main(fetch_args(url, out)) == 0
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert main(fetch_args(url, out)) == 1
    assert "exists" in capsys.readouterr().err
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
    assert len(requests) == 1
    assert (out / "source").read_bytes() == body


@pytest.mark.parametrize("escape", ["plain", "dotdot", "symlink"])
def test_fr14_12_source_capture_rejects_public_paths_before_fetch(
    tmp_path, monkeypatch, source_server, capsys, escape
):
    monkeypatch.chdir(tmp_path)
    url, _, requests = source_server
    root = tmp_path / "data/private"
    root.mkdir(parents=True)
    outside = tmp_path / "public"
    if escape == "symlink":
        alias = root / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        out = alias / "public"
    elif escape == "dotdot":
        out = root / "../../public"
    else:
        out = outside
    assert main(fetch_args(url, out)) == 1
    assert "data/private" in capsys.readouterr().err
    assert requests == []
    assert not outside.exists()


def test_fr14_12_captured_source_and_settings_stay_out_of_git(tmp_path, monkeypatch, source_server):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / ".gitignore").write_text("data/private/\n")
    url, _, _ = source_server
    out = tmp_path / "data/private/plan"
    assert main(fetch_args(url, out)) == 0
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "data/private"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
    ignored = subprocess.run(
        ["git", "check-ignore", "data/private/plan/source", "data/private/plan/review.yaml"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert ignored.stdout.splitlines() == [
        "data/private/plan/source",
        "data/private/plan/review.yaml",
    ]
