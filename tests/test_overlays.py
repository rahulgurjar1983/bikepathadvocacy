import json
import re

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from bikeplan import main
from bikeplan.config import load_region
from bikeplan.edition import edition, edition_page, street_overlay
from bikeplan.options import Joined
from tests.test_checks_opening import OLD, REGION
from tests.test_edition_browser import open_page
from tests.test_network_report import calm, option, shortest

SNAPSHOT = "tests/fixtures/test-grid/snapshot"
PIECES = [
    {
        "name": "Ash St",
        "highway": "residential",
        "lts": 1,
        "aaa": True,
        "lines": [[[-33.900, 151.150], [-33.900, 151.152]]],
    },
    {
        "name": "Dee Lane",
        "highway": "residential",
        "lts": 2,
        "aaa": True,
        "lines": [[[-33.901, 151.150], [-33.901, 151.152]]],
    },
    {
        "name": "Elm Ave",
        "highway": "tertiary",
        "lts": 2,
        "aaa": False,
        "lines": [[[-33.902, 151.150], [-33.902, 151.152]]],
    },
    {
        "name": "Bay St",
        "highway": "secondary",
        "lts": 3,
        "aaa": False,
        "lines": [[[-33.903, 151.150], [-33.903, 151.152]]],
    },
    {
        "name": "Cox Rd",
        "highway": "primary",
        "lts": 4,
        "aaa": False,
        "lines": [[[-33.904, 151.150], [-33.904, 151.152]]],
    },
]
PLACES = (
    [
        {"lat": -33.9 - 0.001 * n, "lon": 151.151, "type": "school", "name": f"School {n}"}
        for n in range(3)
    ]
    + [
        {"lat": -33.91, "lon": 151.151 + 0.0005 * n, "type": "station", "name": f"Station {n}"}
        for n in range(2)
    ]
    + [{"lat": -33.92, "lon": 151.151, "type": "town_centre", "name": "Town Centre"}]
)
COUNTS = {"school": 3, "station": 2, "town_centre": 1}
LINES = [
    {"work": 0, "ok": False, "line": [[151.1500, -33.9300], [151.1520, -33.9300]]},
    {"work": None, "ok": True, "line": [[151.1500, -33.9310], [151.1520, -33.9310]]},
]


def four():
    main_roads = option("Main roads", [0, 30, 70, 90], [0, 3, 6, 9], ["Bay St"], LINES)
    mesh = option("Mesh", [0, 20, 40, 60], [0, 2, 4, 6], ["Ash St", "Bay St", "Cox St"], LINES)
    return [calm(LINES), shortest(95.0, LINES), main_roads, mesh]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    region = load_region(REGION)
    joined = Joined([], [], {kind: {"joined": n, "unjoined": 0} for kind, n in COUNTS.items()})
    rows = [
        ["1", "1000.0", 1, 1],
        ["2", "500.0", 2, 1],
        ["3", "500.0", 2, 0],
        ["4", "250.0", 3, 0],
        ["5", "250.0", 4, 0],
    ]
    streets = street_overlay(PIECES, rows)
    head, body, made, _ = edition(region, four(), PLACES, joined, 0.9, [OLD], streets)
    path = tmp_path_factory.mktemp("overlays") / "report.html"
    path.write_text(edition_page(region, head, body, [OLD, *made], ""))
    return path


@pytest.fixture
def browser(built):
    driver = open_page(built, 1280)
    yield driver
    driver.quit()


def streets_drawn(browser):
    return browser.execute_script(
        "return Array.from(document.querySelectorAll('#network-map path.street-line'))"
        ".map(p => [Number(p.getAttribute('data-level')), p.getAttribute('stroke'),"
        " Number(p.getAttribute('stroke-width'))])"
    )


def toggle(browser, name):
    browser.execute_script(f"document.getElementById('overlay-{name}').click()")


def hue(colour):
    red, _, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return "red" if red > blue else "blue"


def test_fr17_13_the_street_overlay_opens_off_and_places_open_on(browser):
    assert not browser.find_element(By.ID, "overlay-streets").is_selected()
    assert streets_drawn(browser) == []
    for kind in COUNTS:
        assert browser.find_element(By.ID, f"overlay-{kind}").is_selected()


def test_fr17_13_the_street_switch_draws_each_level_in_blue_or_red_and_removes_it(browser):
    toggle(browser, "streets")
    drawn = streets_drawn(browser)
    assert sorted(level for level, _, _ in drawn) == [1, 2, 2, 3, 4]
    assert {level: hue(colour) for level, colour, _ in drawn} == {
        1: "blue",
        2: "blue",
        3: "red",
        4: "red",
    }
    toggle(browser, "streets")
    assert streets_drawn(browser) == []


def test_fr17_13_each_level_has_its_own_switch(browser):
    toggle(browser, "streets")
    for level in (1, 2, 3, 4):
        toggle(browser, f"lts-{level}")
        assert level not in [found for found, _, _ in streets_drawn(browser)]
        toggle(browser, f"lts-{level}")
        assert level in [found for found, _, _ in streets_drawn(browser)]


def test_fr17_13_the_all_ages_switch_shows_only_the_streets_rated_all_ages(browser):
    toggle(browser, "streets")
    toggle(browser, "aaa")
    assert sorted(level for level, _, _ in streets_drawn(browser)) == [1, 2]
    toggle(browser, "lts-1")
    assert sorted(level for level, _, _ in streets_drawn(browser)) == [2]


def test_fr17_13_busier_streets_are_drawn_thicker(browser):
    toggle(browser, "streets")
    widths = {level: width for level, _, width in streets_drawn(browser)}
    assert widths[1] < widths[4]
    assert widths[3] < widths[4]


def test_fr17_13_place_markers_match_the_counts_and_each_switch_removes_its_kind(browser):
    def markers():
        return browser.execute_script(
            "const found = {};"
            "document.querySelectorAll('#network-map .place-marker').forEach(m => {"
            " const k = m.getAttribute('data-kind'); found[k] = (found[k] || 0) + 1;});"
            "return found;"
        )

    assert markers() == COUNTS
    for kind in COUNTS:
        toggle(browser, kind)
        assert kind not in markers()
        assert len(markers()) == 2
        toggle(browser, kind)
    assert markers() == COUNTS


def test_fr17_13_the_key_names_each_place_type_with_a_shape_beside_the_colour(browser):
    key = browser.find_element(By.ID, "overlay-key")
    for label in ("Schools", "Stations", "Town centres"):
        assert label in key.text
    shapes = browser.execute_script(
        "return Array.from(document.querySelectorAll('#overlay-key svg[data-kind]'))"
        ".map(s => [s.getAttribute('data-kind'), s.firstElementChild.tagName.toLowerCase()])"
    )
    assert sorted(kind for kind, _ in shapes) == sorted(COUNTS)
    assert len({shape for _, shape in shapes}) == 3
    on_map = browser.execute_script(
        "return Array.from(document.querySelectorAll('#network-map .place-marker svg'))"
        ".map(s => [s.closest('.place-marker').getAttribute('data-kind'),"
        " s.firstElementChild.tagName.toLowerCase()])"
    )
    assert {tuple(item) for item in on_map} == {tuple(item) for item in shapes}


def click_text(browser, selector, index=0):
    browser.execute_script(
        "const e = document.querySelectorAll(arguments[0])[arguments[1]];"
        "const r = e.getBoundingClientRect();"
        "e.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true,"
        " clientX: r.left + r.width / 2, clientY: r.top + r.height / 2}));",
        selector,
        index,
    )
    return browser.find_element(By.CSS_SELECTOR, ".leaflet-tooltip").get_attribute("textContent")


def test_fr17_13_a_street_names_its_type_level_and_all_ages_rating(browser):
    toggle(browser, "streets")
    text = click_text(browser, "#network-map path.street-line[data-level='3']")
    assert "Bay St" in text
    assert "secondary" in text
    assert "level 3" in text.lower()
    assert "not" in text.lower()


def test_fr17_13_an_all_ages_street_says_it_is_rated_all_ages(browser):
    toggle(browser, "streets")
    text = click_text(browser, "#network-map path.street-line[data-level='1']")
    assert "Ash St" in text
    assert "level 1" in text.lower()
    assert "not" not in text.lower()
    assert "all ages" in text.lower()


def test_fr17_13_a_place_names_itself_and_its_type(browser):
    text = click_text(browser, "#network-map .place-marker[data-kind='station']")
    assert "Station" in text
    assert "station" in text.lower()


def pane_of(browser, selector):
    return browser.execute_script(
        "const p = document.querySelector(arguments[0]).closest('.leaflet-pane');"
        "return Number(getComputedStyle(p).zIndex);",
        selector,
    )


def assert_under_links(browser):
    links = pane_of(browser, "#network-map path[data-state]")
    assert pane_of(browser, "#network-map path.street-line") < links
    assert pane_of(browser, "#network-map .place-marker") < links
    assert browser.execute_script(
        "return document.querySelectorAll('#network-map path[data-state]').length"
    ) == len(LINES)


def test_fr17_13_overlays_stay_under_the_links_when_the_option_or_step_changes(browser):
    toggle(browser, "streets")
    assert_under_links(browser)
    browser.execute_script("document.getElementById('option-mesh').click()")
    assert_under_links(browser)
    slider = browser.find_element(By.ID, "disruption-slider")
    slider.send_keys(Keys.ARROW_LEFT)
    assert_under_links(browser)
    assert len(streets_drawn(browser)) == len(PIECES)


def test_fr17_13_the_key_gives_the_km_of_each_level_and_all_ages(built):
    text = built.read_text()
    data = json.loads(re.search(r'id="network-data">(.*?)</script>', text, re.S).group(1))
    assert data["streets"]["km"] == {"1": 1.0, "2": 1.0, "3": 0.25, "4": 0.25, "aaa": 1.5}
    assert len(data["streets"]["pieces"]) == len(PIECES)


def test_fr17_13_street_km_by_level_are_summed_from_the_rows():
    rows = [["1", "1500.0", 1, 1], ["2", "250.0", 3, 0], ["3", "250.0", 3, 1]]
    result = street_overlay(PIECES, rows)["km"]
    assert result == {"1": 1.5, "2": 0.0, "3": 0.5, "4": 0.0, "aaa": 1.75}


@pytest.fixture(scope="module")
def release(tmp_path_factory):
    out = tmp_path_factory.mktemp("overlay-release")
    assert main(["report", REGION, "--snapshot", SNAPSHOT, "--out", str(out)]) == 0
    return out


def test_fr17_13_on_a_release_the_street_km_add_up_to_the_street_figure(release):
    figures = json.loads((release / "figures.json").read_text())
    first = next(item for item in figures if item["id"] == "F1")
    text = (release / "report.html").read_text()
    data = json.loads(re.search(r'id="network-data">(.*?)</script>', text, re.S).group(1))
    km = data["streets"]["km"]
    assert sum(km[level] for level in "1234") == pytest.approx(first["value"], abs=0.003)
    assert km["aaa"] <= first["value"]
    saved = json.loads((release / "map.json").read_text())["segments"]
    kept = [{key: item[key] for key in item if key != "fix"} for item in saved]
    assert data["streets"]["pieces"] == kept
