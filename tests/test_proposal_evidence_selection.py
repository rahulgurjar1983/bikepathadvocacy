import copy
import json
from html.parser import HTMLParser

import pytest
from selenium.webdriver.common.by import By

from bikeplan import proposal_views
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser
from tests.test_report_change import move


class Evidence(HTMLParser):
    def __init__(self):
        super().__init__()
        self.package = None
        self.active = False
        self.text = ""
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "selected-evidence":
            self.package = attrs.get("data-package")
        if attrs.get("id") == "evidence-summary":
            self.active = True
        if tag == "script":
            self.scripts += 1

    def handle_data(self, data):
        if self.active:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "code":
            self.active = False


def test_fr16_1_script_free_evidence_uses_selected_record_and_keeps_missing_blocks(built):
    record = json.loads((built / "proposal.json").read_text())
    default = record["selected"]
    selected = copy.deepcopy(record["packages"][-1])
    selected["evidence_limits"]["school_sites"] = {
        "value": None,
        "reason": "School entrance unknown <script>throw Error('unsafe')</script>",
    }
    record["selected"] = selected
    page = Evidence()
    page.feed(proposal_views.evidence_view(record))
    identity = selected["identity"]
    assert page.package == f"{identity['scenario']}:{identity['rank']}"
    assert json.loads(page.text) == selected["evidence_limits"]
    assert page.scripts == 0
    assert json.loads(page.text)["school_sites"]["value"] is None
    assert "School entrance unknown" in page.text
    saved = Evidence()
    saved.feed((built / "report.html").read_text())
    assert saved.package is not None
    assert json.loads(saved.text) == default["evidence_limits"]


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_evidence_limits_follow_record_offline_exports_and_print(browser, built, name):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 2})
    changed["evidence_limits"]["route_gaps"] = [
        {"destination": "test-destination", "reason": "unknown_entrance_link"}
    ]
    changed["evidence_limits"]["school_sites"] = {
        "value": None,
        "reason": "Unknown <script>throw Error('unsafe')</script>",
    }
    browser.execute_script(
        "const n=document.getElementById('package-export-data');"
        "const d=JSON.parse(n.textContent);d.packages[arguments[0]].record=arguments[1];"
        "n.textContent=JSON.stringify(d);",
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
            sections = browser.find_elements(By.ID, "selected-evidence")
            assert sections, "Selected evidence limits need their own view"
            assert sections[0].get_attribute("data-package") == key
            assert browser.find_element(By.ID, "evidence-package").text == key
            summary = browser.find_element(By.ID, "evidence-summary")
            assert summary.is_displayed()
            assert json.loads(summary.text) == package["evidence_limits"]
            assert not summary.find_elements(By.TAG_NAME, "script")
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href)"
            ".then(r=>r.json()).then(arguments[0]);"
        )
        assert payload["selected"]["evidence_limits"] == package["evidence_limits"]
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
