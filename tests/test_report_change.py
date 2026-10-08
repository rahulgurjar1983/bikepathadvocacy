import json
import re
from pathlib import Path
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


def test_fr13_15_with_scripts_off_the_recommended_step_totals_still_show(built, frontier):
    html = (built / "report.html").read_text()
    section = re.search(r'<section id="change".*?</section>', html, re.S).group(0)
    parsed = Totals()
    parsed.feed(section)
    chosen = scenario(frontier, "shipped")
    pick = chosen["picks"][chosen["recommended_stop"] or 0]
    assert parsed.found
    for key, text in parsed.found.items():
        assert float(text) == pytest.approx(step_value(pick, key))
    assert {"score", "disruption", "parking_spaces", "lane_km", "speed_km"} <= set(parsed.found)
    assert {"people.school", "people.station"} <= set(parsed.found)
    assert all(re.fullmatch(r"#F\d+", href) for href in parsed.links.values())
    assert "recommended" in re.search(r'id="change-why".*?</p>', section, re.S).group(0)


def test_fr13_15_chromium_opens_at_the_recommended_step_without_errors(browser, frontier):
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
    chosen = scenario(frontier, "shipped")
    slider = browser.find_element(By.ID, "change-slider")
    assert slider.is_enabled()
    assert int(slider.get_attribute("value")) == (chosen["recommended_stop"] or 0)
    assert int(slider.get_attribute("max")) == len(chosen["picks"]) - 1
    assert drawn(browser) == features_up_to(frontier, "shipped", chosen["recommended_stop"] or 0)


def test_fr13_15_moving_the_slider_changes_the_projects_drawn_and_the_totals(browser, frontier):
    chosen = scenario(frontier, "shipped")
    for step in (0, len(chosen["picks"]) - 1, 0):
        move(browser, step)
        assert drawn(browser) == features_up_to(frontier, "shipped", step)
        for key, value in shown(browser).items():
            assert value == pytest.approx(step_value(chosen["picks"][step], key))
    move(browser, 0)
    low = drawn(browser)
    move(browser, len(chosen["picks"]) - 1)
    assert drawn(browser) > low


def test_fr13_15_the_scenario_switch_changes_the_curve_and_the_slider_range(browser, frontier):
    for name in ("light", "heavy", "shipped"):
        browser.find_element(By.ID, f"scenario-{name}").click()
        selected = [
            item.get_attribute("id")
            for item in browser.find_elements(By.CSS_SELECTOR, "#change-chart [data-selected=true]")
        ]
        assert selected == [f"curve-{name}"]
        chosen = scenario(frontier, name)
        slider = browser.find_element(By.ID, "change-slider")
        assert int(slider.get_attribute("max")) == len(chosen["picks"]) - 1
        assert int(slider.get_attribute("value")) == (chosen["recommended_stop"] or 0)
        for key, value in shown(browser).items():
            pick = chosen["picks"][chosen["recommended_stop"] or 0]
            assert value == pytest.approx(step_value(pick, key))


def test_fr13_15_the_chart_dot_sits_at_the_step(browser, frontier):
    chosen = scenario(frontier, "shipped")
    browser.find_element(By.ID, "scenario-shipped").click()
    for step in (0, len(chosen["picks"]) - 1):
        move(browser, step)
        dot = browser.find_element(By.ID, "change-dot")
        assert int(dot.get_attribute("data-step")) == step
        curve = browser.find_element(By.ID, "curve-shipped").get_attribute("points")
        x, y = curve.split()[step].split(",")
        assert float(dot.get_attribute("cx")) == pytest.approx(float(x))
        assert float(dot.get_attribute("cy")) == pytest.approx(float(y))


def test_fr13_15_the_chart_has_a_title_and_a_table(built):
    html = (built / "report.html").read_text()
    section = re.search(r'<section id="change".*?</section>', html, re.S).group(0)
    assert re.search(r'<svg id="change-chart"[^>]*role="img"', section)
    assert re.search(r"<title[^>]*>[^<]+</title>", section)
    assert 'data-for="change-chart"' in section


PLACES = {"score": 1, "disruption": 1, "parking_spaces": 0, "lane_km": 3, "speed_km": 3}


def places(key):
    if key.startswith("people."):
        return 0
    if key.startswith("km."):
        return 3
    return PLACES[key]


def test_fr9_2_people_in_the_totals_are_whole_numbers(built):
    html = (built / "report.html").read_text()
    section = re.search(r'<section id="change".*?</section>', html, re.S).group(0)
    cells = re.findall(r'data-total="(people\.[a-z_]+)">([^<]*)<', section)
    assert cells
    assert all(re.fullmatch(r"\d+", text) for _, text in cells)


def test_fr9_2_moving_the_slider_shows_rounded_totals(browser, frontier):
    chosen = scenario(frontier, "shipped")
    for step in (0, 1, len(chosen["picks"]) - 1):
        move(browser, step)
        for item in browser.find_elements(By.CSS_SELECTOR, "#change-totals [data-total]"):
            key = item.get_attribute("data-total")
            want = f"{step_value(chosen['picks'][step], key):.{places(key)}f}"
            assert item.text == want


def section_of(built, name):
    html = (built / "report.html").read_text()
    return re.search(rf'<section id="{name}".*?</section>', html, re.S).group(0)


def test_fr9_2_people_in_the_projects_table_are_whole_numbers(built):
    row = re.search(r"<tbody><tr>(.*?)</tr>", section_of(built, "projects"), re.S).group(1)
    cells = re.findall(r"<code>([^<]*)</code>", row)
    assert re.fullmatch(r"\d+", cells[-1])


def test_fr9_2_people_in_the_summary_are_whole_numbers(built):
    summary = section_of(built, "summary")
    people = summary.split("People who gain safe reach, by place type")[1]
    cells = re.findall(r"<code>([^<]*)</code>", people)
    counts = cells[1::2]
    assert counts
    assert all(re.fullmatch(r"\d+", text) for text in counts)


def test_fr9_2_people_in_a_project_sheet_are_whole_numbers(built):
    html = (built / "report.html").read_text()
    sheet = re.search(r"<article id=\"project-.*?</article>", html, re.S).group(0)
    people = sheet.split("<th>Place type</th><th>People</th>")[1]
    counts = re.findall(r"<code>([^<]*)</code>", people)[1::2]
    assert counts
    assert all(re.fullmatch(r"\d+", text) for text in counts)


def change_part(out):
    html = (out / "report.html").read_text()
    return re.search(r'<section id="change".*?</section>', html, re.S).group(0)


def test_fr8_14_the_report_says_when_the_cap_was_reached(tmp_path):
    text = (
        Path(REGION)
        .read_text()
        .replace("  max_projects: 25\n", "  max_projects: 25\n  frontier_max_projects: 1\n")
    )
    region = tmp_path / "region.yaml"
    region.write_text(text)
    out = tmp_path / "out"
    assert main(["report", str(region), "--snapshot", str(COMMITTED), "--out", str(out)]) == 0
    assert "cap" in re.search(r'id="change-capped".*?</p>', change_part(out), re.S).group(0)
