import copy
import json
from html.parser import HTMLParser

import pytest
from selenium.webdriver.common.by import By

from bikeplan.proposal_inputs import delivery_section
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser
from tests.test_report_change import move


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


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_delivery_opening_print_and_exports_read_saved_package(browser, built, name):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 2})
    changed["decision"]["ask"] = "Seek selected public crossing records"
    changed["costs"]["capital"]["reason"] = "Selected cost scope unpriced"
    changed["owner"] = {"value": [{"organization": "Test public authority"}], "status": "partial"}
    browser.execute_script(
        "const n=document.getElementById('package-export-data');const d=JSON.parse(n.textContent);"
        "d.packages[arguments[0]].record=arguments[1];n.textContent=JSON.stringify(d);",
        f"{name}:2",
        changed,
    )
    for rank in (0, 1, 2, 0):
        move(browser, rank)
        package = next(
            p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": rank}
        )
        key = f"{name}:{rank}"
        for media in ("screen", "print"):
            browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
            assert browser.find_element(By.ID, "delivery").get_attribute("data-package") == key
            assert browser.find_element(By.ID, "delivery-package").text == key
            for selector in ("delivery-choice", "opening-delivery"):
                view = browser.find_element(By.ID, selector)
                assert view.is_displayed()
                assert view.get_attribute("data-package") == key
                assert package["decision"]["ask"] in view.text
                assert package["costs"]["capital"]["reason"] in view.text
                assert "Capital cost: unknown" in view.text
                assert "Funding: unknown" in view.text
                if rank == 2:
                    assert "Test public authority; remaining scope unknown" in view.text
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href).then(r=>r.json()).then(arguments[0]);"
        )
        assert payload["selected"]["decision"] == package["decision"]
        assert payload["selected"]["costs"] == package["costs"]
        assert payload["selected"]["owner"] == package["owner"]
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
