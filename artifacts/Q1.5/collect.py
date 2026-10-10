import csv
import hashlib
import json
import subprocess
from pathlib import Path

import gpxpy.gpx
from pyproj import Transformer

from bikeplan.access import edge_table, last_legs, reach, safe_reach, scene
from bikeplan.config import config_hash, load_profile, load_region
from bikeplan.network import build
from bikeplan.propose import confirmed_planning, planning_network
from bikeplan.stress import score_edges

root = Path("/tmp/bikeplan-Q1.5")
root.mkdir(exist_ok=True)
region_path = "tests/fixtures/test-grid/region.yaml"
snapshot = "tests/fixtures/test-grid/snapshot"
commands = [
    [
        "uv",
        "run",
        "--frozen",
        "bikeplan",
        "run",
        region_path,
        "--snapshot",
        snapshot,
        "--out",
        str(root / "run"),
    ],
    [
        "uv",
        "run",
        "--frozen",
        "bikeplan",
        "report",
        region_path,
        "--snapshot",
        snapshot,
        "--out",
        str(root / "report"),
    ],
]
to_metres = Transformer.from_crs(4326, 32756, always_xy=True)
to_degrees = Transformer.from_crs(32756, 4326, always_xy=True)
x, y = to_metres.transform(151.15, -33.95)
track = gpxpy.gpx.GPXTrack()
segment = gpxpy.gpx.GPXTrackSegment()
track.segments.append(segment)
for offset in range(200, 601, 20):
    lon, lat = to_degrees.transform(x + offset, y + 200)
    segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon))
gpx = gpxpy.gpx.GPX()
gpx.tracks.append(track)
route = root / "made-up.gpx"
route.write_text(gpx.to_xml())
claims = root / "claims.yaml"
claims.write_text("[]\n")
commands.append(
    [
        "uv",
        "run",
        "--frozen",
        "bikeplan",
        "review",
        str(route),
        "--claims",
        str(claims),
        "--region",
        region_path,
        "--snapshot",
        snapshot,
        "--out",
        str(root / "review"),
    ]
)
for command in commands:
    subprocess.run(command, check=True, capture_output=True, text=True)
region = load_region(region_path)
profile = load_profile(region.profile, "profiles")
graph = build(snapshot, region, profile)
_, _, _, placed, resident, weights = scene(graph, region, snapshot)
planning = confirmed_planning(graph, profile, planning_network(graph, profile, region))
table = edge_table(graph)
sources = [node for _, node in placed]
legs = last_legs(
    graph, score_edges(graph, profile), sorted(resident.people), region.access.last_leg_m
)
allowed = {key for key, item in planning.edges.items() if not item["needs"]}
before = reach(
    graph, sources, region.access.reach_m, region.access.detour_max, allowed, table, legs
)


def independent(fixed):
    allowed = {key for key, item in planning.edges.items() if set(item["needs"]) <= fixed}
    after = safe_reach(
        table,
        [item.within for item in before],
        sources,
        region.access.reach_m,
        region.access.detour_max,
        allowed,
        legs,
    )
    nodes = {kind: set() for kind in weights}
    for (kind, _), was, now in zip(placed, before, after, strict=True):
        nodes[kind].update(now.safe - was.safe)
    counts = {
        kind: sum(resident.people.get(node, 0) for node in sorted(found))
        for kind, found in nodes.items()
    }
    union = set().union(*nodes.values())
    return {
        "unique_people": sum(resident.people.get(node, 0) for node in sorted(union)),
        "unique_people_by_type": counts,
        "gains_by_type": sum(counts.values()),
    }


def check(saved, expected):
    for key in ("unique_people", "gains_by_type"):
        assert abs(saved[key] - expected[key]) < 0.001
    assert set(saved["unique_people_by_type"]) == set(expected["unique_people_by_type"])
    for kind, count in expected["unique_people_by_type"].items():
        assert abs(saved["unique_people_by_type"][kind] - count) < 0.001


frontier = json.loads((root / "run/frontier.json").read_text())
packages = []
for curve in frontier["scenarios"]:
    for pick, package in zip(curve["picks"], curve["trip_packages"], strict=True):
        expected = independent(set(package["element_ids"]))
        check(pick, expected)
        packages.append({"package": package["package"], **expected})
records = json.loads((root / "run/projects.json").read_text())
fixed = set()
for record in records:
    fixed.update(item["id"] for item in record["elements"])
    check(record["totals"]["package_access_gains"], independent(fixed))
summary = json.loads((root / "run/summary.json").read_text())
check(summary["access_gains"], independent(fixed))
with (root / "run/projects.csv").open() as stream:
    for record, row in zip(records, csv.DictReader(stream), strict=True):
        expected = record["totals"]["access_gains"]
        for key in ("unique_people", "gains_by_type"):
            assert abs(float(row[key]) - expected[key]) < 0.001
        for kind, count in expected["unique_people_by_type"].items():
            assert abs(float(row["unique_people_" + kind]) - count) < 0.001
figures = json.loads((root / "report/figures.json").read_text())
for item in figures:
    value = subprocess.run(
        ["uv", "run", "--frozen", "python", "-I", "-c", item["recipe"]],
        cwd=root / "report",
        check=True,
        capture_output=True,
        text=True,
    )
    assert float(value.stdout) == item["value"]
review = json.loads((root / "review/figures.json").read_text())
labels = {item["label"]: item["value"] for item in review}
assert labels["Unique people gaining a safe destination"] == 750
assert labels["Unique people by type: school"] == 750
assert labels["Gains counted by type"] == 750
proof = {
    "row": "Q1.5",
    "scope": "Fresh full-mode shipped test-grid worked case; no real-region claim",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "config_hash": config_hash(region, profile),
    "snapshot_sha256": hashlib.sha256(Path(snapshot, "manifest.json").read_bytes()).hexdigest(),
    "commands": [" ".join(command) for command in commands],
    "packages": packages,
    "summary_access_gains": summary["access_gains"],
    "review_access_gains": {
        key: value
        for key, value in labels.items()
        if key.startswith(("Unique people", "Gains counted"))
    },
    "outputs": [
        {
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(root.glob("*/*"))
        if path.is_file()
    ],
}
Path("artifacts/Q1.5/people-proof.json").write_text(
    json.dumps(proof, indent=2, sort_keys=True) + "\n"
)
print("Package unions, summary, exports, figure recipes and route review agree")
