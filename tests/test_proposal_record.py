import hashlib
import json
from pathlib import Path

import pytest

from bikeplan import main


@pytest.fixture(scope="module")
def archives(tmp_path_factory):
    root = tmp_path_factory.mktemp("proposal-record")
    result = {}
    for command in ("run", "report"):
        out = root / command
        assert (
            main(
                [
                    command,
                    "tests/fixtures/test-grid/region.yaml",
                    "--snapshot",
                    "tests/fixtures/test-grid/snapshot",
                    "--out",
                    str(out),
                ]
            )
            == 0
        )
        result[command] = out
    return result


def test_fr16_1_archives_save_versioned_selected_record_and_unknowns(archives):
    for command, out in archives.items():
        path = out / "proposal.json"
        assert path.is_file()
        record = json.loads(path.read_text())
        assert record["schema_version"] == 1
        assert record["region"] == "test-grid"
        assert record["snapshot"]["id"] == "2026-10-01"
        manifest = Path("tests/fixtures/test-grid/snapshot/manifest.json")
        assert record["snapshot"]["sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
        for digest in record["input_hashes"].values():
            assert len(digest) == 64
        assert len(record["code"]["sha256"]) == 64
        assert record["code"]["version"]
        selected = record["selected"]
        assert selected["kind"] == "confirmed"
        assert selected["evidence_mode"] == "confirmed"
        cost = selected["metrics"]["capital_cost"]
        assert cost["value"] is None
        assert cost["reason"]
        assert cost["evidence_status"] == "unknown"
        for metric in selected["metrics"].values():
            assert {
                "value",
                "unit",
                "scope",
                "source",
                "method",
                "evidence_status",
            } <= metric.keys()
            if metric["value"] is None:
                assert metric["reason"]
        assert record["pending"] == ["shared_view_selection", "goal_and_stage_packages"]
        sums = "outputs.sha256" if command == "run" else "SHA256SUMS"
        hashes = dict(line.split("  ")[::-1] for line in (out / sums).read_text().splitlines())
        assert hashes["proposal.json"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_fr15_2_record_keeps_curve_ids_totals_and_old_shortlist_apart(archives):
    for out in archives.values():
        record = json.loads((out / "proposal.json").read_text())
        frontier = json.loads((out / "frontier.json").read_text())
        packages = []
        for curve in frontier["scenarios"]:
            for package in curve["trip_packages"]:
                rank = package["package"]["rank"]
                saved = next(p for p in record["packages"] if p["identity"] == package["package"])
                assert saved["project_ids"] == sorted(set(package["project_ids"]))
                assert saved["element_ids"] == sorted(set(package["element_ids"]))
                assert saved["metrics"]["access_score"]["value"] == curve["picks"][rank]["score"]
                assert (
                    saved["metrics"]["parking_spaces_removed"]["value"]
                    == curve["picks"][rank]["parking_spaces"]
                )
                assert saved["evidence"]["rank"] == rank
                assert saved["evidence"]["scenario"] == curve["id"]
                packages.append(saved)
        assert record["packages"] == packages
        chosen = next(c for c in frontier["scenarios"] if c["id"] == frontier["default"])
        assert record["selected"]["identity"] == {
            "scenario": chosen["id"],
            "rank": chosen["recommended_stop"] or 0,
        }
        assert record["selected"] in packages
        assert record["shortlist"]["id"] == "legacy-min-gain"
        assert record["shortlist"]["label"] == "Old minimum-gain shortlist"
        assert record["shortlist"]["selected"] is False
