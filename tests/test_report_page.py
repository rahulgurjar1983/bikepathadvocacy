import math
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from bikeplan import main
from bikeplan.config import load_region

MOCK = Path("specs/20-design/mock.html")
GRID = "regions/test-grid.yaml"
SNAPSHOT = "tests/fixtures/test-grid/snapshot"
ORDER = ["top", "find", "spots", "streets", "wards", "plans", "cost", "ask", "how", "evidence"]
MOCK_ONLY = ["pr191", "794", "Coward", "Design mock", "36\u201358", "Mascot", "Ward 3"]


def step(number, score, safe, km, parking, works=(), school=0):
    return {
        "step": number,
        "works": list(works),
        "totals": {
            "trips": 20,
            "safe_trips": safe,
            "score": score,
            "km_by_level": {1: km, 2: 0.0, 3: 0.0, 4: 0.0},
            "km_all_ages": km,
            "places_safe": {"school": school},
            "assumed_share": 0.5,
        },
        "disruption": {
            "parking_spaces": parking,
            "lane_km": 0.0,
            "speed_km": 0.0,
            "path_km": 0.0,
            "score": parking,
        },
    }


def work(street, fix, km, parking, **more):
    return {
        "street": street,
        "fix": fix,
        "km": km,
        "parking_spaces": parking,
        "lane_km": 0.0,
        "speed_km": 0.0,
        "path_km": 0.0,
        "score": parking,
        "links": [[0, 1, 0]],
    } | more


def spot(street, fix, km, parking, owner=None, trips=0):
    return work(
        street,
        fix,
        km,
        parking,
        spot=True,
        owner=owner,
        assumed=False,
        site_check=False,
        trips=trips,
    )


def lines(work_index, ok=False, at=(151.15, -33.95)):
    return {
        "work": work_index,
        "ok": ok,
        "line": [list(at), [at[0] + 0.001, at[1] + 0.001]],
    }


def pick():
    return {
        "id": "calm",
        "name": "Calm streets",
        "same_as": None,
        "km": 12.4,
        "ceiling": 95.0,
        "no_spots": 40.0,
        "blockers": [],
        "no_fix": [],
        "unjoined": [],
        "works": [
            work("Ash Street", "quietway", 4.0, 4),
            spot("Bay Street", "raised_zebra_crossing", 0.04, 3, trips=3),
            spot("Forest Road", "bike_walk_signals", 0.05, 3, "Transport for NSW", 6),
        ],
        "steps": [
            step(0, 10.0, 2, 0.0, 0),
            step(1, 50.0, 10, 4.0, 4, [0], 1),
            step(2, 65.0, 13, 4.04, 7, [1], 2),
            step(3, 90.0, 19, 12.4, 10, [2], 3),
        ],
        "lines": [
            lines(None, True, (151.1, -33.9)),
            lines(0, False, (151.11, -33.91)),
            lines(1, False, (151.12, -33.92)),
            lines(2, False, (151.13, -33.93)),
            lines(None, False, (151.14, -33.94)),
        ],
    }


CHOICE = {"pick": "calm", "step": 1, "streets": ["Ash Street"], "ask": "Adopt this."}
JOINED = {"school": {"joined": 3, "unjoined": 1}, "station": {"joined": 0, "unjoined": 0}}
MARKS = [{"lon": 151.12, "lat": -33.92, "type": "school", "name": "Oak School"}]
STREETS = {
    "pieces": [],
    "model_pieces": [{"name": "Ash Street", "lines": [[[-33.91, 151.11], [-33.9, 151.12]]]}],
}
CORRIDOR = {
    "counts": {"covered": 2, "partly": 1, "missed": 3},
    "routes": [{"id": "T1", "lines": [[[151.1, -33.9], [151.2, -33.9]]]}],
    "source": {
        "title": "TfNSW corridors",
        "date": "2023-02",
        "url": "https://x.test",
        "sha256": "0",
    },
}


def data_for(**more):
    from bikeplan.report_page import report_data

    given = {
        "options": [pick()],
        "choice": CHOICE,
        "marks": MARKS,
        "joined": JOINED,
        "streets": STREETS,
        "corridor": CORRIDOR,
        "boundary": None,
    }
    return report_data(**(given | more))


def page_for(data, evidence='<section id="options"><h2>Options</h2></section>', figures=()):
    from bikeplan.report_page import five_minute_page

    return five_minute_page(load_region("regions/au-nsw-bayside.yaml"), data, "", evidence, figures)


class Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.stack = []
        self.inside = {}
        self.details_open = None

    def handle_starttag(self, tag, attrs):
        found = dict(attrs)
        if "id" in found:
            self.ids.append(found["id"])
            if self.stack:
                self.inside[found["id"]] = self.stack[-1]
        if tag == "details" and found.get("id") == "evidence":
            self.details_open = "open" in found
        if tag not in {"br", "img", "input", "meta", "link", "hr"}:
            self.stack.append("evidence" if found.get("id") == "evidence" else self.where())

    def where(self):
        return self.stack[-1] if self.stack else None

    def handle_endtag(self, tag):
        if self.stack and tag not in {"br", "img", "input", "meta", "link", "hr"}:
            self.stack.pop()


def parse(text):
    found = Ids()
    found.feed(text)
    return found


def open_page(path, width=1440):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": False},
    )
    driver.get(path.resolve().as_uri())
    driver.implicitly_wait(5)
    return driver


@pytest.fixture(scope="module")
def full_page(tmp_path_factory):
    path = tmp_path_factory.mktemp("page") / "report.html"
    path.write_text(page_for(data_for()))
    return path


@pytest.fixture(scope="module")
def grid_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("grid") / "out"
    assert main(["run", GRID, "--snapshot", SNAPSHOT, "--out", str(out)]) == 0
    return out


def test_fr20_25_data_holds_the_stage_values_the_spots_and_the_line_styles():
    data = data_for()
    today, first, full = (data["stages"][key] for key in ("today", "first", "works"))
    assert (today["score"], today["trips"], today["km"], today["park"]) == (10.0, 20, 0.0, 0)
    assert (first["score"], first["km"], first["park"], first["places"]["school"]) == (
        50.0,
        4.0,
        4,
        1,
    )
    assert (full["score"], full["km"], full["park"], full["places"]["school"]) == (
        90.0,
        12.4,
        10,
        3,
    )
    assert data["rec"] == 1
    assert data["joined"]["school"] == {"joined": 3, "unjoined": 1}
    assert [item["w"] for item in data["steps"]] == [[], [0], [1], [2]]
    assert [line["s"] for line in data["lines"]] == [0, 1, 3, 3, 4]
    assert [line["w"] for line in data["lines"]] == [None, 0, 1, 2, None]
    assert [(w["i"], w["street"], w["stage"]) for w in data["works"]] == [(0, "Ash Street", 1)]


def test_fr20_25_spots_rank_by_the_trips_their_step_makes_safe():
    spots = data_for()["spots"]
    assert [(s["n"], s["street"], s["kind"], s["trips"]) for s in spots] == [
        (1, "Forest Road", "signals", 6),
        (2, "Bay Street", "zebra", 3),
    ]
    assert [s["owner"] for s in spots] == ["Transport for NSW", None]
    assert [round(s["m"]) for s in spots] == [50, 40]


def test_fr20_25_the_tfnsw_counts_and_lines_come_from_the_run():
    data = data_for()
    assert data["corridor_counts"] == {"covered": 2, "partly": 1, "missed": 3}
    assert data["corridors"] == [{"id": "T1", "lines": [[[151.1, -33.9], [151.2, -33.9]]]}]
    assert data["streets"] == [[[151.11, -33.91], [151.12, -33.9]]]


def test_fr20_25_a_part_without_data_is_left_out_of_the_data():
    data = data_for(corridor=None, marks=[])
    assert data["corridors"] == []
    assert data["places"] == []
    assert "council" not in data
    assert "wards" not in data


def test_fr20_25_the_page_has_the_mock_section_ids_in_order_less_missing_parts(full_page):
    ids = parse(full_page.read_text()).ids
    kept = [name for name in ids if name in ORDER]
    assert kept == ["top", "find", "spots", "streets", "plans", "ask", "how", "evidence"]
    assert "wards" not in ids
    assert "cost" not in ids
    mock = parse(MOCK.read_text()).ids
    assert [name for name in mock if name in ORDER] == ORDER


def test_fr20_25_no_spots_data_shows_no_spots_section():
    spotless = pick()
    spotless["works"] = spotless["works"][:1]
    spotless["steps"] = spotless["steps"][:2]
    spotless["lines"] = spotless["lines"][:2]
    ids = parse(page_for(data_for(options=[spotless]))).ids
    assert "spots" not in ids
    assert "streets" in ids


def test_fr20_25_no_tfnsw_data_shows_no_plans_section():
    ids = parse(page_for(data_for(corridor=None))).ids
    assert "plans" not in ids
    assert "spots" in ids


def test_fr20_25_the_ids_of_the_page_are_unique(full_page):
    ids = parse(full_page.read_text()).ids
    assert len(ids) == len(set(ids))


OVERRIDES = Path("specs/20-design/token-overrides.json")
ROOT_BLOCK = re.compile(r":root[^{]*\{[^}]*\}")


def squeeze(text):
    return re.sub(r"\s+", "", text)


def with_override(block, tokens):
    body = block[block.index("{") + 1 : block.rindex("}")]
    for name, value in tokens.items():
        body, hits = re.subn(rf"{re.escape(name)}:[^;}}]*", f"{name}:{value}", body)
        if not hits:
            body = body.rstrip().rstrip(";") + f";{name}:{value}"
    return block[: block.index("{") + 1] + body.rstrip().rstrip(";") + ";}"


def mock_blocks_after_overrides():
    import json

    found = json.loads(OVERRIDES.read_text())
    blocks = ROOT_BLOCK.findall(MOCK.read_text())
    out = []
    for block in blocks:
        head = block[: block.index("{")]
        if "dark" in head:
            block = with_override(block, found["dark"])
        elif "color-scheme" not in block:
            block = with_override(block, found["light"])
        out.append(squeeze(block))
    return out


def test_fr20_25_the_root_tokens_equal_the_mock(full_page):
    page = [squeeze(block) for block in ROOT_BLOCK.findall(full_page.read_text())]
    assert page == mock_blocks_after_overrides()
    assert any("--spot:#c2410c" in block for block in page)
    assert not any("--spot:#e8590c" in block for block in page)


def test_fr20_25_finished_spots_use_the_override_rule(full_page):
    text = squeeze(full_page.read_text())
    assert squeeze(".smark.done{background:var(--spot-done)}") in text
    assert squeeze(".smark.done{background:var(--plan)}") not in text


def test_fr20_25_the_mock_banner_and_data_are_not_on_the_page(full_page):
    text = full_page.read_text()
    for word in MOCK_ONLY:
        assert not re.search(rf"\b{re.escape(word)}\b", text), word


def test_fr20_25_the_hero_and_the_spot_story_show_this_runs_numbers(full_page):
    driver = open_page(full_page)
    try:

        def read(name):
            return driver.find_element(By.ID, name).text

        WebDriverWait(driver, 5).until(lambda _: read("t-km") == "12")
        WebDriverWait(driver, 5).until(lambda _: read("t-sch") == "3")
        assert read("t-sch-l") == "of 3 schools with an all-ages ride"
        WebDriverWait(driver, 5).until(lambda _: read("t-park") == "10")
        driver.find_element(By.CSS_SELECTOR, '[data-stage="1"]').click()
        WebDriverWait(driver, 5).until(lambda _: read("t-km") == "4")
        assert read("t-park") == "4"
        assert "50%" in read("scoreline")
        assert "of 20 short trips" in read("scoreline")
        assert "2 short spots" in read("spot-h")
        buttons = driver.find_elements(By.CSS_SELECTOR, "#spotlist li")
        assert [b.text.split("\n")[1] for b in buttons] == ["Forest Road", "Bay Street"]
        assert "TfNSW" in buttons[0].text
        assert "cover 2 in full and 1 in part. They miss 3." in read("tf-text")
        severe = [m for m in driver.get_log("browser") if m["level"] == "SEVERE"]
        assert severe == []
    finally:
        driver.quit()


def test_fr20_7_the_reading_time_is_the_word_count_over_200_rounded_up(full_page):
    driver = open_page(full_page)
    try:
        words = int(driver.execute_script("return document.documentElement.dataset.words"))
        shown = driver.find_element(By.ID, "readtime").text
        assert words > 0
        assert shown == f"{math.ceil(words / 200)}-minute read"
    finally:
        driver.quit()


def test_fr20_25_the_run_writes_the_mock_page_for_the_test_grid(grid_out):
    text = (grid_out / "report.html").read_text()
    ids = parse(text).ids
    assert [name for name in ids if name in ORDER] == ["top", "find", "ask", "how", "evidence"]
    assert "{{" not in text
    for word in MOCK_ONLY:
        assert not re.search(rf"\b{re.escape(word)}\b", text), word


def test_fr20_18_every_old_part_sits_inside_the_closed_check_every_number(grid_out):
    found = parse((grid_out / "report.html").read_text())
    assert found.details_open is False
    for name in ["opening", "options", "chart", "works", "quality", "appendix", "report-glossary"]:
        assert found.inside.get(name) == "evidence", name


def test_fr20_18_every_figure_link_still_resolves(grid_out):
    text = (grid_out / "report.html").read_text()
    found = parse(text)
    links = set(re.findall(r'href="#(F\d+)"', text))
    assert links
    assert {found.inside.get(name) for name in links} == {"evidence"}


def test_fr20_18_how_i_know_names_the_snapshot_date_and_the_modelled_ratings(grid_out):
    text = (grid_out / "report.html").read_text()
    part = text.split('id="how"')[1].split("<details")[0]
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"<[^>]+>", " ", part))
    assert "modelled" in part
    assert "1 October 2026" in part
    assert len(words) <= 120


def test_fr20_25_missing_cost_data_leaves_out_the_cost_tile(full_page):
    found = parse(full_page.read_text())
    assert "t-cost" not in found.ids


def test_fr20_25_the_map_key_spot_is_an_unnumbered_dot(full_page):
    driver = open_page(full_page)
    try:
        key = driver.find_element(By.CSS_SELECTOR, ".legend .dot")
        assert key.text == ""
    finally:
        driver.quit()


def test_fr20_18_a_place_count_links_to_its_own_figure_entry(grid_out):
    text = (grid_out / "report.html").read_text()
    want = re.search(r'<article id="(F\d+)"><h3>F\d+: Places of type school, joined', text)[1]
    driver = open_page(grid_out / "report.html")
    try:
        link = driver.find_element(By.XPATH, "//a[contains(@class,'fig')][contains(., 'school')]")
        assert link.get_attribute("href").endswith(f"#{want}")
    finally:
        driver.quit()


def test_fr20_18_following_a_figure_link_opens_the_closed_part_at_the_entry(grid_out):
    text = (grid_out / "report.html").read_text()
    want = re.search(r'<article id="(F\d+)"><h3>F\d+: Places of type school, joined', text)[1]
    driver = open_page(grid_out / "report.html")
    try:
        assert driver.execute_script("return document.getElementById('evidence').open") is False
        driver.find_element(By.XPATH, "//a[contains(@class,'fig')][contains(., 'school')]").click()
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.getElementById('evidence').open")
        )
        assert driver.find_element(By.ID, want).is_displayed()
    finally:
        driver.quit()


def corridor_figures(first):
    return [
        {
            "id": f"F{first + number}",
            "label": f"Corridor segments {name} by my pick",
            "value": value,
        }
        for number, (name, value) in enumerate([("covered", 2), ("partly", 1), ("missed", 3)])
    ]


@pytest.fixture(scope="module")
def page_figs():
    from bikeplan.edition import options_text
    from bikeplan.report_page import page_figures

    options = [pick()]
    joined = SimpleNamespace(counts=JOINED, unjoined=[])
    text = options_text(options, 0.9, joined)
    return page_figures(options, CHOICE, text, 100), text


def test_fr20_18_page_figures_hold_the_spot_street_change_and_score_numbers(page_figs):
    figures, _ = page_figs
    assert [item["id"] for item in figures] == [f"F{n}" for n in range(100, 105)]
    found = {item["label"]: item["value"] for item in figures}
    assert found == {
        "Spots of my pick": 2,
        "Length of the spots of my pick": 0.1,
        "Safety score of my pick without its spots": 40.0,
        "Safety score of my pick with every work built": 90.0,
        "Km of quietway works of my pick": 4.0,
    }
    for item in figures:
        assert set(item) == {
            "id",
            "label",
            "value",
            "unit",
            "spec",
            "method",
            "inputs",
            "sources",
            "recipe",
        }


def test_fr20_18_each_page_figure_recipe_prints_its_value_from_options_json(page_figs, tmp_path):
    figures, text = page_figs
    (tmp_path / "options.json").write_text(text)
    for item in figures:
        shown = subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert float(shown) == pytest.approx(item["value"])


def test_fr20_18_a_run_without_spots_or_works_makes_no_page_figures():
    from bikeplan.edition import options_text
    from bikeplan.report_page import page_figures

    bare = pick() | {"works": [], "steps": [step(0, 10.0, 2, 0.0, 0)]}
    joined = SimpleNamespace(counts=JOINED, unjoined=[])
    text = options_text([bare], 0.9, joined)
    assert page_figures([bare], CHOICE | {"step": 0}, text, 100) == []


def test_fr20_18_the_spot_street_change_and_corridor_numbers_link_to_their_own_figures(
    page_figs, tmp_path
):
    figures, _ = page_figs
    ids = {item["label"]: item["id"] for item in figures}
    path = tmp_path / "report.html"
    path.write_text(page_for(data_for(), figures=[*figures, *corridor_figures(200)]))
    driver = open_page(path)
    try:

        def target(xpath):
            return driver.find_element(By.XPATH, xpath).get_attribute("href").split("#")[1]

        heading = "//*[@id='spot-h']/a"
        assert target(heading) == ids["Spots of my pick"]
        links = driver.find_elements(By.CSS_SELECTOR, "#spot-p a.fig")
        assert [link.get_attribute("href").split("#")[1] for link in links] == [
            ids["Spots of my pick"],
            ids["Length of the spots of my pick"],
            ids["Safety score of my pick without its spots"],
            ids["Safety score of my pick with every work built"],
        ]
        assert (
            target(
                "//article[contains(@class,'fix')]"
                "[.//h3[.='Quiet street: 30 km/h and fewer cars cutting through']]//a"
            )
            == (ids["Km of quietway works of my pick"])
        )
        links = driver.find_elements(By.CSS_SELECTOR, "#tf-text a.fig")
        assert [link.get_attribute("href").split("#")[1] for link in links] == [
            "F200",
            "F201",
            "F202",
        ]
    finally:
        driver.quit()


def test_fr20_21_white_numbers_on_the_spot_colours_reach_4_5_to_1(full_page):
    driver = open_page(full_page)
    try:
        colours = driver.execute_script(
            "const s=getComputedStyle(document.documentElement);"
            "return [s.getPropertyValue('--spot').trim(), s.getPropertyValue('--spot-done').trim()];"
        )
    finally:
        driver.quit()

    def luminance(hexcode):
        parts = [int(hexcode[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    assert colours == ["#c2410c", "#1d4ed8"]
    for colour in colours:
        assert 1.05 / (luminance(colour) + 0.05) >= 4.5
