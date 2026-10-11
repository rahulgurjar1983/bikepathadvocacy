import hashlib
import json

from bikeplan import main


def test_fr16_1_proposal_record_is_in_the_report_hash_list(tmp_path):
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
    record = tmp_path / "proposal.json"
    assert record.is_file()
    assert json.loads(record.read_text())["schema_version"] == 1
    hashes = {
        name: digest
        for digest, name in (
            line.split("  ", 1) for line in (tmp_path / "SHA256SUMS").read_text().splitlines()
        )
    }
    assert hashes["proposal.json"] == hashlib.sha256(record.read_bytes()).hexdigest()
