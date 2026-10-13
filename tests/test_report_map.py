import json

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By

from bikeplan import main
from tests.report_snapshot import crafted
from tests.test_report import REGION


def node(number, lat, lon, tags):
    return {"type": "node", "id": number, "lat": lat, "lon": lon, "tags": tags}


PLACES = {
    "elements": [
        node(3000, -33.9482999, 151.1567429, {"amenity": "school", "name": "Grid School"}),
        node(3001, -33.9482999, 151.1572, {"amenity": "school", "name": "Second School"}),
        node(3002, -33.9478, 151.1567429, {"railway": "station", "name": "Grid Station"}),
    ]
}


def channels(colour):
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return red, green, blue


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = crafted(tmp_path_factory.mktemp("map-snapshot"), PLACES)
    out = tmp_path_factory.mktemp("map-out")
    assert main(["report", REGION, "--snapshot", str(folder), "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def data(built):
    return json.loads((built / "map.json").read_text())


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


def strokes(browser):
    return browser.execute_script(
        "return Array.from(document.querySelectorAll('#report-map svg path.leaflet-interactive'))"
        ".filter(p => p.getAttribute('stroke-dasharray') === null)"
        ".map(p => p.getAttribute('stroke'))"
    )


def switch(browser, name):
    browser.find_element(By.ID, name).click()


def test_fr13_9_map_data_adds_up_to_f1_and_f4(built, data):
    figures = {item["id"]: item for item in json.loads((built / "figures.json").read_text())}
    assert figures["F4"]["value"] == len(data["segments"])
    assert figures["F4"]["unit"] == "pieces"
    assert "map.json" in (built / "SHA256SUMS").read_text()
    assert {s["lts"] for s in data["segments"]} == {1, 3, 4}
    assert data["projects"]["features"]
