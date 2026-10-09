import hashlib
import json
import subprocess
from pathlib import Path

out = Path("/tmp/bikeplan-Q1.3-full")
proof = Path("artifacts/Q1.3")
summary = json.loads((out / "summary.json").read_text())
projects = json.loads((out / "projects.json").read_text())
network = json.loads((out / "network.geojson").read_text())
surveys = network["survey_options"]
evidence = {
    feature["properties"]["id"]: feature["properties"]
    for feature in json.loads((out / "projects.geojson").read_text())["features"]
}
assert summary["projects"] == len(projects)
assert surveys["features"]
assert all(feature["properties"]["fit_status"] == "needs_survey" for feature in surveys["features"])
for project in projects:
    for record in project["elements"]:
        element = evidence[record["id"]]
        if element["carriageway"] is not None:
            assert element["confirmed"]
            assert element["carriageway"]["observed"] or element["fix"] == "quietway"
        if element["fix"] == "verge_path":
            assert element["usable_verge"]["low_m"] is not None
            assert all(
                value == "clear" for value in element["usable_verge"]["constraints"].values()
            )
if not projects:
    assert summary["shortlist_reason"]
    assert "No confirmed project gains enough" in (out / "report.html").read_text()
parcel = next(
    feature["properties"]
    for feature in network["features"]
    if feature["properties"]["carriageway"]["source"] == "reserve"
)
assert not parcel["carriageway"]["observed"]
assert parcel["usable_verge"]["width_m"] is None
assert parcel["road_reserve"]["width_m"] is not None
assert parcel["road_reserve"]["date"] is not None
report_bytes = (out / "report.html").stat().st_size
assert report_bytes <= 8_000_000, report_bytes
(proof / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
(proof / "width-sample.json").write_text(json.dumps(parcel, indent=2, sort_keys=True) + "\n")
inputs = [
    Path("regions/au-nsw-bayside.yaml"),
    Path("profiles/au-nsw.yaml"),
    Path("data/cache/au-nsw-bayside/2026-10-01/manifest.json"),
]
manifest = {
    "row": "Q1.3",
    "commit": subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src/", "pyproject.toml", "uv.lock"], text=True
    ).strip(),
    "command": (
        "/usr/bin/time -v -o /tmp/q13-real-time.txt uv run bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.3-full"
    ),
    "inputs_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
    "outputs_sha256": [
        {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(out.iterdir())
        if path.is_file()
    ],
    "confirmed_projects": len(projects),
    "survey_segments": sum(
        len(feature["properties"]["segments"]) for feature in surveys["features"]
    ),
    "report_bytes": report_bytes,
    "shortlist_reason": summary["shortlist_reason"],
}
(proof / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
(proof / "time-full.txt").write_text(Path("/tmp/q13-real-time.txt").read_text())
print(
    json.dumps(
        {
            key: manifest[key]
            for key in ("confirmed_projects", "survey_segments", "report_bytes", "shortlist_reason")
        }
    )
)
