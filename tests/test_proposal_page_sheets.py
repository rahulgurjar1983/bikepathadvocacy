import json

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By

from tests.test_report_change import browser as browser
from tests.test_report_change import built as built
from tests.test_report_change import frontier as frontier
from tests.test_report_change import move, scenario


def selected_ids(browser, selector):
    return [
        item.get_attribute("data-project-id")
        for item in browser.find_elements(By.CSS_SELECTOR, selector)
    ]


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_selected_list_and_sheets_follow_exact_curve_projects(
    browser, built, frontier, name
):
    record = json.loads((built / "proposal.json").read_text())
    curve = scenario(frontier, name)
    assert len(curve["picks"]) >= 3
    browser.find_element(By.ID, f"scenario-{name}").click()
    for rank in (0, 1, 2, 0):
        move(browser, rank)
        identity = f"{name}:{rank}"
        section = browser.find_elements(By.ID, "selected-projects")
        assert section, "The selected package needs its own list and page sheets"
        assert section[0].get_attribute("data-package") == identity
        package = next(
            p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": rank}
        )
        ids = [p["id"] for p in curve["picks"][1 : rank + 1]]
        assert sorted(ids) == package["project_ids"]
        assert selected_ids(browser, "#selected-project-list a") == ids
        assert selected_ids(browser, "#selected-project-sheets article") == ids
        for link in browser.find_elements(By.CSS_SELECTOR, "#selected-project-list a"):
            target = link.get_attribute("href").split("#")[-1]
            article = browser.find_element(By.ID, target)
            assert article.is_displayed()
            assert article.get_attribute("data-project-id") == link.get_attribute("data-project-id")
            assert article.get_attribute("data-package") == identity
        assert browser.find_element(By.ID, "opening").get_attribute("data-package") == identity
        assert "Old minimum-gain shortlist" in browser.find_element(By.ID, "selected-projects").text
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]


def test_fr16_1_page_sheets_keep_own_plans_impacts_unknowns_and_print_identity(
    browser, built, frontier
):
    browser.find_element(By.ID, "scenario-shipped").click()
    curve = scenario(frontier, "shipped")
    rank = len(curve["picks"]) - 1
    move(browser, rank)
    articles = browser.find_elements(By.CSS_SELECTOR, "#selected-project-sheets article")
    assert articles, "Every selectable project needs its scenario's sheet on the page"
    for article, sheet in zip(articles, curve["project_sheets"], strict=True):
        assert article.get_attribute("data-project-id") == sheet["id"]
        assert sheet["name"] in article.text
        assert "unknown" in article.text.lower()
        assert article.find_elements(By.CSS_SELECTOR, "svg.project-map")
        for element in sheet["elements"]:
            assert element["id"] in article.text
            for part in [element] if "before" in element else element["sections"]:
                for phase in ("before", "after"):
                    drawing = article.find_element(
                        By.CSS_SELECTOR,
                        f'svg[data-section-id="{part["id"]}"][data-phase="{phase}"]',
                    )
                    assert float(drawing.get_attribute("data-total-width-m")) == pytest.approx(
                        sum(s["width_m"] for s in part[phase]), abs=0.051
                    )
        totals = article.find_element(By.CSS_SELECTOR, '[data-for="sheet-impacts"]').text
        for key in ("parking_spaces", "signals", "refuges"):
            assert f"{sheet['totals'][key]:.1f}" in totals
    browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "print"})
    assert selected_ids(browser, "#selected-project-sheets article") == [
        s["id"] for s in curve["project_sheets"]
    ]
    assert all(a.is_displayed() for a in articles)
    assert f"shipped:{rank}" in browser.find_element(By.ID, "selected-package-label").text
    browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
    ids = browser.execute_script(
        "return Array.from(document.querySelectorAll('[id]')).map(e => e.id)"
    )
    assert len(ids) == len(set(ids))


def test_fr16_1_script_free_page_has_selected_sheets_and_named_shortlist(built):
    record = json.loads((built / "proposal.json").read_text())
    options = webdriver.ChromeOptions()
    for flag in (
        "--headless=new",
        "--no-sandbox",
        "--proxy-server=http://127.0.0.1:9",
        "--blink-settings=scriptEnabled=false",
    ):
        options.add_argument(flag)
    with webdriver.Chrome(options=options) as driver:
        driver.get((built / "report.html").resolve().as_uri())
        sections = driver.find_elements(By.ID, "selected-projects")
        assert sections, "The saved selected package must remain readable without scripts"
        identity = record["selected"]["identity"]
        assert (
            sections[0].get_attribute("data-package")
            == f"{identity['scenario']}:{identity['rank']}"
        )
        assert (
            sorted(selected_ids(driver, "#selected-project-sheets article"))
            == record["selected"]["project_ids"]
        )
        assert "Old minimum-gain shortlist" in sections[0].text
