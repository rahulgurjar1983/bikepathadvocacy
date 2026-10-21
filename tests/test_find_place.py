import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from bikeplan.config import DisruptionWeights, load_profile
from bikeplan.ladder import build_ladder, link_fixes
from bikeplan.options import link_table
from bikeplan.rating import model_ratings, option_totals
from bikeplan.stress import score_edges
from tests.test_option_ladder import fix_graph, people, row
from tests.test_option_rating import CALM, DETOUR, joined_path
from tests.test_report_page import data_for, lines, open_page, page_for, pick, work

PROFILE = load_profile("au-nsw")
WEIGHTS = DisruptionWeights(1.0, 40.0, 2.0, 15.0, 3.0, 5.0)

ASH_BEFORE = [
    ["parking", 2.1],
    ["through", 3.0],
    ["through", 3.0],
    ["parking", 2.1],
    ["spare", 1.8],
]
ASH_AFTER = [
    ["cycleway", 2.5],
    ["separator", 0.5],
    ["through", 3.0],
    ["through", 3.0],
    ["parking", 2.1],
    ["spare", 0.9],
]
TYPICAL = [["through", 3.0], ["through", 3.0]]

PLACES = [
    {"lon": 151.1105, "lat": -33.9095, "type": "school", "name": "Oak School", "id": "node/1"},
    {"lon": 151.12, "lat": -33.92, "type": "station", "name": "Elm Station", "id": "node/2"},
    {"lon": 151.13, "lat": -33.93, "type": "town_centre", "name": "Pine Centre", "id": "node/3"},
]
PARTNERS = [
    {"node/1": [], "node/2": [], "node/3": []},
    {"node/1": ["node/2"], "node/2": ["node/1"], "node/3": []},
    {"node/1": ["node/2"], "node/2": ["node/1"], "node/3": []},
    {
        "node/1": ["node/2", "node/3"],
        "node/2": ["node/1", "node/3"],
        "node/3": ["node/1", "node/2"],
    },
]


def strips(pairs):
    return [{"kind": kind, "width_m": width} for kind, width in pairs]


def street_pick():
    found = pick()
    for step, partners in zip(found["steps"], PARTNERS, strict=True):
        step["totals"]["partners"] = partners
    found["works"][0]["fix"] = "cycleway_in_spare"
    found["works"][0]["section"] = {"width": 12.0, "before": ASH_BEFORE, "after": ASH_AFTER}
    found["works"].append(
        work("Ash Street", "cycleway_parking_one_side", 0.6, 9, lane_km=0.3)
        | {"section": {"width": 12.0, "before": ASH_BEFORE, "after": ASH_AFTER}}
    )
    found["lines"].append(lines(3, False, (151.1106, -33.9096)))
    found["works"].append(
        work("Birch Road", "verge_path", 0.5, 0) | {"section": {"width": None, "before": TYPICAL}}
    )
    found["lines"].append(lines(4, False, (151.15, -33.95)))
    return found


@pytest.fixture(scope="module")
def card_page(tmp_path_factory):
    path = tmp_path_factory.mktemp("find") / "report.html"
    path.write_text(page_for(data_for(options=[street_pick()], marks=PLACES)))
    return path


def open_hash(path, fragment):
    driver = open_page(path)
    driver.get("about:blank")
    driver.get(path.resolve().as_uri() + fragment)
    return driver


def card(driver):
    return driver.find_element(By.CSS_SELECTOR, "#result.show")


def test_fr20_10_option_totals_list_the_safe_partners_of_each_place():
    graph, ratings, joined = joined_path()
    table = link_table(graph, ratings)
    first = option_totals(table, CALM + DETOUR, joined.joined)["partners"]
    assert first == {"node/1": [], "node/2": ["node/3"], "node/3": ["node/2"]}
    last = option_totals(table, CALM + DETOUR, joined.joined, frozenset(DETOUR))["partners"]
    assert last == {
        "node/1": ["node/2", "node/3"],
        "node/2": ["node/1", "node/3"],
        "node/3": ["node/1", "node/2"],
    }


def test_fr20_10_the_page_data_holds_each_places_safe_trips_by_stage_and_its_joins():
    data = data_for(options=[street_pick()], marks=PLACES)
    assert [item["t"] for item in data["places"]] == [[0, 1, 2], [0, 1, 2], [0, 0, 2]]
    assert [item["j"] for item in data["places"]] == [[1, 2], [0, 2], [0, 1]]


def test_fr20_10_enter_opens_the_place_card_with_the_hand_counted_trips(card_page):
    driver = open_page(card_page)
    try:
        box = driver.find_element(By.ID, "q")
        assert box.get_attribute("role") == "combobox"
        box.send_keys("o")
        assert driver.find_elements(By.CSS_SELECTOR, "#qlist li") == []
        box.send_keys("a")
        shown = [item.text for item in driver.find_elements(By.CSS_SELECTOR, "#qlist li")]
        assert any(text.startswith("Oak School") for text in shown)
        assert box.get_attribute("aria-expanded") == "true"
        box.send_keys("k")
        box.send_keys(Keys.ENTER)
        found = card(driver)
        assert found.find_element(By.TAG_NAME, "h3").text == "Oak School"
        assert found.find_element(By.ID, "pc-today").text.split()[0] == "0"
        assert found.find_element(By.ID, "pc-first").text.split()[0] == "1"
        assert found.find_element(By.ID, "pc-full").text.split()[0] == "2"
        assert driver.execute_script("return location.hash") == "#find-oak-school"
    finally:
        driver.quit()


def test_fr20_10_the_place_card_lists_the_joined_places_works_and_spots(card_page):
    driver = open_hash(card_page, "#find-oak-school")
    try:
        found = card(driver)
        joins = [item.text for item in found.find_elements(By.CSS_SELECTOR, "#pc-joins li")]
        assert joins == ["Elm Station", "Pine Centre"]
        assert found.find_element(By.CSS_SELECTOR, "#pc-works b").text == "1"
        assert found.find_element(By.CSS_SELECTOR, "#pc-spots b").text == "0"
    finally:
        driver.quit()


def test_fr20_10_a_station_card_counts_the_spots_within_500_m(card_page):
    driver = open_hash(card_page, "#find-elm-station")
    try:
        found = card(driver)
        assert found.find_element(By.CSS_SELECTOR, "#pc-spots b").text == "1"
        assert found.find_element(By.CSS_SELECTOR, "#pc-works b").text == "0"
        joins = [item.text for item in found.find_elements(By.CSS_SELECTOR, "#pc-joins li")]
        assert joins == ["Oak School", "Pine Centre"]
    finally:
        driver.quit()


def test_fr20_10_the_card_has_a_copy_link_button_and_the_equals_form_opens_it(card_page):
    driver = open_hash(card_page, "#find=oak-school")
    try:
        found = card(driver)
        assert found.find_element(By.CSS_SELECTOR, "button.copy").text == "Copy link"
        assert found.find_element(By.TAG_NAME, "h3").text == "Oak School"
    finally:
        driver.quit()


def test_fr20_10_a_hash_change_opens_the_card_without_a_reload(card_page):
    driver = open_page(card_page)
    try:
        driver.execute_script("location.hash = '#find-pine-centre'")
        WebDriverWait(driver, 5).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "#result.show h3")
        )
        assert card(driver).find_element(By.TAG_NAME, "h3").text == "Pine Centre"
    finally:
        driver.quit()


def street_cards(driver):
    return driver.find_elements(By.CSS_SELECTOR, "#result.show .swork")


def test_fr20_11_the_street_card_has_one_block_per_work_with_its_facts(card_page):
    driver = open_hash(card_page, "#find-ash-street")
    try:
        blocks = street_cards(driver)
        assert len(blocks) == 2
        first, second = [block.text for block in blocks]
        assert "Protected bike lane in spare road space" in first
        assert "4.0 km" in first and "First stage" in first
        assert "4 parking spaces" in first and "No traffic lane lost" in first
        assert "600 m" in second and "Full plan" in second
        assert "9 parking spaces" in second and "0.3 km of traffic lane" in second
    finally:
        driver.quit()


def rects(driver, block, which):
    return driver.execute_script(
        "return [...arguments[0].querySelectorAll('figure')[arguments[1]]"
        ".querySelectorAll('rect[data-m]')].map(r => [r.dataset.kind,"
        " parseFloat(r.dataset.m), parseFloat(r.getAttribute('width'))])",
        block,
        which,
    )


def test_fr20_11_the_cross_sections_are_drawn_to_one_scale_from_the_widths(card_page):
    driver = open_hash(card_page, "#find-ash-street")
    try:
        block = street_cards(driver)[0]
        before, after = rects(driver, block, 0), rects(driver, block, 1)
        kinds = [item[0] for item in before]
        assert {"footpath", "kerb", "parking", "through", "spare"} <= set(kinds)
        assert {"cycleway", "separator"} <= {item[0] for item in after}
        scales = {round(width / metres, 3) for _, metres, width in before + after}
        assert len(scales) == 1
        assert [m for k, m, _ in before if k == "through"] == [3.0, 3.0]
        assert round(sum(m for k, m, _ in before if k not in ("footpath", "kerb")), 1) == 12.0
        assert round(sum(m for k, m, _ in after if k not in ("footpath", "kerb")), 1) == 12.0
    finally:
        driver.quit()


def test_fr20_11_each_cross_section_names_its_parts_in_words(card_page):
    driver = open_hash(card_page, "#find-ash-street")
    try:
        block = street_cards(driver)[0]
        words = driver.execute_script(
            "return [...arguments[0].querySelectorAll('figure .xl')].map(e => e.textContent)",
            block,
        )
        for name in ("footpath", "kerb", "parking", "traffic lane"):
            assert name in words[0]
        assert "bike lane" in words[1]
        assert "12.0 m" in block.text
        assert "typical width" not in block.text
    finally:
        driver.quit()


def test_fr20_11_an_unknown_width_says_typical_width_and_a_path_is_labelled(card_page):
    driver = open_hash(card_page, "#find-birch-road")
    try:
        block = street_cards(driver)[0]
        assert "typical width" in block.text
        after = rects(driver, block, 1)
        assert "path" in [kind for kind, _, _ in after]
        words = driver.execute_script(
            "return arguments[0].querySelectorAll('figure .xl')[1].textContent",
            block,
        )
        assert "path" in words
    finally:
        driver.quit()


def test_fr20_11_link_fixes_carry_the_width_and_the_before_and_after_strips():
    graph = fix_graph()
    for _, _, data in graph.edges(data=True):
        data["width_measured_m"] = 12.0
    fits = {
        "s01": {
            "status": "fix",
            "fix": "cycleway_parking_one_side",
            "before": strips(ASH_BEFORE),
            "after": strips(ASH_AFTER),
        },
        "s12": {"status": "no_fit"},
    }
    ratings = model_ratings(graph, score_edges(graph, PROFILE), fits)
    table = link_table(graph, ratings)
    found = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    assert found[0, 1, 0]["section"] == {
        "width": 12.0,
        "before": ASH_BEFORE,
        "after": ASH_AFTER,
    }


def test_fr20_11_a_fix_other_than_the_fit_pick_draws_its_own_after_strips():
    graph = fix_graph()
    for _, _, data in graph.edges(data=True):
        data["width_measured_m"] = 14.0
    fits = {
        "s01": {
            "status": "fix",
            "fix": "road_diet",
            "before": strips(ASH_BEFORE),
            "after": strips(ASH_BEFORE),
            "candidates": [
                {
                    "fix": "cycleway_parking_one_side",
                    "accepted": True,
                    "layout": "pair",
                    "widths": "min",
                }
            ],
        },
        "s12": {"status": "no_fit"},
    }
    ratings = model_ratings(graph, score_edges(graph, PROFILE), fits)
    table = link_table(graph, ratings)
    found = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    assert found[0, 1, 0]["fix"] == "cycleway_parking_one_side"
    kinds = [kind for kind, _ in found[0, 1, 0]["section"]["after"]]
    assert "cycleway" in kinds and "separator" in kinds


def test_fr20_11_an_unknown_width_is_kept_as_none_in_the_section():
    graph = fix_graph()
    fits = {
        "s01": {"status": "fix", "fix": "cycleway_parking_one_side", "before": strips(TYPICAL)},
        "s12": {"status": "no_fit"},
    }
    ratings = model_ratings(graph, score_edges(graph, PROFILE), fits)
    table = link_table(graph, ratings)
    found = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    assert found[0, 1, 0]["section"]["width"] is None
    assert found[0, 1, 0]["section"]["before"] == TYPICAL


def test_fr20_11_a_ladder_work_keeps_the_section_of_its_first_link():
    table = {(0, 1, 0): row(), (1, 2, 0): row()}
    section = {"width": 9.0, "before": TYPICAL, "after": TYPICAL}
    fixes = {
        (0, 1, 0): {
            "street": "A St",
            "fix": "quietway",
            "parking_spaces": 0,
            "lane_km": 0.0,
            "speed_km": 0.1,
            "path_km": 0.0,
            "section": section,
        },
        (1, 2, 0): {
            "street": "A St",
            "fix": "quietway",
            "parking_spaces": 0,
            "lane_km": 0.0,
            "speed_km": 0.1,
            "path_km": 0.0,
            "section": section,
        },
    }
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 2)), fixes, WEIGHTS)
    assert ladder["works"][0]["section"] == section


def test_fr20_11_the_page_data_carries_each_works_section():
    data = data_for(options=[street_pick()], marks=PLACES)
    ash = next(item for item in data["works"] if item["street"] == "Ash Street")
    assert ash["sec"] == {"w": 12.0, "b": ASH_BEFORE, "a": ASH_AFTER}
    birch = next(item for item in data["works"] if item["street"] == "Birch Road")
    assert birch["sec"] == {"w": None, "b": TYPICAL, "a": None}


@pytest.fixture(scope="module")
def area_page(tmp_path_factory):
    from tests.test_council_plan import council_block, report_with_areas

    routes, areas = report_with_areas()
    data = data_for(
        options=[street_pick()],
        marks=PLACES,
        council=council_block() | {"routes": routes},
        areas=areas,
    )
    path = tmp_path_factory.mktemp("area") / "report.html"
    path.write_text(page_for(data))
    return path


def test_fr20_10_choosing_an_area_opens_the_ward_card_with_its_map_and_values(area_page):
    driver = open_page(area_page)
    try:
        box = driver.find_element(By.ID, "q")
        box.send_keys("ward 2")
        WebDriverWait(driver, 5).until(lambda d: d.find_elements(By.CSS_SELECTOR, "#qlist li"))
        assert driver.find_element(By.CSS_SELECTOR, "#qlist li").text.startswith("Ward 2")
        box.send_keys(Keys.ENTER)
        found = card(driver)
        assert found.find_element(By.TAG_NAME, "h3").text == "Ward 2"
        assert found.find_elements(By.CSS_SELECTOR, "svg polygon")
        assert found.find_element(By.CSS_SELECTOR, "button.copy").text == "Copy link"
        assert driver.current_url.endswith("#find-ward-2")
    finally:
        driver.quit()


def test_fr20_10_the_area_card_holds_the_same_values_as_the_ward_card_on_the_page(area_page):
    driver = open_hash(area_page, "#find-ward-1")
    try:
        found = card(driver)
        page_card = driver.find_elements(By.CSS_SELECTOR, "#wardcards .ward")[0]
        want = [item.text for item in page_card.find_elements(By.CSS_SELECTOR, "li")]
        got = [item.text for item in found.find_elements(By.CSS_SELECTOR, ".ward li")]
        assert got == want
        assert got[0] == "4 km of routes"
        assert found.find_element(By.CSS_SELECTOR, ".ward p").text == "Alpha, Beta"
        words = " ".join([*got, found.find_element(By.TAG_NAME, "h3").text]).split()
        assert len(words) <= 40
    finally:
        driver.quit()


def test_fr20_10_the_area_card_numbers_link_to_figure_entries(area_page):
    driver = open_hash(area_page, "#find=ward-1")
    try:
        links = card(driver).find_elements(By.CSS_SELECTOR, ".ward a.fig")
        assert len(links) == 5
    finally:
        driver.quit()
