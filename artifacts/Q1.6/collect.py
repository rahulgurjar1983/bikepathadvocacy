import hashlib
import json
import shutil
import subprocess
from pathlib import Path

out = Path("/tmp/bikeplan-Q1.6-real")
proof = Path("artifacts/Q1.6")
record = json.loads((out / "proposal.json").read_text())
frontier = json.loads((out / "frontier.json").read_text())
assert record["schema_version"] == 1
assert record["region"] == "au-nsw-bayside"
manifest = Path("data/cache/au-nsw-bayside/2026-10-01/manifest.json")
assert record["snapshot"]["sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
curves = {c["id"]: c for c in frontier["scenarios"]}
expected_ids = [p["package"] for c in frontier["scenarios"] for p in c["trip_packages"]]
assert [p["identity"] for p in record["packages"]] == expected_ids
for package in record["packages"]:
    identity = package["identity"]
    curve = curves[identity["scenario"]]
    rank = identity["rank"]
    raw = curve["trip_packages"][rank]
    assert package["kind"] == package["evidence_mode"] == "confirmed"
    assert package["project_ids"] == sorted(set(raw["project_ids"]))
    assert package["element_ids"] == sorted(set(raw["element_ids"]))
    assert package["works"] == raw["works"]
    assert package["costs"] == raw["delivery"]["costs"]
    assert package["decision"] == raw["delivery"]["decision"]
    assert package["outcomes"]["strict_complete_trips"] == len(raw["strict"])
    for field, key in (
        ("access_score", "score"),
        ("parking_spaces_removed", "parking_spaces"),
        ("unique_people_gaining_access", "unique_people"),
    ):
        assert package["metrics"][field]["value"] == curve["picks"][rank][key]
    for item in package["metrics"].values():
        assert {"unit", "scope", "source", "method", "evidence_status"} <= item.keys()
        if item["value"] is None:
            assert item["reason"]
            assert item["evidence_status"] == "unknown"
chosen = curves[frontier["default"]]
assert record["selected"]["identity"] == {
    "scenario": chosen["id"],
    "rank": chosen["recommended_stop"] or 0,
}
assert record["selected"] in record["packages"]
assert record["pending"] == ["shared_view_selection", "goal_and_stage_packages"]
projects = json.loads((out / "projects.json").read_text())
assert record["shortlist"]["project_ids"] == sorted({p["id"] for p in projects})
assert record["shortlist"]["selected"] is False
outputs = []
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    outputs.append({"path": name, "sha256": digest})
assert "proposal.json" in [item["path"] for item in outputs]
saved = {
    "command": (
        "/usr/bin/time -v -o /tmp/q16-real-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.6-real"
    ),
    "check_command": "uv run --frozen python artifacts/Q1.6/collect.py",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "snapshot": record["snapshot"],
    "code": record["code"],
    "input_hashes": record["input_hashes"],
    "outputs": outputs,
    "packages_checked": len(record["packages"]),
    "selected": record["selected"],
    "shortlist": record["shortlist"],
    "pending": record["pending"],
    "scope": "Versioned archive record only; view selection and goal/stage packages remain open",
}
(proof / "archive-record.json").write_text(json.dumps(saved, sort_keys=True, indent=2) + "\n")
shutil.copyfile("/tmp/q16-real-time.txt", proof / "time-full.txt")
print("Archive record agrees with every saved curve package; selection work remains open")
