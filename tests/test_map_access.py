import hashlib

import pytest
from selenium.webdriver.common.by import By

from tests.test_map_page import map_data_for, page_text, popup_links
from tests.test_report_page import open_page

AXE_SHA256 = "20c09fe157a8a34a30e241aaa1fcdade657734f08ab379ecfbeb7d45cc46e878"
SIZES = [(390, 844), (1440, 900)]


@pytest.fixture(scope="module")
def data():
    return map_data_for()


@pytest.fixture(scope="module")
def page(data, tmp_path_factory):
    path = tmp_path_factory.mktemp("map-access") / "map.html"
    path.write_text(page_text(data))
    return path


def sized(page, size, change=None):
    driver = open_page(page, size[0])
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": size[0], "height": size[1], "deviceScaleFactor": 1, "mobile": size[0] < 500},
    )
    if change:
        driver.get(page.resolve().as_uri() + "#" + change)
        driver.refresh()
        popup_links(driver)
    return driver


def test_fr21_8_axe_core_is_pinned_by_version_and_sha256(page):
    from bikeplan import axe

    assert axe.AXE_VERSION == "4.14.0"
    assert axe.AXE_SHA256 == AXE_SHA256
    assert hashlib.sha256(axe.axe_source().encode()).hexdigest() == AXE_SHA256
    driver = sized(page, SIZES[1])
    try:
        driver.execute_script(axe.axe_source())
        assert driver.execute_script("return axe.version") == "4.14.0"
    finally:
        driver.quit()


@pytest.mark.parametrize("size", SIZES, ids=["phone", "desktop"])
def test_fr21_8_no_serious_or_critical_violation_at_load(page, size):
    from bikeplan import axe

    driver = sized(page, size)
    try:
        assert axe.violations(driver) == []
    finally:
        driver.quit()


@pytest.mark.parametrize("size", SIZES, ids=["phone", "desktop"])
def test_fr21_8_no_serious_or_critical_violation_with_a_street_change_popup_open(page, data, size):
    from bikeplan import axe

    driver = sized(page, size, data["changes"][0]["id"])
    try:
        assert len(driver.find_elements(By.CSS_SELECTOR, ".leaflet-popup a.btn")) == 2
        assert axe.violations(driver) == []
    finally:
        driver.quit()


def test_fr21_8_a_planted_serious_violation_is_reported(page):
    from bikeplan import axe

    driver = sized(page, SIZES[1])
    try:
        driver.execute_script(
            "document.querySelector('#q').insertAdjacentHTML('afterend',"
            "'<img src=\"data:image/gif;base64,R0lGODlhAQABAAAAACw=\">')"
        )
        found = axe.violations(driver)
        assert [v["id"] for v in found] == ["image-alt"]
        assert found[0]["impact"] == "critical"
    finally:
        driver.quit()


@pytest.mark.parametrize("size", SIZES, ids=["phone", "desktop"])
def test_fr21_8_tab_reaches_the_search_the_chips_the_layer_boxes_and_each_list_item(
    page, data, size
):
    from bikeplan import axe

    driver = sized(page, size)
    try:
        stops = axe.tab_stops(driver, 80)
        ids = [s["id"] for s in stops if s["id"]]
        assert "q" in ids
        boxes = [
            e.get_attribute("id")
            for e in driver.find_elements(By.CSS_SELECTOR, "#layers .layer input")
        ]
        assert len(boxes) == 9 and set(boxes) <= set(ids)
        chips = [s["data"]["f"] for s in stops if s["cls"] == "chip"]
        assert chips == ["all", "quietway"]
        items = [
            s["data"].get("id") or s["data"].get("p") or s["data"].get("n")
            for s in stops
            if s["cls"] == "item"
        ]
        assert items == [
            "ash-street-quietway-1",
            "ash-street-quietway-2",
            "path-bay-trail",
            "path-park-link",
            "1",
            "2",
        ]
        assert [s["ring"] for s in stops if s["ring"] is False] == []
    finally:
        driver.quit()
