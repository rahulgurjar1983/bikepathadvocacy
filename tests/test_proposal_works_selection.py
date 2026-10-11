import copy
import json
from html.parser import HTMLParser

import pytest
from selenium.webdriver.common.by import By

from bikeplan.works import works_section
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser
from tests.test_report_change import move

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


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_works_totals_and_rows_follow_saved_package_offline_and_print(browser, built, name):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 2})
    assert len(changed["works"]["crossing_upgrades"]) >= 2
    changed["works"]["unique_roads"] = 123
    changed["works"]["crossing_upgrades"] = changed["works"]["crossing_upgrades"][1:]
    browser.execute_script(
        "const node=document.getElementById('package-export-data');"
        "const data=JSON.parse(node.textContent);"
        "data.packages[arguments[0]].record=arguments[1];"
        "node.textContent=JSON.stringify(data);",
        f"{name}:2",
        changed,
    )
    for rank in (0, 1, 2, 0):
        move(browser, rank)
        identity = {"scenario": name, "rank": rank}
        package = next(p for p in record["packages"] if p["identity"] == identity)
        key = f"{name}:{rank}"
        for media in ("screen", "print"):
            browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
            assert (
                browser.find_element(By.ID, "physical-works").get_attribute("data-package") == key
            )
            assert browser.find_element(By.ID, "works-package").text == key
            assert json.loads(browser.find_element(By.ID, "works-summary").text) == summary(
                package["works"]
            )
            rows = browser.find_elements(By.CSS_SELECTOR, "#works-rows tr")
            assert [row.get_attribute("data-work-id") for row in rows] == work_ids(package["works"])
            assert all(row.is_displayed() for row in rows)
            assert all(row.get_attribute("data-package") == key for row in rows)
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href)"
            ".then(r=>r.json()).then(arguments[0]);"
        )
        assert payload["selected"]["works"] == package["works"]
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
