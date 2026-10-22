import base64
import re

import pytest
from selenium.webdriver.common.by import By

from bikeplan import main
from tests.test_report_page import GRID, SNAPSHOT, STREETS, data_for, open_page, page_for


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    path = tmp_path_factory.mktemp("five") / "report.html"
    path.write_text(page_for(data_for()))
    return path


@pytest.fixture(scope="module")
def grid(tmp_path_factory):
    out = tmp_path_factory.mktemp("five-grid") / "out"
    assert main(["run", GRID, "--snapshot", SNAPSHOT, "--out", str(out)]) == 0
    return out


def resize(driver, width, height):
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 500},
    )


def test_fr20_1_the_stage_km_start_from_the_modelled_km_and_add_each_stage_gain():
    data = data_for(streets=STREETS | {"model_km": {"aaa": 5.0}})
    assert data["stages"]["today"]["km"] == 5.0
    assert data["stages"]["first"]["km"] == 9.0
    assert data["stages"]["works"]["km"] == 17.4
    assert [item["km"] for item in data["steps"]] == [5.0, 9.0, 9.04, 17.4]


def test_fr20_1_every_stage_tile_on_the_grid_page_shows_the_modelled_km(grid):
    text = (grid / "report.html").read_text()
    modelled = re.search(r'"model_km":\{"aaa":([\d.]+)\}', text).group(1)
    assert float(modelled) > 0
    driver = open_page(grid / "report.html")
    try:
        shown = []
        for button in driver.find_elements(By.CSS_SELECTOR, "[data-stage]"):
            button.click()
            shown.append(driver.find_element(By.ID, "t-km").text)
        assert shown == [str(round(float(modelled)))] * 3
    finally:
        driver.quit()


def test_fr20_20_the_big_numbers_are_at_least_40_px_at_390(page):
    driver = open_page(page, 390)
    try:
        resize(driver, 390, 844)
        sizes = driver.execute_script(
            "return [...document.querySelectorAll('.tile .n')]"
            ".map(e => parseFloat(getComputedStyle(e).fontSize))"
        )
        assert sizes
        assert min(sizes) >= 40
    finally:
        driver.quit()


def print_pages(driver):
    pdf = driver.execute_cdp_cmd(
        "Page.printToPDF", {"paperWidth": 8.27, "paperHeight": 11.69, "printBackground": True}
    )
    return len(re.findall(rb"/Type\s*/Page[^s]", base64.b64decode(pdf["data"])))


def test_fr20_20_the_a4_print_has_at_most_4_pages(page):
    driver = open_page(page)
    try:
        assert print_pages(driver) <= 4
    finally:
        driver.quit()
