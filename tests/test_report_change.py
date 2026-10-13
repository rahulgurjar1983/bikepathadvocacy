import json
import re
from html.parser import HTMLParser

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By

from bikeplan import main
from tests.test_report import COMMITTED, REGION


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("change-out")
    assert main(["report", REGION, "--snapshot", str(COMMITTED), "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def frontier(built):
    return json.loads((built / "frontier.json").read_text())


@pytest.fixture(scope="module")
def browser(built):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.get((built / "report.html").resolve().as_uri())
    driver.implicitly_wait(5)
    yield driver
    driver.quit()


class Totals(HTMLParser):
    def __init__(self):
        super().__init__()
        self.key = None
        self.found = {}
        self.links = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "data-total" in attrs:
            self.key = attrs["data-total"]
            self.links[self.key] = attrs["href"]

    def handle_data(self, data):
        if self.key:
            self.found[self.key] = data
            self.key = None


def scenario(frontier, name):
    return next(item for item in frontier["scenarios"] if item["id"] == name)


def step_value(pick, key):
    kind, _, name = key.partition(".")
    return pick["people"][name] if kind == "people" else pick[key]


def shown(browser):
    return {
        item.get_attribute("data-total"): float(item.text)
        for item in browser.find_elements(By.CSS_SELECTOR, "#change-totals [data-total]")
    }


def move(browser, step):
    browser.execute_script(
        "const s = document.getElementById('change-slider'); s.value = arguments[0];"
        "s.dispatchEvent(new Event('input', {bubbles: true}));",
        step,
    )


def drawn(browser):
    return len(browser.find_elements(By.CSS_SELECTOR, "#report-map svg path.change-project"))


def features_up_to(frontier, name, step):
    picks = scenario(frontier, name)["picks"][1 : step + 1]
    ids = {item["id"] for item in picks}
    return sum(1 for item in frontier["shapes"]["features"] if item["properties"]["project"] in ids)


def test_fr13_15_frontier_json_ships_with_the_report(built, frontier):
    assert "frontier.json" in (built / "SHA256SUMS").read_text()
    assert [item["id"] for item in frontier["scenarios"]] == ["light", "shipped", "heavy"]
    for item in frontier["scenarios"]:
        assert [pick["rank"] for pick in item["picks"]] == list(range(len(item["picks"])))
        assert item["picks"][0]["disruption"] == 0
    assert frontier["shapes"]["features"]


def test_fr13_15_the_step_figures_have_ids_and_recipes(built):
    figures = {item["id"]: item for item in json.loads((built / "figures.json").read_text())}
    assert {"F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F13"} <= set(figures)
    for name in ("F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F13"):
        assert [part["name"] for part in figures[name]["inputs"]] == ["frontier.json"]


PLACES = {"score": 1, "disruption": 1, "parking_spaces": 0, "lane_km": 3, "speed_km": 3}


def places(key):
    if key.startswith("people."):
        return 0
    if key.startswith("km."):
        return 3
    return PLACES[key]


def section_of(built, name):
    html = (built / "report.html").read_text()
    return re.search(rf'<section id="{name}".*?</section>', html, re.S).group(0)


def change_part(out):
    html = (out / "report.html").read_text()
    return re.search(r'<section id="change".*?</section>', html, re.S).group(0)
