import json
import re
import sys
import tempfile
from pathlib import Path

from bikeplan import main, proposal_views
from bikeplan.proposal_record import option_packages

SOURCE = {"source": "council plan", "date": "2026-01-01"}
CONTENTS = {
    "stages": [
        {
            **SOURCE,
            "id": "study",
            "kind": "studies",
            "element_ids": ["segment:a"],
            "project_ids": [],
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
    page = (Path(tmp) / "report.html").read_text()
example = proposal_views.option_view({"option_packages": option_packages({"contents": CONTENTS})})
result = {
    "archive_empty_state": 'id="option-package-empty"' in page,
    "archive_option_packages": len(record["option_packages"]),
    "example_articles": re.findall(r'data-option-type="(\w+)"', example),
    "example_scripts": example.count("<script"),
}
if not result["archive_empty_state"] or result["archive_option_packages"] != 0:
    sys.exit("empty option state missing")
Path("artifacts/Q1.6/option-view.json").write_text(json.dumps(result, indent=1) + "\n")
print(result)
