import copy
import json
from html.parser import HTMLParser

import pytest
from selenium.webdriver.common.by import By

from bikeplan.change import proposal_opening
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser
from tests.test_report_change import move


def values(package):
    return {
        "trips": package["outcomes"]["trip_summary"]["strict_return_trips"]["value"],
        "residents": package["outcomes"]["resident_outcomes"]["strict"]["unique_residents"][
            "newly_gained"
        ],
    }


class Opening(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.text = {}
        self.links = {}
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id", "").startswith("opening-outcome-"):
            self.active = attrs["id"].removeprefix("opening-outcome-")
            self.text[self.active] = ""
            self.links[self.active] = attrs.get("href")
        if tag == "script":
            self.scripts += 1

    def handle_data(self, data):
        if self.active:
            self.text[self.active] += data

    def handle_endtag(self, tag):
        if tag in ("a", "span"):
            self.active = None


def test_fr16_1_script_free_opening_outcomes_read_record_and_preserve_unknowns(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    selected = copy.deepcopy(record["selected"])
    selected["outcomes"]["trip_summary"]["strict_return_trips"]["value"] = 17
    residents = selected["outcomes"]["resident_outcomes"]["strict"]
    residents["unique_residents"]["newly_gained"] = 12.345
    page = Opening()
    page.feed(proposal_opening(frontier, selected=selected))
    assert float(page.text["trips"]) == 17
    assert float(page.text["residents"]) == 12.345
    assert page.links["trips"] == "#F25"
    assert page.links["residents"] == "#F24"
    residents["unique_residents"]["newly_gained"] = None
    residents["reason"] = "Unknown entrance <script>throw Error('unsafe')</script>"
    trips = selected["outcomes"]["trip_summary"]["strict_return_trips"]
    trips["value"] = None
    trips["reason"] = "Return link not proved"
    missing = Opening()
    missing.feed(proposal_opening(frontier, selected=selected))
    assert missing.text["trips"] == "unknown"
    assert missing.text["residents"] == "unknown"
    assert missing.text["trips-reason"] == trips["reason"]
    assert missing.text["residents-reason"] == residents["reason"]
    assert missing.scripts == 0
    saved = Opening()
    saved.feed((built / "report.html").read_text())
    assert {key: float(saved.text[key]) for key in values(record["selected"])} == values(
        record["selected"]
    )


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_opening_outcomes_follow_record_exports_and_print(browser, built, name):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 2})
    changed["outcomes"]["trip_summary"]["strict_return_trips"].update(
        value=None, reason="Return <script>throw Error('unsafe')</script> unknown"
    )
    changed["outcomes"]["resident_outcomes"]["strict"]["unique_residents"]["newly_gained"] = 12.345
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
        for media in ("screen", "print"):
            browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
            assert (
                browser.find_element(By.ID, "opening").get_attribute("data-package")
                == f"{name}:{rank}"
            )
            for key, value in values(package).items():
                element = browser.find_element(By.ID, f"opening-outcome-{key}")
                assert element.is_displayed()
                assert element.text == ("unknown" if value is None else str(value))
                assert element.get_attribute("href").endswith("#F25" if key == "trips" else "#F24")
            reason = browser.find_element(By.ID, "opening-outcome-trips-reason")
            assert reason.text == package["outcomes"]["trip_summary"]["strict_return_trips"].get(
                "reason", ""
            )
            assert not reason.find_elements(By.TAG_NAME, "script")
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href)"
            ".then(r=>r.json()).then(arguments[0]);"
        )
        assert values(payload["selected"]) == values(package)
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
