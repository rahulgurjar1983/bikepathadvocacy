import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path

from bikeplan.change import change_figures, change_section, frontier_data

out = Path("/tmp/bikeplan-Q1.1-full")
proof = Path("artifacts/Q1.1")
raw = json.loads((out / "frontier.json").read_text())
curves = []
for scenario in raw["scenarios"]:
    best = 0.0
    stop = None
    for pick in scenario["picks"]:
        ratio = pick["gain"] / (pick["cost"] + 1)
        assert pick["gain"] > 0
        best = max(best, ratio)
        if ratio >= scenario["recommend_ratio"] * best:
            stop = pick["rank"]
    assert scenario["recommended_stop"] == stop
    assert scenario["evaluated_projects"] == len(scenario["picks"])
    assert scenario["truncated"] == (scenario["termination_reason"] == "project_cap")
    curves.append({key: value for key, value in scenario.items() if key != "shapes"})
(proof / "curve-data.json").write_text(json.dumps({"scenarios": curves}, indent=2) + "\n")
baseline = curves[0]["picks"][0]["score"] - curves[0]["picks"][0]["gain"]
kinds = sorted(curves[0]["picks"][0]["people"])
report_data = frontier_data(raw, baseline, kinds, {})
figures = {item["id"]: item for item in change_figures(report_data, json.dumps(report_data))}
section = change_section(report_data, figures)
assert "cost plus one" in section
assert "best ratio so far" in section
for scenario in curves:
    if scenario["truncated"]:
        assert scenario["label"] in section
        assert "curve is cut short" in section
(proof / "stop-section.html").write_text(section + "\n")
time_text = (proof / "time-full.txt").read_text()


def measured(label):
    return next(
        line.split(label + ": ", 1)[1] for line in time_text.splitlines() if label + ": " in line
    )


wall = measured("Elapsed (wall clock) time (h:mm:ss or m:ss)").split(":")
wall_seconds = sum(float(part) * 60**index for index, part in enumerate(reversed(wall)))
rss = int(measured("Maximum resident set size (kbytes)"))
assert wall_seconds <= 45 * 60
assert rss <= 6 * 1024**2
assert measured("Exit status") == "0"
files = [
    Path("regions/au-nsw-bayside.yaml"),
    Path("profiles/au-nsw.yaml"),
    Path("data/cache/au-nsw-bayside/2026-10-01/manifest.json"),
]
manifest = {
    "command": (
        "/usr/bin/time -v -o artifacts/Q1.1/time-full.txt uv run bikeplan propose "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.1-full"
    ),
    "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "config_and_snapshot_sha256": {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files
    },
    "output_sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(out.iterdir())
        if path.is_file()
    },
    "host": platform.platform(),
    "available_cpus": len(os.sched_getaffinity(0)),
    "run_state": "fresh outputs; no stage cache",
    "wall_seconds": wall_seconds,
    "user_cpu_seconds": float(measured("User time (seconds)")),
    "system_cpu_seconds": float(measured("System time (seconds)")),
    "peak_rss_kbytes": rss,
    "scenarios": [
        {key: value for key, value in scenario.items() if key not in ("shapes", "picks")}
        for scenario in curves
    ],
}
(proof / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest["scenarios"], indent=2))
