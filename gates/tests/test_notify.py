import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]


def notify(home: Path, *args: str, **extra: str):
    env = dict(os.environ, HOME=str(home), **extra)
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / "notify.sh"), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def write_config(home: Path) -> None:
    config = home / ".config" / "bikepathadvocacy"
    config.mkdir(parents=True)
    (config / "telegram.json").write_text(json.dumps({"botToken": "t0k", "chatId": "42"}))


class Recorder(BaseHTTPRequestHandler):
    seen: ClassVar[list] = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        Recorder.seen.append((self.path, parse_qs(body)))
        payload = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        return None


def test_fr0_19_dry_run_prints_the_note(tmp_path):
    result = notify(tmp_path, "row P0.1 merged", NOTIFY_DRY_RUN="1")
    assert result.returncode == 0
    assert "row P0.1 merged" in result.stdout


def test_fr0_19_missing_config_fails(tmp_path):
    result = notify(tmp_path, "hello")
    assert result.returncode != 0
    assert "telegram.json" in result.stderr


def test_fr0_19_sends_the_note_to_the_bot_api(tmp_path):
    write_config(tmp_path)
    Recorder.seen = []
    server = HTTPServer(("127.0.0.1", 0), Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        api = f"http://127.0.0.1:{server.server_address[1]}"
        result = notify(tmp_path, "row P0.1 merged", NOTIFY_API=api)
    finally:
        server.shutdown()
    assert result.returncode == 0, result.stdout + result.stderr
    path, form = Recorder.seen[0]
    assert path == "/bott0k/sendMessage"
    assert form["chat_id"] == ["42"]
    assert "row P0.1 merged" in form["text"][0]


def test_fr0_19_api_failure_exits_non_zero(tmp_path):
    write_config(tmp_path)
    result = notify(tmp_path, "hello", NOTIFY_API="http://127.0.0.1:9")
    assert result.returncode != 0
    assert "notify: send failed" in result.stderr
    assert "t0k" not in result.stdout + result.stderr
