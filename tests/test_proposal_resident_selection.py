import copy
import json
from html.parser import HTMLParser

from bikeplan import trips
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser


class Residents(HTMLParser):
    def __init__(self):
        super().__init__()
        self.package = None
        self.active = False
        self.text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "selected-residents":
            self.package = attrs.get("data-package")
        if attrs.get("id") == "resident-summary":
            self.active = True

    def handle_data(self, data):
        if self.active:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "code":
            self.active = False


def test_fr16_1_script_free_residents_read_selected_record_with_null_and_reason(built):
    record = json.loads((built / "proposal.json").read_text())
    selected = copy.deepcopy(record["packages"][-1])
    outcomes = selected["outcomes"]["resident_outcomes"]
    outcomes["strict"]["unique_residents"]["after"] = None
    outcomes["strict"]["reason"] = "Entrance link unknown"
    record["selected"] = selected
    page = Residents()
    page.feed(trips.resident_section(record))
    identity = selected["identity"]
    assert page.package == f"{identity['scenario']}:{identity['rank']}"
    assert json.loads(page.text) == outcomes
    assert outcomes["strict"]["unique_residents"]["after"] is None
    assert outcomes["strict"]["reason"] == "Entrance link unknown"


def test_fr16_1_resident_figure_replays_saved_default_union(built):
    import hashlib
    import subprocess
    import sys

    record = json.loads((built / "proposal.json").read_text())
    figures = json.loads((built / "figures.json").read_text())
    found = [figure for figure in figures if figure["id"] == "F24"]
    assert found, "Selected residents need an archived figure recipe"
    figure = found[0]
    assert (
        figure["value"]
        == record["selected"]["outcomes"]["resident_outcomes"]["strict"]["unique_residents"][
            "newly_gained"
        ]
    )
    assert figure["unit"] == "estimated residents"
    assert figure["inputs"] == [
        {
            "name": "proposal.json",
            "sha256": hashlib.sha256((built / "proposal.json").read_bytes()).hexdigest(),
        }
    ]
    result = subprocess.run(
        [sys.executable, "-I", "-c", figure["recipe"]],
        cwd=built,
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(result.stdout) == figure["value"]
