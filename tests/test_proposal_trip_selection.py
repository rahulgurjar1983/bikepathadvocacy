import copy
import hashlib
import json
import subprocess
import sys
from html.parser import HTMLParser

import pytest
from selenium.webdriver.common.by import By

from bikeplan import trips
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser
from tests.test_report_change import move


class SelectedTrips(HTMLParser):
    def __init__(self):
        super().__init__()
        self.package = None
        self.active = False
        self.text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "selected-trips":
            self.package = attrs.get("data-package")
        if attrs.get("id") == "trip-summary":
            self.active = True

    def handle_data(self, data):
        if self.active:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "code":
            self.active = False


def test_fr16_1_trip_record_and_script_free_view_keep_scope_and_unknowns(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    for package in record["packages"]:
        identity = package["identity"]
        curve = next(c for c in frontier["scenarios"] if c["id"] == identity["scenario"])
        source = curve["trip_packages"][identity["rank"]]
        metrics = package["outcomes"]["trip_summary"]
        for key, value, unit in (
            ("strict_return_trips", len(source["strict"]), "return trips"),
            ("route_groups", len(source["groups"]), "route groups"),
            ("route_gaps", len(source["gaps"]), "route gaps"),
        ):
            assert metrics[key]["value"] == value
            assert metrics[key]["unit"] == unit
            assert metrics[key]["scope"]["package"] == identity
            assert metrics[key]["source"]["file"] == "frontier.json"
            assert metrics[key]["method"]
            assert metrics[key]["evidence_status"] == "modelled"
    selected = copy.deepcopy(record["packages"][-1])
    selected["outcomes"]["trip_summary"]["strict_return_trips"].update(
        value=None, reason="Entrance evidence missing", evidence_status="unknown"
    )
    record["selected"] = selected
    page = SelectedTrips()
    page.feed(trips.selected_trip_section(record))
    identity = selected["identity"]
    assert page.package == f"{identity['scenario']}:{identity['rank']}"
    assert json.loads(page.text) == selected["outcomes"]["trip_summary"]
    assert "Entrance evidence missing" in page.text


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_selected_trip_summary_reads_record_offline_and_print(browser, built, name):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 2})
    changed["outcomes"]["trip_summary"]["route_groups"]["value"] = 123
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
            section = browser.find_element(By.ID, "selected-trips")
            assert section.get_attribute("data-package") == key
            assert browser.find_element(By.ID, "trip-package").text == key
            summary = browser.find_element(By.ID, "trip-summary")
            assert summary.is_displayed()
            assert json.loads(summary.text) == package["outcomes"]["trip_summary"]
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href)"
            ".then(r=>r.json()).then(arguments[0]);"
        )
        assert payload["selected"]["outcomes"] == package["outcomes"]
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]


def test_fr16_1_trip_figure_replays_selected_record(built):
    record = json.loads((built / "proposal.json").read_text())
    figures = json.loads((built / "figures.json").read_text())
    figure = next(f for f in figures if f["id"] == "F25")
    assert (
        figure["value"]
        == record["selected"]["outcomes"]["trip_summary"]["strict_return_trips"]["value"]
    )
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
