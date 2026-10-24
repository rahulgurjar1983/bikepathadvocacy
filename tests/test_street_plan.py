import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from tests.test_find_place import PLACES, TYPICAL, open_hash, street_cards, street_pick
from tests.test_report_page import data_for, lines, open_page, page_for, work


def plan_pick():
    found = street_pick()
    number = len(found["works"]) + 1
    found["works"].append(
        work("unnamed path road", "verge_path", 0.4, 0)
        | {"section": {"width": None, "before": TYPICAL}}
    )
    found["lines"].append(lines(number - 1, False, (151.16, -33.96)))
    return found, number


@pytest.fixture(scope="module")
def plan_page(tmp_path_factory):
    found, number = plan_pick()
    path = tmp_path_factory.mktemp("plan") / "report.html"
    path.write_text(page_for(data_for(options=[found], marks=PLACES)))
    return path, number


def test_fr16_11_an_unnamed_street_is_found_by_its_work_id(plan_page):
    path, number = plan_page
    driver = open_page(path)
    try:
        box = driver.find_element(By.ID, "q")
        box.send_keys(f"work {number}")
        WebDriverWait(driver, 5).until(lambda d: d.find_elements(By.CSS_SELECTOR, "#qlist li"))
        box.send_keys(Keys.ARROW_DOWN, Keys.ENTER)
        blocks = street_cards(driver)
        assert len(blocks) == 1
        assert f"Work {number}" in driver.find_element(By.CSS_SELECTOR, "#result.show h3").text
        assert "400 m" in blocks[0].text
    finally:
        driver.quit()


def test_fr16_11_the_work_id_opens_from_a_link(plan_page):
    path, number = plan_page
    driver = open_hash(path, f"#find-work-{number}")
    try:
        assert len(street_cards(driver)) == 1
    finally:
        driver.quit()


def test_fr16_11_each_local_work_names_the_selected_package_and_stage(plan_page):
    path, _ = plan_page
    driver = open_hash(path, "#find-ash-street")
    try:
        first, second = [block.text for block in street_cards(driver)]
        assert "My pick" in first and "First stage" in first
        assert "My pick" in second and "Full plan" in second
    finally:
        driver.quit()


def test_fr16_11_map_and_list_links_work_without_a_network(plan_page):
    path, _ = plan_page
    driver = open_hash(path, "#find-ash-street")
    try:
        block = street_cards(driver)[0]
        assert block.find_element(By.CSS_SELECTOR, "button.maplink").is_displayed()
        link = block.find_element(By.CSS_SELECTOR, "a.listlink")
        assert link.get_attribute("href").endswith("#streets")
        button = block.find_element(By.CSS_SELECTOR, "button.maplink")
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'})", button
        )
        button.click()
        WebDriverWait(driver, 5).until(lambda d: d.execute_script("return window.scrollY") < 400)
    finally:
        driver.quit()


def test_fr16_11_the_card_keeps_unknown_construction_effects_and_record_gaps_visible(plan_page):
    path, number = plan_page
    driver = open_hash(path, f"#find-work-{number}")
    try:
        text = street_cards(driver)[0].text
        assert "Temporary works: effects during building are not measured" in text
        assert "Not recorded: road width" in text
        assert "Not recorded: parking use and driveway access" in text
        assert "Cost: not priced" in text
        assert "Later decision" in text
    finally:
        driver.quit()


def test_fr16_11_a_known_width_is_not_listed_as_a_record_gap(plan_page):
    path, _ = plan_page
    driver = open_hash(path, "#find-ash-street")
    try:
        text = street_cards(driver)[0].text
        assert "Not recorded: road width" not in text
        assert "Next decision: council funds the design of this stage" in text
    finally:
        driver.quit()


def test_fr16_11_the_card_holds_at_390_px_without_sideways_scroll(plan_page):
    path, number = plan_page
    driver = open_hash(path, f"#find-work-{number}")
    try:
        driver.set_window_size(390, 900)
        assert "Next decision" in street_cards(driver)[0].text or "Later decision" in (
            street_cards(driver)[0].text
        )
        assert driver.execute_script(
            "return document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
    finally:
        driver.quit()


def test_fr16_11_the_card_names_both_endpoints_of_the_work(plan_page):
    path, number = plan_page
    driver = open_hash(path, f"#find-work-{number}")
    try:
        text = street_cards(driver)[0].text
        assert "Ends: -33.9600, 151.1600 to -33.9590, 151.1610" in text
    finally:
        driver.quit()


def test_fr16_11_the_card_separates_lasting_changes_from_temporary_works(plan_page):
    path, number = plan_page
    driver = open_hash(path, f"#find-work-{number}")
    try:
        text = street_cards(driver)[0].text
        assert "Lasting change: Shared path beside the road, 400 m" in text
        assert text.index("Lasting change") < text.index("Temporary works")
        assert "Not recorded: how building effects will be reduced" in text
    finally:
        driver.quit()


def test_fr16_11_print_shows_the_street_card_with_its_package_and_hides_the_buttons(plan_page):
    path, _ = plan_page
    driver = open_hash(path, "#find-ash-street")
    try:
        driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "print"})
        result = driver.find_element(By.ID, "result")
        assert result.is_displayed()
        assert "My pick" in result.text and "Ash Street" in result.text
        assert not driver.find_element(By.CSS_SELECTOR, "#result button.maplink").is_displayed()
        assert not driver.find_element(By.CSS_SELECTOR, "#result a.listlink").is_displayed()
    finally:
        driver.quit()
