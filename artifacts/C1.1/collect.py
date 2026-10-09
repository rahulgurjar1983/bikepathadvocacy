import hashlib
import json
import subprocess
from pathlib import Path

out = Path("/tmp/bikeplan-C1.1-proof")
proof = Path("artifacts/C1.1")
frontier = json.loads((out / "frontier.json").read_text())
shortlist = json.loads((out / "projects.geojson").read_text())["trip_proof"]
rows = []
samples = []
for scenario in frontier["scenarios"]:
    assert len(scenario["trip_packages"]) == len(scenario["picks"])
    for rank, package in enumerate(scenario["trip_packages"]):
        assert package["package"] == {"scenario": scenario["id"], "rank": rank}
        assert len(package["project_ids"]) == rank
        assert len(package["groups"]) == len({g["id"] for g in package["groups"]})
        assert package["continuous_network"] == bool(
            package["strict"] and len(package["groups"]) == 1
        )
        for witness in package["strict"]:
            assert witness["arrival_evidence"]["bike_accessible"] is True
            assert witness["arrival_evidence"]["source"]
            assert witness["evidence_status"] == "confirmed"
            assert set(witness["required_elements"]) <= set(package["element_ids"])
            for direction in ("outbound", "return"):
                route = witness[direction]
                assert route["distance_m"] <= package["rules"]["reach_m"]
                assert route["distance_m"] <= package["rules"]["detour_max"] * route["shortest_m"]
                assert all(
                    item["status"] == "confirmed" for item in route["links"] + route["movements"]
                )
                assert all(
                    a[1] == b[0] for a, b in zip(route["edges"], route["edges"][1:], strict=False)
                )
        rows.append(
            {
                "package": package["package"],
                "project_ids": package["project_ids"],
                "element_ids": package["element_ids"],
                "strict_return_trips": len(package["strict"]),
                "route_groups": len(package["groups"]),
                "joins": len(package["joins"]),
                "gaps": len(package["gaps"]),
                "continuous_network": package["continuous_network"],
                "first_leg_status": package["first_leg_status"],
                "first_leg_model_trips": None
                if package["first_leg_model"] is None
                else len(package["first_leg_model"]),
            }
        )
        if rank in {0, scenario["recommended_stop"] or 0}:
            samples.append({**package, "gaps": package["gaps"][:3]})
html = (out / "report.html").read_text()
assert "Complete trips and route groups" in html
assert "Calm first legs are model-score assumptions" in html
assert (out / "report.html").stat().st_size <= 8_000_000
inputs = [
    Path("regions/au-nsw-bayside.yaml"),
    Path("profiles/au-nsw.yaml"),
    Path("data/cache/au-nsw-bayside/2026-10-01/manifest.json"),
]
manifest = {
    "row": "C1.1",
    "build_commit": subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src/"], text=True
    ).strip(),
    "command": (
        "/usr/bin/time -v -o /tmp/c11-real-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-C1.1-proof"
    ),
    "inputs": [
        {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs
    ],
    "outputs": [
        {"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(out.iterdir())
        if p.is_file()
    ],
    "packages": rows,
    "shortlist_strict_return_trips": len(shortlist["strict"]),
    "source_destinations": len(frontier["trip_sources"]["destinations"]),
    "source_entrances": len(frontier["trip_sources"]["evidence"].get("entrances", [])),
    "limit": (
        "These checks inspect saved model witnesses. "
        "They do not prove field safety or complete source coverage."
    ),
}
(proof / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
(proof / "trip-samples.json").write_text(json.dumps(samples, indent=2, sort_keys=True) + "\n")
(proof / "time-full.txt").write_text(Path("/tmp/c11-real-time.txt").read_text())
print(
    json.dumps(
        {
            key: manifest[key]
            for key in ("source_destinations", "source_entrances", "shortlist_strict_return_trips")
        }
    )
)
