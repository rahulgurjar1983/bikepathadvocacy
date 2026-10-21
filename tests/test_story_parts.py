import re

from selenium.webdriver.common.by import By

from bikeplan.cost import load_rates
from tests.test_council_plan import council_block, report_with_areas
from tests.test_report_page import (
    CORRIDOR,
    data_for,
    open_page,
    page_for,
    pick,
    spot,
    work,
)

QUIET = "Quiet street: 30 km/h and fewer cars cutting through"
STATE = "Transport for NSW"


def words(text):
    return len(re.findall(r"[A-Za-z0-9]+", text))


def shown(tmp_path, data, **more):
    path = tmp_path / "report.html"
    path.write_text(page_for(data, **more))
    return path


def texts(driver, selector):
    return [item.text for item in driver.find_elements(By.CSS_SELECTOR, selector)]


def many_spots(count):
    found = pick()
    for number in range(count):
        found["works"].append(
            spot(f"Spot {number} Road", "raised_zebra_crossing", 0.03, 2, trips=100 - number)
        )
        found["lines"].append(
            {
                "work": len(found["works"]) - 1,
                "ok": False,
                "line": [[151.2, -33.9], [151.21, -33.91]],
            }
        )
    found["steps"][3]["works"] = list(range(1, len(found["works"])))
    return found


def many_streets(names):
    found = pick()
    index = len(found["works"])
    for number, name in enumerate(names):
        found["works"].append(work(name, "quietway", 3.0 - number * 0.1, 0))
    found["steps"][1]["works"] = [0, *range(index, index + len(names))]
    return found


def test_fr20_12_each_spot_carries_the_parking_it_removes():
    data = data_for()
    assert [(item["street"], item["park"]) for item in data["spots"]] == [
        ("Forest Road", 3),
        ("Bay Street", 3),
    ]


def test_fr20_12_the_cards_follow_km_with_the_plain_names_and_no_code_word(tmp_path):
    driver = open_page(shown(tmp_path, data_for()))
    try:
        names = texts(driver, "#fixes .fix h3")
        assert names == [QUIET, "Bike and walk signals", "Raised zebra crossing"]
        assert not [name for name in names if "_" in name]
    finally:
        driver.quit()


def test_fr20_12_a_spot_card_gives_its_count_and_the_parking_it_removes(tmp_path):
    driver = open_page(shown(tmp_path, data_for()))
    try:
        cards = {
            card.find_element(By.TAG_NAME, "h3").text: card.text
            for card in driver.find_elements(By.CSS_SELECTOR, "#fixes .fix")
        }
        assert "1 spot" in cards["Raised zebra crossing"]
        assert "3 parking spaces" in cards["Raised zebra crossing"]
        assert "1 spot" in cards["Bike and walk signals"]
        assert "4 parking spaces" in cards[QUIET]
        assert "4.0 km" in cards[QUIET]
    finally:
        driver.quit()


def test_fr20_13_one_sentence_gives_the_spots_their_length_and_the_share_before_and_after(
    tmp_path,
):
    driver = open_page(shown(tmp_path, data_for()))
    try:
        sentence = driver.find_element(By.ID, "spot-p").text
        assert (
            sentence == "Fix these 2 spots, 90 m in all, and all-ages trips rise from 40% to 90%."
        )
    finally:
        driver.quit()


def test_fr20_13_the_sentence_numbers_link_to_their_own_figures(tmp_path):
    figures = [
        {"id": f"F{number}", "label": label, "value": 1}
        for number, label in enumerate(
            (
                "Spots of my pick",
                "Length of the spots of my pick",
                "Safety score of my pick without its spots",
                "Safety score of my pick with every work built",
            ),
            300,
        )
    ]
    driver = open_page(shown(tmp_path, data_for(), figures=figures))
    try:
        links = driver.find_elements(By.CSS_SELECTOR, "#spot-p a.fig")
        assert [link.get_attribute("href").split("#")[1] for link in links] == [
            "F300",
            "F301",
            "F302",
            "F303",
        ]
    finally:
        driver.quit()


def test_fr20_13_the_list_shows_at_most_ten_ranked_by_trips_and_counts_the_rest(tmp_path):
    driver = open_page(shown(tmp_path, data_for(options=[many_spots(10)])))
    try:
        items = texts(driver, "#spotlist li")
        assert len(items) == 10
        trips = [int(item.split("\n")[-2]) for item in items]
        assert trips == sorted(trips, reverse=True)
        assert items[0].split("\n")[1] == "Spot 0 Road"
        assert (
            driver.find_element(By.ID, "spotmore").text
            == "And 2 more spots that hold back fewer trips."
        )
    finally:
        driver.quit()


def test_fr20_15_each_plan_card_credits_its_source_by_title_date_and_link(tmp_path):
    routes, _ = report_with_areas()
    block = council_block() | {"routes": routes}
    block["source"] = block["source"] | {"read_on": "2026-10-17"}
    driver = open_page(shown(tmp_path, data_for(council=block)))
    try:
        council = driver.find_element(By.ID, "card-council")
        link = council.find_element(By.CSS_SELECTOR, "a.src")
        assert link.get_attribute("href") == "https://x.test/"
        assert "Plan" in link.text
        assert "2026-10-17" in council.find_element(By.CSS_SELECTOR, ".credit").text
        corridors = driver.find_element(By.ID, "card-tfnsw")
        link = corridors.find_element(By.CSS_SELECTOR, "a.src")
        assert link.get_attribute("href") == CORRIDOR["source"]["url"] + "/"
        assert link.text == CORRIDOR["source"]["title"]
        assert CORRIDOR["source"]["date"] in corridors.find_element(By.CSS_SELECTOR, ".credit").text
    finally:
        driver.quit()


def test_fr20_16_the_two_stages_sit_side_by_side_with_the_stage_values(tmp_path):
    driver = open_page(shown(tmp_path, data_for(rates=load_rates())))
    try:
        rows = {
            row.find_element(By.TAG_NAME, "th").text: [
                cell.text for cell in row.find_elements(By.TAG_NAME, "td")
            ]
            for row in driver.find_elements(By.CSS_SELECTOR, "#compare tbody tr")
        }
        heads = driver.find_elements(By.CSS_SELECTOR, "#compare thead th")
        assert [item.get_attribute("textContent") for item in heads][1:] == [
            "First stage",
            "Full plan",
        ]
        assert rows["Rough cost"] == ["$1 to 2 million", "$2 to 4 million"]
        assert rows["Parking spaces that change"] == ["4", "10"]
        assert rows["Places with an all-ages ride"] == ["1 of 3", "3 of 3"]
        assert rows["Trips that are all-ages"] == ["50%", "90%"]
        assert "rough cost from 2025 Victorian rates" in driver.find_element(By.ID, "cost").text
    finally:
        driver.quit()


def test_fr20_16_no_cost_data_leaves_out_the_cost_section():
    from tests.test_report_page import parse

    assert "cost" not in parse(page_for(data_for())).ids
    assert "cost" in parse(page_for(data_for(rates=load_rates()))).ids


def test_fr20_17_three_asks_each_within_25_words(tmp_path):
    driver = open_page(shown(tmp_path, data_for()))
    try:
        asks = texts(driver, "#asks li")
        assert len(asks) == 3
        assert all(words(ask) <= 25 for ask in asks)
        assert "bike network plan" in asks[0]
        assert "Fund the design of the first stage" in asks[1]
        assert "Ash Street" in asks[1]
        assert STATE in asks[2]
        assert "state roads" in asks[2]
        assert "Three steps" in driver.find_element(By.ID, "ask-h").text
    finally:
        driver.quit()


def test_fr20_17_the_second_ask_names_at_most_ten_streets_and_counts_the_rest(tmp_path):
    names = [f"Street{letter}" for letter in "ABCDEFGHIJKL"]
    driver = open_page(shown(tmp_path, data_for(options=[many_streets(names)])))
    try:
        ask = texts(driver, "#asks li")[1]
        named = [name for name in [*names, "Ash Street"] if name in ask]
        assert len(named) == 10
        assert named == [*names[:9], "Ash Street"]
        assert "and 3 more streets" in ask
        assert words(ask) <= 25
    finally:
        driver.quit()


def test_fr20_17_long_street_names_are_cut_to_stay_within_25_words(tmp_path):
    names = [f"Alexander Hamilton Memorial Drive {letter}" for letter in "ABCDEFGHIJKL"]
    driver = open_page(shown(tmp_path, data_for(options=[many_streets(names)])))
    try:
        ask = texts(driver, "#asks li")[1]
        assert words(ask) <= 25
        named = sum(name in ask for name in [*names, "Ash Street"])
        rest = int(re.search(r"and (\d+) more streets", ask).group(1))
        assert named >= 1
        assert named + rest == 13
    finally:
        driver.quit()


def test_fr20_17_no_state_road_spot_means_no_third_ask(tmp_path):
    found = pick()
    found["works"][2]["owner"] = None
    driver = open_page(shown(tmp_path, data_for(options=[found])))
    try:
        asks = texts(driver, "#asks li")
        assert len(asks) == 2
        assert not [ask for ask in asks if STATE in ask]
    finally:
        driver.quit()


def ward_data():
    routes, areas = report_with_areas()
    for area in areas:
        area |= {
            "top": ["Ash Street", "Bay Street", "Cook Street"],
        }
    areas[0]["safe"] = {"schools": [0, 1, 2], "stations": [0, 0, 1], "centres": [0, 1, 1]}
    areas[1]["safe"] = {"schools": [0, 1, 2], "stations": [0, 0, 0], "centres": [0, 0, 1]}
    return data_for(council=council_block() | {"routes": routes}, areas=areas)


def test_fr20_14_a_ward_card_has_its_top_streets_and_safe_places_in_40_words(tmp_path):
    driver = open_page(shown(tmp_path, ward_data()))
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, "#wardcards .ward")
        assert len(cards) == 2
        safes = ["Safe trip to 4 of 7 places", "Safe trip to 3 of 3 places"]
        for card, safe in zip(cards, safes, strict=True):
            assert "Ash Street, Bay Street, Cook Street" in card.text
            assert safe in card.text
            assert words(card.text) <= 40
    finally:
        driver.quit()


def test_fr20_14_the_ward_card_drops_suburbs_when_it_would_pass_40_words(tmp_path):
    data = ward_data()
    for ward in data["wards"]:
        ward["top"] = ["Alexander Hamilton Memorial Drive", "Bay Street", "Cook Street"]
    data["subs"] = {
        ward["name"]: ["Alpha Beach", "Beta Bay", "Gamma Heights"] for ward in data["wards"]
    }
    driver = open_page(shown(tmp_path, data))
    try:
        for card in driver.find_elements(By.CSS_SELECTOR, "#wardcards .ward"):
            assert words(card.text) <= 40
            assert "Alexander Hamilton Memorial Drive" in card.text
    finally:
        driver.quit()


def test_fr20_12_a_run_without_spots_has_no_spot_card(tmp_path):
    found = pick()
    found["works"] = found["works"][:1]
    found["steps"] = found["steps"][:2]
    found["lines"] = found["lines"][:2]
    driver = open_page(shown(tmp_path, data_for(options=[found])))
    try:
        assert texts(driver, "#fixes .fix h3") == [QUIET]
    finally:
        driver.quit()
