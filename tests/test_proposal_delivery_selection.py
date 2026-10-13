import copy
import json
from html.parser import HTMLParser

from bikeplan.proposal_inputs import delivery_section
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser


class Delivery(HTMLParser):
    def __init__(self):
        super().__init__()
        self.package = None
        self.text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "delivery":
            self.package = attrs.get("data-package")

    def handle_data(self, data):
        self.text += data


def test_fr16_1_script_free_delivery_reads_selected_record_and_unknowns(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    selected = copy.deepcopy(record["packages"][-1])
    selected["decision"]["ask"] = "Seek the selected crossing records"
    selected["costs"]["capital"]["reason"] = "No price for this crossing"
    record["selected"] = selected
    links = {f"{p['identity']['scenario']}:{p['identity']['rank']}": {} for p in record["packages"]}
    page = Delivery()
    body, _ = delivery_section(frontier, links, record)
    page.feed(body)
    identity = selected["identity"]
    assert page.package == f"{identity['scenario']}:{identity['rank']}"
    assert selected["decision"]["ask"] in page.text
    assert "Capital cost: unknown. No price for this crossing" in page.text
    assert selected["costs"]["capital"]["low"] is None
    assert "Owner: unknown" in page.text
    assert "Funding: unknown" in page.text
