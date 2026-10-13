import json

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from bikeplan.config import load_region
from bikeplan.edition import edition, edition_page
from bikeplan.options import Joined
from tests.test_checks_opening import OLD, REGION, options_four

ORDER = ["opening", "options", "map", "chart", "works", "no-fix", "quality"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    region = load_region(REGION)
    joined = Joined([], [], {"school": {"joined": 3, "unjoined": 0}})
    head, body, made, _ = edition(region, options_four(), [], joined, 0.9, [OLD])
    path = tmp_path_factory.mktemp("browser") / "report.html"
    path.write_text(edition_page(region, head, body, [OLD, *made], ""))
    return path


def open_page(path, width, scripts=True):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    if not scripts:
        options.add_experimental_option(
            "prefs", {"profile.managed_default_content_settings.javascript": 2}
        )
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 500},
    )
    driver.get(path.resolve().as_uri())
    driver.implicitly_wait(5)
    return driver


@pytest.mark.parametrize("width", [390, 1280])
def test_fr15_3_the_options_report_has_no_sideways_scroll(built, width):
    driver = open_page(built, width)
    try:
        wide = driver.execute_script(
            "return document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert wide <= 0
        assert driver.find_element(By.ID, "options").is_displayed()
    finally:
        driver.quit()


def test_fr15_3_the_arrow_keys_move_the_step_and_a_text_status_announces_it(built):
    driver = open_page(built, 1280)
    try:
        status = driver.find_element(By.ID, "step-totals")
        assert status.get_attribute("aria-live") == "polite"
        before = status.text
        slider = driver.find_element(By.ID, "disruption-slider")
        slider.send_keys(Keys.ARROW_LEFT)
        assert slider.get_attribute("value") == "2"
        assert status.text != before
        assert "step 2" in status.text
    finally:
        driver.quit()


def test_fr15_3_the_page_prints_the_opening_and_the_method(built):
    text = built.read_text()
    assert "@media print" in text
    assert text.index('id="opening"') < text.index('id="appendix"')


def test_fr16_2_the_pick_the_ask_and_the_gaps_come_before_the_appendix_in_order(built):
    text = built.read_text()
    spots = [text.index(f'id="{name}"') for name in ORDER]
    assert spots == sorted(spots)
    opening = text.split('id="map"')[0]
    assert "I ask council to adopt" in opening
    assert "<details>" in opening


def test_fr16_2_with_scripts_off_the_opening_and_the_step_status_still_read(built):
    driver = open_page(built, 1280, scripts=False)
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        assert "My pick" in body
        assert "I ask council" in body
        assert driver.find_element(By.ID, "step-totals").is_displayed()
    finally:
        driver.quit()


def test_fr16_2_changing_the_option_changes_the_status_under_the_map(built):
    driver = open_page(built, 1280)
    try:
        status = driver.find_element(By.ID, "step-totals")
        first = status.text
        driver.find_element(By.ID, "option-mesh").click()
        assert status.text != first
        assert "Mesh" in status.text
        assert json.loads(driver.find_element(By.ID, "network-data").get_attribute("textContent"))
    finally:
        driver.quit()
