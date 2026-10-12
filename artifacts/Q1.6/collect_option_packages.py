import json
import sys
import tempfile
from pathlib import Path

from bikeplan import main
from bikeplan.proposal_record import option_packages

SOURCE = {"source": "council plan", "date": "2026-01-01"}
CONTENTS = {
    "stages": [
        {
            **SOURCE,
            "id": "study",
            "kind": "studies",
            "element_ids": ["segment:a"],
            "depends_on": [],
        },
        {
            **SOURCE,
            "id": "build",
            "kind": "construction",
            "element_ids": ["segment:b"],
            "depends_on": ["study"],
        },
    ]
}

with tempfile.TemporaryDirectory() as tmp:
    args = ["run", "tests/fixtures/test-grid/region.yaml", "--snapshot"]
    if main([*args, "tests/fixtures/test-grid/snapshot", "--out", tmp]) != 0:
        sys.exit("run failed")
    record = json.loads((Path(tmp) / "proposal.json").read_text())
result = {
    "archive_option_packages": record["option_packages"],
    "archive_curve_packages": len(record["packages"]),
    "stage_example": option_packages({"contents": CONTENTS}),
}
Path("artifacts/Q1.6/option-packages.json").write_text(json.dumps(result, indent=1) + "\n")
print(len(result["stage_example"]), "stage packages;", len(record["option_packages"]), "archive")
