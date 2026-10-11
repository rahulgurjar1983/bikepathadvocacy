import copy
import json
from html.parser import HTMLParser

import pytest
from selenium.webdriver.common.by import By

from bikeplan import trips
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser
from tests.test_report_change import move


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


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_resident_views_read_saved_record_offline_and_print(browser, built, name):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 2})
    changed["outcomes"]["resident_outcomes"]["strict"]["unique_residents"]["after"] = 12.345
    changed["outcomes"]["resident_outcomes"]["first_leg_model"]["reason"] = "Model only"
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
            section = browser.find_elements(By.ID, "selected-residents")
            assert section, "Resident outcomes need a selected-package view"
            assert section[0].get_attribute("data-package") == key
            assert browser.find_element(By.ID, "resident-package").text == key
            summary = browser.find_element(By.ID, "resident-summary")
            assert summary.is_displayed()
            assert json.loads(summary.text) == package["outcomes"]["resident_outcomes"]
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href)"
            ".then(r=>r.json()).then(arguments[0]);"
        )
        assert payload["selected"]["outcomes"] == package["outcomes"]
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]


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
