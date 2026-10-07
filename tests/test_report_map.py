import gzip
import json
import re
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By

from bikeplan import main
from tests.test_report import BOUNDARY, REGION

FIXTURE = Path("tests/fixtures/network/cases.osm")
PLACES = {
    "elements": [
        {
            "type": "node",
            "lat": -33.9101,
            "lon": 151.1202,
            "tags": {"amenity": "school", "name": "A"},
        },
        {
            "type": "node",
            "lat": -33.9102,
            "lon": 151.1204,
            "tags": {"amenity": "school", "name": "B"},
        },
        {
            "type": "way",
            "center": {"lat": -33.9103, "lon": 151.1206},
            "tags": {"railway": "station", "name": "Cases Station"},
        },
        {"type": "node", "lat": -33.9104, "lon": 151.1208, "tags": {"shop": "bakery"}},
    ]
}


def channels(colour):
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return red, green, blue


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = tmp_path_factory.mktemp("map-snapshot")
    (folder / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (folder / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    (folder / "places.json").write_text(json.dumps(PLACES))
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
    km = round(sum(float(s["length_m"]) for s in data["segments"]) / 1000, 3)
    assert km == figures["F1"]["value"] == figures["F4"]["value"]
    assert "map.json" in (built / "SHA256SUMS").read_text()
    assert {s["lts"] for s in data["segments"]} == {1, 2, 3, 4}


def test_fr13_9_the_inline_data_is_the_map_file(built, data):
    html = (built / "report.html").read_text()
    inline = re.search(r'<script type="application/json" id="map-data">(.*?)</script>', html, re.S)
    assert json.loads(inline.group(1)) == data
    markup = re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.S)
    assert not re.search(r'(?:src|href)="https?:', markup)


def test_fr13_9_chromium_logs_no_error_and_paints_each_level_colour(browser, data):
    errors = [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
    assert not errors
    painted = strokes(browser)
    assert len(painted) == len(data["segments"])
    blue = {c for c in painted if channels(c)[2] > channels(c)[0]}
    red = {c for c in painted if channels(c)[0] > channels(c)[2]}
    assert len(blue) == 2
    assert len(red) == 2
    assert blue | red == set(painted)


def test_fr13_9_a_level_switch_hides_that_level_only(browser, data):
    before = strokes(browser)
    switch(browser, "layer-lts-3")
    after = strokes(browser)
    level_3 = sum(1 for s in data["segments"] if s["lts"] == 3)
    assert level_3
    assert len(before) - len(after) == level_3
    switch(browser, "layer-lts-3")
    assert len(strokes(browser)) == len(before)


def test_fr13_9_the_all_ages_switch_keeps_only_safe_streets(browser, data):
    switch(browser, "layer-aaa")
    kept = len(strokes(browser))
    switch(browser, "layer-aaa")
    assert kept == sum(1 for s in data["segments"] if s["aaa"])
    assert kept < len(data["segments"])


def test_fr13_9_station_and_school_switches_draw_each_place(browser):
    def places():
        return browser.execute_script(
            "return Array.from(document.querySelectorAll('#report-map svg path.map-place'))"
            ".map(p => p.getAttribute('data-kind'))"
        )

    assert places() == []
    switch(browser, "layer-schools")
    assert places() == ["school", "school"]
    switch(browser, "layer-stations")
    assert sorted(places()) == ["school", "school", "station"]


def test_fr13_9_hover_names_street_type_level_and_all_ages(browser, data):
    segment = data["segments"][0]
    browser.execute_script(
        "const p = Array.from(document.querySelectorAll('#report-map svg path'))"
        ".find(p => p.getAttribute('data-id') === arguments[0]);"
        "p.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));",
        segment["id"],
    )
    text = browser.find_element(By.CSS_SELECTOR, ".leaflet-tooltip").text
    assert (segment["name"] or "Unnamed street") in text
    assert segment["highway"] in text
    assert f"level {segment['lts']}" in text.lower()
    assert "safe for all ages" in text.lower()


def test_fr13_9_the_proposed_changes_switch_is_off_and_says_why(browser):
    box = browser.find_element(By.ID, "layer-proposed")
    assert not box.is_enabled()
    assert not box.is_selected()
    note = browser.find_element(By.ID, "proposed-note").text
    assert "rank" in note


def test_fr13_9_the_map_is_a_figure_with_an_appendix_entry(built):
    html = (built / "report.html").read_text()
    assert 'id="report-map"' in html
    assert html.index('id="report-map"') < html.index('id="chart"')
    assert 'href="#F4"' in html
    assert 'id="F4"' in html
