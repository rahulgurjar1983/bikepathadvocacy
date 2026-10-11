import json

from bikeplan import main
from tests.test_propose_frontier import curve
from tests.test_propose_network import BUSY
from tests.test_propose_picks import star


def test_fr15_2_each_curve_project_has_a_full_sheet_with_its_own_totals():
    found = curve(star([(400, BUSY), (400, BUSY)]), {1: 100, 2: 10})
    sheets = found["project_sheets"]
    assert len(sheets) == len(found["picks"]) == 2
    for sheet, pick in zip(sheets, found["picks"], strict=True):
        assert sheet["id"] == pick["id"]
        assert sheet["rank"] == pick["rank"]
        assert sheet["gain"] == pick["gain"]
        assert sheet["score_after"] == pick["score"]
        assert sheet["totals"]["parking_spaces"] == 94
        assert sheet["elements"]
        for element in sheet["elements"]:
            assert element["before"]
            assert element["after"]
            assert element["check_links"]
            assert "width_confidence" in element
            assert "usable_verge" in element
    assert found["picks"][-1]["parking_spaces"] == 188


def test_fr16_1_archive_keeps_scenario_sheets_and_exact_package_membership(tmp_path):
    assert (
        main(
            [
                "report",
                "tests/fixtures/test-grid/region.yaml",
                "--snapshot",
                "tests/fixtures/test-grid/snapshot",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    record = json.loads((tmp_path / "proposal.json").read_text())
    frontier = json.loads((tmp_path / "frontier.json").read_text())
    assert [block["scenario"] for block in record["project_sheets"]] == [
        c["id"] for c in frontier["scenarios"]
    ]
    for block, scenario in zip(record["project_sheets"], frontier["scenarios"], strict=True):
        assert block["sheets"] == scenario["project_sheets"]
        assert [s["id"] for s in block["sheets"]] == [p["id"] for p in scenario["picks"][1:]]
        for sheet in block["sheets"]:
            assert sheet["delivery"]["costs"]["capital"]["low"] is None
            assert sheet["delivery"]["costs"]["capital"]["reason"]
        for package in record["packages"]:
            if package["identity"]["scenario"] == block["scenario"]:
                rank = package["identity"]["rank"]
                assert sorted(s["id"] for s in block["sheets"][:rank]) == package["project_ids"]
