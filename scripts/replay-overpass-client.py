import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from bikeplan.snapshot import OverpassClient


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        body = b'{"elements":[]}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    output_dir = Path("artifacts/P2.1")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "overpass.json"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = OverpassClient(f"http://127.0.0.1:{server.server_port}/api/interpreter")
        entry = client.fetch(
            "[out:json];node(1);out;",
            "2026-10-01T00:00:00Z",
            output,
            licence="ODbL 1.0",
            attribution="© OpenStreetMap contributors",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    manifest = output_dir / "manifest-entry.json"
    manifest.write_text(json.dumps(entry.as_dict(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
