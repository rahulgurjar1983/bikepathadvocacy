import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

out = Path("/tmp/bikeplan-C1.3-real")
proof = Path("artifacts/C1.3")
frontier = json.loads((out / "frontier.json").read_text())
population = frontier["trip_sources"]["population"]
shares = population["shares"]
assert len(shares) == len({(item["unit"], item["node"]) for item in shares})
source = Path("data/cache/au-nsw-bayside/2026-10-01/population.gpkg")
with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as connection:
    units = dict(connection.execute("select h3, population from population"))
assert set(item["unit"] for item in shares) <= set(units)
for unit in {item["unit"] for item in shares}:
    allocated = sum(item["people"] for item in shares if item["unit"] == unit)
    assert abs(allocated - units[unit]) < 1e-6
assert (
    abs(
        sum(units.values())
        - sum(item["people"] for item in shares)
        - population["buffer_excluded"]
        - population["unsnapped"]
    )
    < 1e-6
)
kinds = {item["id"]: item["type"] for item in frontier["trip_sources"]["destinations"]}
rows = []
for curve in frontier["scenarios"]:
    base = curve["trip_packages"][0]
    for package in curve["trip_packages"]:
        outcomes = package["resident_outcomes"]
        for mode in ("strict", "first_leg_model"):
            if base.get(mode) is None or package.get(mode) is None:
                assert outcomes[mode]["unique_residents"] == dict.fromkeys(
                    ("before", "after", "newly_gained")
                )
                continue
            pairs = {
                label: {(item["origin"], item["destination"]) for item in record[mode]}
                for label, record in (("before", base), ("after", package))
            }
            pairs["newly_gained"] = pairs["after"] - pairs["before"]
            for label, found in pairs.items():
                nodes = {node for node, _ in found}
                expected = sum(item["people"] for item in shares if item["node"] in nodes)
                assert outcomes[mode]["unique_residents"][label] == expected
                for kind in sorted(set(kinds.values())):
                    nodes = {node for node, destination in found if kinds[destination] == kind}
                    expected = sum(item["people"] for item in shares if item["node"] in nodes)
                    assert outcomes[mode]["by_place_type"][kind][label] == expected
        rows.append(
            {
                "package": package["package"],
                "project_ids": package["project_ids"],
                "strict": outcomes["strict"]["unique_residents"],
                "by_place_type": outcomes["strict"]["by_place_type"],
                "first_leg_model": outcomes["first_leg_model"]["unique_residents"],
                "evidence_status": outcomes["evidence_status"],
            }
        )
page = (out / "report.html").read_text()
assert "Unique estimated residents" in page
assert "Unknown age, disability, pupil and household data" in page
assert (out / "report.html").stat().st_size <= 8_000_000
shortlist = json.loads((out / "projects.geojson").read_text())["trip_proof"]
assert shortlist["resident_outcomes"]["strict"]["unique_residents"]["after"] == 0
inputs = [
    Path("regions/au-nsw-bayside.yaml"),
    Path("profiles/au-nsw.yaml"),
    source.parent / "manifest.json",
]
manifest = {
    "row": "C1.3",
    "build_commit": subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src/"], text=True
    ).strip(),
    "command": (
        "/usr/bin/time -v -o /tmp/c13-real-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-C1.3-real"
    ),
    "inputs": [
        {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs
    ],
    "outputs": [
        {"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(out.iterdir())
        if p.is_file()
    ],
    "population": {key: value for key, value in population.items() if key != "shares"},
    "source_population": sum(units.values()),
    "packages": rows,
    "report_bytes": (out / "report.html").stat().st_size,
    "limit": (
        "Saved model unions do not prove field safety or complete source coverage. "
        "Missing entrances leave strict trips unproved. Cell centres define scope; "
        "whole partial cells and equal node shares are proxies, not home addresses "
        "or household counts."
    ),
}
(proof / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
(proof / "time-full.txt").write_text(Path("/tmp/c13-real-time.txt").read_text())
print(
    json.dumps({key: manifest[key] for key in ("source_population", "report_bytes", "population")})
)
