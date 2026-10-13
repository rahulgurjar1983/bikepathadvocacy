import copy
import json
from html.parser import HTMLParser

from bikeplan.works import works_section
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser

SUMMARY_KEYS = (
    "unique_roads",
    "distinct_sections",
    "unnamed_roads",
    "km_by_design",
    "existing_links_retained",
    "crossing_upgrades",
    "parking_spaces",
)


def summary(works):
    return {key: works[key] for key in SUMMARY_KEYS} | {"gap_records": len(works["remaining_gaps"])}


def work_ids(works):
    return [section["id"] for section in works["sections"]] + works["crossing_upgrades"]


class Works(HTMLParser):
    def __init__(self):
        super().__init__()
        self.key = None
        self.text = ""
        self.rows = []
        self.package = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "physical-works":
            self.package = attrs.get("data-package")
        if attrs.get("id") == "works-summary":
            self.key = "summary"
        if tag == "tr" and "data-work-id" in attrs:
            self.rows.append(attrs["data-work-id"])

    def handle_data(self, data):
        if self.key:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "code":
            self.key = None


def test_fr16_1_script_free_works_read_selected_record_and_keep_nulls(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    selected = copy.deepcopy(record["packages"][-1])
    assert selected["works"]["crossing_upgrades"]
    selected["works"]["crossing_upgrades"] = selected["works"]["crossing_upgrades"][1:]
    selected["works"]["unique_roads"] = 123
    selected["works"]["parking_spaces"]["before"]["value"] = None
    record["selected"] = selected
    page = Works()
    page.feed(works_section(frontier, record))
    identity = selected["identity"]
    assert page.package == f"{identity['scenario']}:{identity['rank']}"
    assert json.loads(page.text) == summary(selected["works"])
    assert page.rows == work_ids(selected["works"])
    assert selected["works"]["parking_spaces"]["before"]["reason"]
