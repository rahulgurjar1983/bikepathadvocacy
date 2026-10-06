import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from bikeplan.snapshot import OverpassClient, fetch_boundary, network_query, places_query

RELATION = {
    "elements": [
        {
            "type": "relation",
            "id": 42,
            "members": [
                {
                    "type": "way",
                    "role": "outer",
                    "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 4}, {"lat": 4, "lon": 4}],
                },
                {
                    "type": "way",
                    "role": "outer",
                    "geometry": [{"lat": 4, "lon": 4}, {"lat": 4, "lon": 0}, {"lat": 0, "lon": 0}],
                },
            ],
        }
    ]
}
BOX = (-34.0, 151.0, -33.9, 151.1)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        body = json.dumps(RELATION).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    output_dir = Path("artifacts/P2.2")
    output_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = OverpassClient(f"http://127.0.0.1:{server.server_port}/api/interpreter")
        entry = fetch_boundary(client, 42, "2026-10-01T00:00:00Z", output_dir / "boundary.geojson")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    (output_dir / "boundary-entry.json").write_text(
        json.dumps(entry.as_dict(), indent=2, sort_keys=True) + "\n"
    )
    (output_dir / "network.query").write_text(network_query(BOX) + "\n")
    (output_dir / "places.query").write_text(places_query(BOX) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
