import copy
import hashlib
import json
import socket
import subprocess
from pathlib import Path

from bikeplan.proposal_inputs import (
    attach_metadata,
    delivery_record,
    delivery_text,
    load_proposal_inputs,
    metadata_bytes,
)

out = Path("/tmp/bikeplan-Q2.4-real")
proof = Path("artifacts/Q2.4")


def offline(*args, **kwargs):
    raise AssertionError("network call during metadata replay")


socket.socket.connect = offline
frontier = json.loads((out / "frontier.json").read_text())
assert frontier["proposal_metadata"]["contents"] is None
packages = []
for curve in frontier["scenarios"]:
    for package in curve["trip_packages"]:
        delivery = package["delivery"]
        assert delivery == delivery_record(
            load_proposal_inputs(None),
            package["element_ids"],
            curve["works_catalog"],
            package["project_ids"],
        )
        for kind in ("capital", "upkeep"):
            total = delivery["costs"][kind]
            assert total["low"] is None and total["high"] is None
            assert total["missing_element_ids"] == sorted(set(package["element_ids"]))
        assert delivery["owner"]["value"] is None
        assert delivery["approvals"]["value"] is None
        assert delivery["funding"]["value"] is None
        assert delivery["decision"]["kind"] == "survey_or_concept_design"
        assert delivery["decision"]["build_ready"] is False
        if package["package"]["rank"] == (curve["recommended_stop"] or 0):
            packages.append({"package": package["package"], "delivery": delivery})
source = load_proposal_inputs(proof / "sourced-inputs.json")
assert source["sha256"] == hashlib.sha256(metadata_bytes(source["contents"])).hexdigest()
replayed = copy.deepcopy(frontier)
attach_metadata(replayed, source)
replay = []
for curve in replayed["scenarios"]:
    original = next(c for c in frontier["scenarios"] if c["id"] == curve["id"])
    for package, prior in zip(curve["trip_packages"], original["trip_packages"], strict=True):
        assert {k: v for k, v in package.items() if k != "delivery"} == {
            k: v for k, v in prior.items() if k != "delivery"
        }
        record = package["delivery"]
        assert record["metadata_sha256"] == source["sha256"]
        assert record["decision"]["ask"] == source["contents"]["next_decision"]["ask"]
        assert record["costs"]["capital"]["low"] is None
        assert record["owner"]["value"] is None
        assert record["funding"]["value"] is None
        assert record["decision"]["build_ready"] is False
        assert "council review" in delivery_text(record)
        if package["package"]["rank"] == (curve["recommended_stop"] or 0):
            replay.append({"package": package["package"], "delivery": record})
page = (out / "report.html").read_text()
assert "Capital cost: unknown" in page and "Upkeep cost: unknown" in page
assert "Spending, parking loss and weighted disruption are separate" in page
assert (out / "report.html").stat().st_size <= 8_000_000
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
manifest = {
    "row": "Q2.4",
    "build_commit": (proof / "build-commit.txt").read_text().strip(),
    "replay_commit": subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src/"], text=True
    ).strip(),
    "command": (
        "/usr/bin/time -v -o /tmp/q24-real-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q2.4-real"
    ),
    "replay_command": "uv run --frozen python artifacts/Q2.4/collect.py",
    "inputs": [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (
            Path("regions/au-nsw-bayside.yaml"),
            Path("profiles/au-nsw.yaml"),
            Path("data/cache/au-nsw-bayside/2026-10-01/manifest.json"),
            proof / "sourced-inputs.json",
        )
    ],
    "outputs": [
        {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(out.iterdir())
        if path.is_file()
    ],
    "metadata_sha256": source["sha256"],
    "packages_without_metadata": packages,
    "replayed_packages": replay,
    "report_bytes": (out / "report.html").stat().st_size,
    "scope": (
        "Fresh full Bayside run without metadata, plus offline sourced metadata replay on "
        "its exact saved packages. EW6 is public planning context and a proposed next ask, "
        "not confirmed works, ownership, consent, funding or a copied council budget. "
        "This proves truthful metadata handling, not costs, field safety or performance."
    ),
}
(proof / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
(proof / "time-full.txt").write_text(Path("/tmp/q24-real-time.txt").read_text())
print(json.dumps({"row": "Q2.4", "metadata_sha256": source["sha256"], "status": "passed"}))
