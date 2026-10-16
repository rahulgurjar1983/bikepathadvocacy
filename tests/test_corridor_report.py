import html
import json
import re
import subprocess
import sys

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By

from bikeplan.config import load_region
from bikeplan.edition import edition, edition_page
from bikeplan.options import Joined
from tests.test_checks_opening import OLD, REGION, options_four

TITLE = "Strategic cycleway corridors, Greater Sydney network map"
URL = (
    "https://www.transport.nsw.gov.au/system/files/media/documents/2023/"
    "Greater-Sydney-strategic-cycleway-corridors-network-map.pdf"
)
JOINED = Joined([], [], {"school": {"joined": 3, "unjoined": 0}})


def row(name, verdict, inside, near, today, step):
    return {
        "id": name,
        "from": f"{name} start",
        "to": f"{name} end",
        "km": inside + 1.0,
        "inside_km": inside,
        "near_km": near,
        "all_ages_km": today,
        "step_all_ages_km": step,
        "verdict": verdict,
    }


def corridor():
    segments = [
        row("T1", "covered", 2.5, 2.5, 1.25, 2.5),
        row("T2", "partly", 4.0, 2.0, 0.5, 1.75),
        row("T3", "missed", 3.0, 0.25, 0.0, 0.0),
        row("T4", "none inside", 0.0, 0.0, 0.0, 0.0),
    ]
    return {
        "source": {
            "title": TITLE,
            "date": "February 2023",
            "url": URL,
            "sha256": "a" * 64,
        },
        "segments": segments,
        "counts": {"covered": 1, "partly": 1, "missed": 1},
        "works": {"km": 1.75, "total_km": 7.0, "share": 0.25, "streets": ["Bay St"]},
        "routes": [
            {"id": "T1", "lines": [[[151.10, -33.90], [151.11, -33.90]]]},
            {"id": "T2", "lines": [[[151.10, -33.91], [151.11, -33.91]]]},
            {"id": "T3", "lines": [[[151.10, -33.92], [151.11, -33.92]]]},
        ],
    }


@pytest.fixture(scope="module")
def made():
    region = load_region(REGION)
    head, body, figures, text = edition(
        region, options_four(), [], JOINED, 0.9, [OLD], None, corridor()
    )
    return region, head, body, figures, text


@pytest.fixture(scope="module")
def plain():
    region = load_region(REGION)
    return edition(region, options_four(), [], JOINED, 0.9, [OLD], corridor=None)


def section(body):
    start = body.index('<section id="corridors">')
    return body[start : body.index("</section>", start)]


def test_fr19_5_the_section_follows_the_works_of_my_pick(made):
    _, _, body, _, _ = made
    spots = [body.index(f'id="{name}"') for name in ("works", "corridors", "no-fix")]
    assert spots == sorted(spots)
    assert "<h2>How my pick fits the TfNSW corridors</h2>" in section(body)


def test_fr19_5_it_opens_with_one_sentence_of_counts_and_works_km(made):
    _, _, body, _, _ = made
    text = re.sub(r"<[^>]+>", "", section(body))
    first = text.split("How my pick fits the TfNSW corridors", 1)[1].split(".", 1)[0]
    assert "covers 1 of the 4 segments" in first
    assert "partly covers 1" in first
    assert "misses 1" in first
    assert "1.75 km of its works" in first


def test_fr19_5_the_table_gives_each_segment_values_and_verdict(made):
    _, _, body, _, _ = made
    rows = re.findall(r"<tr>(.*?)</tr>", section(body).split("<tbody>")[1])
    assert len(rows) == 4
    cells = [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<td>(.*?)</td>", rows[1])]
    assert cells == ["T2", "T2 start", "T2 end", "4.00", "2.00", "0.50", "1.75", "partly"]
    assert "none inside" in rows[3]


def test_fr19_5_the_routes_are_called_indicative_never_tfnsws(made):
    _, _, body, _, _ = made
    text = html.unescape(re.sub(r"<[^>]+>", "", section(body)))
    assert "indicative" in text
    assert "TfNSW's route" not in text
    assert "TfNSW route" not in text


def test_fr19_5_the_section_credits_the_map_by_title_date_and_url(made):
    _, _, body, _, _ = made
    text = section(body)
    assert TITLE in text
    assert "February 2023" in text
    assert f'href="{URL}"' in text


def test_fr19_5_every_value_is_a_figure_with_a_recipe(made):
    _, _, body, figures, _ = made
    block = section(body)
    cells = re.findall(r"<td>(.*?)</td>", block.split("<tbody>")[1])
    numeric = [c for c in cells if re.fullmatch(r"(<a[^>]*>)?[\d.]+(</a>)?", c)]
    assert len(numeric) == 4 * 4
    assert all(c.startswith("<a href=") for c in numeric)
    ids = {item["id"] for item in figures}
    for link in re.findall(r'href="#(F\d+)"', block):
        assert link in ids
    assert all(item["spec"] == "spec 19" for item in figures if "corridor" in item["label"].lower())


def test_fr19_5_each_figure_recipe_prints_its_value_from_options_json(made, tmp_path):
    _, _, body, figures, text = made
    (tmp_path / "options.json").write_text(text)
    wanted = {link for link in re.findall(r'href="#(F\d+)"', section(body))}
    chosen = [item for item in figures if item["id"] in wanted]
    assert len(chosen) >= 4 * 4 + 4
    for item in chosen:
        shown = subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert float(shown) == pytest.approx(item["value"])


def test_fr19_5_the_sentence_counts_are_the_saved_counts(made):
    _, _, _, figures, _ = made
    values = sorted(
        item["value"] for item in figures if item["label"].startswith("Corridor segments")
    )
    assert values == [1, 1, 1]


def test_fr19_5_without_corridor_data_there_is_no_section_or_switch(plain):
    _, _, body, _ = plain
    assert 'id="corridors"' not in body
    assert "overlay-corridors" not in body
    assert "TfNSW" not in body


def test_fr19_5_the_overlay_switch_starts_off_and_is_in_the_key(made):
    _, _, body, _, _ = made
    assert re.search(r'<input type="checkbox" id="overlay-corridors">', body)
    assert "TfNSW corridors (indicative)" in body


@pytest.fixture(scope="module")
def browser(made, tmp_path_factory):
    region, head, body, figures, _ = made
    path = tmp_path_factory.mktemp("corridor") / "report.html"
    path.write_text(edition_page(region, head, body, [OLD, *figures], ""))
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    driver = webdriver.Chrome(options=options)
    driver.get(path.resolve().as_uri())
    driver.implicitly_wait(5)
    yield driver
    driver.quit()


def dashed(browser):
    return browser.execute_script(
        "return Array.from(document.querySelectorAll('#network-map path.corridor-line'))"
        ".map(p => [p.getAttribute('data-id'), p.getAttribute('stroke-dasharray')])"
    )


def test_fr19_5_the_overlay_draws_dashed_routes_with_ids_and_removes_them(browser):
    assert dashed(browser) == []
    browser.find_element(By.ID, "overlay-corridors").click()
    found = dashed(browser)
    assert [name for name, _ in found] == ["T1", "T2", "T3"]
    assert all(pattern for _, pattern in found)
    labels = browser.execute_script(
        "return Array.from(document.querySelectorAll('#network-map .corridor-label'))"
        ".map(e => e.textContent.trim())"
    )
    assert sorted(labels) == ["T1", "T2", "T3"]
    browser.find_element(By.ID, "overlay-corridors").click()
    assert dashed(browser) == []
    labels = browser.execute_script(
        "return document.querySelectorAll('#network-map .corridor-label').length"
    )
    assert labels == 0


def test_fr19_5_the_page_makes_no_network_call(browser):
    logs = [e for e in browser.get_log("browser") if "ERR_" in e["message"]]
    assert logs == []


def test_fr19_5_the_options_data_holds_the_routes(made):
    _, head, _, _, _ = made
    data = json.loads(re.search(r'id="network-data">(.*?)</script>', head).group(1))
    assert [item["id"] for item in data["corridors"]] == ["T1", "T2", "T3"]
