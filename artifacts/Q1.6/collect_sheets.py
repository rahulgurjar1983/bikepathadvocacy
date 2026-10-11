import hashlib
import json
import shutil
import subprocess
from pathlib import Path

out = Path("/tmp/bikeplan-Q1.6-sheets")
proof = Path("artifacts/Q1.6")
record = json.loads((out / "proposal.json").read_text())
frontier = json.loads((out / "frontier.json").read_text())
assert record["region"] == "au-nsw-bayside"
assert [b["scenario"] for b in record["project_sheets"]] == [c["id"] for c in frontier["scenarios"]]
counts = []
for block, curve in zip(record["project_sheets"], frontier["scenarios"], strict=True):
    assert block["sheets"] == curve["project_sheets"]
    assert [s["id"] for s in block["sheets"]] == [p["id"] for p in curve["picks"][1:]]
    for sheet, pick in zip(block["sheets"], curve["picks"][1:], strict=True):
        assert sheet["rank"] == pick["rank"]
        assert sheet["gain"] == pick["gain"]
        assert sheet["score_after"] == pick["score"]
        assert sheet["delivery"]["project_ids"] == [sheet["id"]]
        assert sheet["elements"]
        for element in sheet["elements"]:
            assert element["check_links"]
            assert "width_confidence" in element
            if "sections" not in element:
                assert element["before"]
                assert element["after"]
    packages = [p for p in record["packages"] if p["identity"]["scenario"] == curve["id"]]
    for package in packages:
        rank = package["identity"]["rank"]
        sheets = block["sheets"][:rank]
        assert sorted(s["id"] for s in sheets) == package["project_ids"]
        assert sorted({e["id"] for s in sheets for e in s["elements"]}) == package["element_ids"]
    counts.append(
        {"scenario": curve["id"], "sheets": len(block["sheets"]), "packages": len(packages)}
    )
outputs = []
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    outputs.append({"path": name, "sha256": digest})
saved = {
    "build_command": (
        "/usr/bin/time -v -o /tmp/q16-sheets-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.6-sheets"
    ),
    "check_command": "uv run --frozen python artifacts/Q1.6/collect_sheets.py",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "snapshot": record["snapshot"],
    "code": record["code"],
    "input_hashes": record["input_hashes"],
    "counts": counts,
    "outputs": outputs,
    "scope": (
        "Archive sheet records only; shared page selection, exports "
        "and goal/stage packages remain open"
    ),
}
(proof / "archive-sheets.json").write_text(json.dumps(saved, sort_keys=True, indent=2) + "\n")
shutil.copyfile("/tmp/q16-sheets-time.txt", proof / "sheets-time-full.txt")
print("All curve sheet records and package memberships agree; all output hashes match")
