import json

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from bikeplan import main
from tests.test_report import COMMITTED, REGION


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("community")
    assert main(["report", REGION, "--snapshot", str(COMMITTED), "--out", str(out)]) == 0
    return out


@pytest.fixture
def browser(built):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    driver = webdriver.Chrome(options=options)
    driver.get((built / "report.html").resolve().as_uri())
    yield driver
    driver.quit()


def test_fr16_2_proposal_tradeoffs_ask_and_gaps_lead_offline(browser):
    opening = browser.find_element(By.ID, "opening")
    text = opening.text
    for word in (
        "proposal",
        "trips",
        "school",
        "Capital",
        "Upkeep",
        "stage",
        "unknown",
        "I ask council",
    ):
        assert word in text
    assert opening.find_element(By.CSS_SELECTOR, 'a[href="#street-plans"]')
    sections = browser.find_elements(By.CSS_SELECTOR, "body > section")
    assert [item.get_attribute("id") for item in sections] == [
        "opening",
        "map",
        "change",
        "neighbourhoods",
        "street-plans",
        "delivery",
        "evidence",
        "report-glossary",
        "appendix",
    ]
    assert browser.find_element(By.ID, "chart").location["y"] > opening.location["y"]


def test_fr16_2_selected_opening_changes_and_baseline_is_honest(browser, built):
    frontier = json.loads((built / "frontier.json").read_text())
    slider = browser.find_element(By.ID, "change-slider")
    slider.send_keys(Keys.HOME)
    opening = browser.find_element(By.ID, "opening")
    assert "No new works" in opening.text
    assert opening.get_attribute("data-package") == "shipped:0"
    slider.send_keys(Keys.END)
    chosen = next(item for item in frontier["scenarios"] if item["id"] == "shipped")
    pick = chosen["picks"][-1]
    assert opening.get_attribute("data-package") == f"shipped:{pick['rank']}"
    assert float(
        opening.find_element(By.CSS_SELECTOR, '[data-opening="parking_spaces"]').text
    ) == pytest.approx(pick["parking_spaces"], abs=0.5)
    assert "removed" in opening.text
    assert "unknown" in opening.text


def test_fr16_2_scripts_off_retains_default_proposal_and_folded_evidence(built):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.javascript": 2}
    )
    driver = webdriver.Chrome(options=options)
    try:
        driver.get((built / "report.html").resolve().as_uri())
        assert "I ask council" in driver.find_element(By.ID, "opening").text
        table = driver.find_element(By.CSS_SELECTOR, '[data-for="change-chart"]')
        assert not table.is_displayed()
        driver.find_element(By.CSS_SELECTOR, "#curve-table > summary").click()
        assert table.is_displayed()
    finally:
        driver.quit()


@pytest.mark.parametrize("width", [390, 1280])
def test_fr15_3_layout_keyboard_status_and_print_selected_package(browser, built, width):
    browser.set_window_size(width, 900)
    assert browser.execute_script(
        "return document.documentElement.scrollWidth <= window.innerWidth"
    )
    radio = browser.find_element(By.ID, "scenario-shipped")
    radio.send_keys(Keys.ARROW_RIGHT)
    slider = browser.find_element(By.ID, "change-slider")
    slider.send_keys(Keys.HOME)
    slider.send_keys(Keys.ARROW_RIGHT)
    status = browser.find_element(By.ID, "package-status")
    assert status.get_attribute("role") == "status"
    assert "heavy" in status.text.lower() and "1" in status.text
    assert browser.find_element(By.ID, "opening").get_attribute("data-package") == "heavy:1"
    browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "print"})
    assert status.is_displayed()
    assert browser.find_element(
        By.CSS_SELECTOR, "#opening [data-opening=parking_spaces]"
    ).is_displayed()
    assert browser.find_element(By.ID, "change-why").is_displayed()
    assert (built / "report.html").stat().st_size <= 8_000_000
