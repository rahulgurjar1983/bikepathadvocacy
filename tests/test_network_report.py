import re

import pytest
from bikeplan.network_report import choose, network_report, tenths
from selenium import webdriver
from selenium.webdriver.common.by import By

COLOURS = {"today": "#2e7d32", "made": "#1b5e8a", "still": "#a01010"}


def step(number, score, spent, works=(), safe=0, places=0):
    return {
        "step": number,
        "works": list(works),
        "totals": {
            "trips": 10,
            "safe_trips": safe,
            "score": score,
            "km_by_level": {1: 1.0, 2: 0.0, 3: 0.0, 4: 0.0},
            "km_all_ages": 1.0,
            "places_safe": {"school": places},
            "assumed_share": 0.5,
        },
        "disruption": {
            "parking_spaces": spent,
            "lane_km": 0.0,
            "speed_km": 0.0,
            "path_km": 0.0,
            "score": spent,
        },
    }


def work(street, spent, fix="road_diet"):
    return {
        "street": street,
        "fix": fix,
        "km": 0.2,
        "parking_spaces": int(spent),
        "lane_km": 0.0,
        "speed_km": 0.0,
        "path_km": 0.0,
        "score": spent,
        "links": [[0, 1, 0]],
    }


def option(name, scores, spends, streets, lines=(), no_fix=(), same_as=None):
    steps = [step(0, scores[0], spends[0], safe=0)]
    for index in range(1, len(scores)):
        steps.append(step(index, scores[index], spends[index], [index - 1], safe=index))
    return {
        "id": name.lower().split()[0],
        "name": name,
        "same_as": same_as,
        "km": 3.0,
        "steps": steps,
        "works": [work(street, spends[i + 1] - spends[i]) for i, street in enumerate(streets)],
        "no_fix": list(no_fix),
        "lines": list(lines),
        "unjoined": [],
    }


def calm(lines=()):
    return option(
        "Calm streets", [0, 40, 80, 100], [0, 2, 5, 10], ["Ash St", "Elm St", "Oak St"], lines
    )


def shortest(top=95.0, lines=()):
    return option("Shortest", [0, 50, 90, top], [0, 1, 3, 4], ["Bay St", "Elm St", "Fir St"], lines)


def test_fr17_8_pick_is_the_highest_final_score():
    result = choose([calm(), shortest(95.0)], 0.9)
    assert result["pick"] == "calm"


def test_fr17_8_pick_within_one_point_takes_the_less_disruptive_option():
    result = choose([calm(), shortest(99.5)], 0.9)
    assert result["pick"] == "shortest"


def test_fr17_8_recommended_step_is_the_first_to_reach_the_share_of_the_gain():
    assert choose([calm()], 0.9)["step"] == 3
    assert choose([calm()], 0.8)["step"] == 2
    assert choose([calm()], 0.4)["step"] == 1
    assert choose([shortest(99.5)], 0.9)["step"] == 2


def test_fr17_8_ask_names_the_streets_of_the_works_up_to_the_step():
    result = choose([shortest(99.5)], 0.9)
    assert result["streets"] == ["Bay St", "Elm St"]
    assert "Bay St" in result["ask"]
    assert "Elm St" in result["ask"]
    assert "Fir St" not in result["ask"]
    assert "bike network plan" in result["ask"]


def test_fr17_8_an_option_with_no_gain_recommends_step_zero():
    flat = option("Flat", [10, 10], [0, 0], ["Ash St"])
    result = choose([flat], 0.9)
    assert result["step"] == 0
    assert result["streets"] == []


def test_fr17_8_the_opening_lists_every_option_with_its_numbers():
    head, body = network_report([calm(), shortest(95.0)], 0.9)
    opening = body.split('id="map"')[0]
    for text in ("Calm streets", "Shortest", "My pick", "My ask"):
        assert text in opening
    assert "100.0" in opening
    assert "95.0" in opening


def test_fr17_8_a_second_equal_option_reads_same_as_the_first():
    twin = shortest()
    twin["id"], twin["name"], twin["same_as"] = "mesh", "Mesh", "shortest"
    head, body = network_report([shortest(), twin], 0.9)
    assert "same as Shortest" in body


def test_fr17_8_the_report_follows_the_spec_17_order():
    head, body = network_report([calm(), shortest()], 0.9)
    marks = ['id="options"', 'id="map"', 'id="chart"', 'id="works"', 'id="no-fix"', 'id="quality"']
    spots = [body.index(mark) for mark in marks]
    assert spots == sorted(spots)


def test_fr17_10_tenths_hold_the_best_score_within_each_tenth_of_the_disruption():
    rows = tenths(calm())
    assert len(rows) == 11
    assert rows[0] == {"share": 0, "spent": 0.0, "score": 0}
    assert rows[2]["score"] == 40
    assert rows[5]["score"] == 80
    assert rows[10] == {"share": 100, "spent": 10.0, "score": 100}


def test_fr17_10_the_chart_has_one_line_per_option_and_the_dot_at_the_step():
    head, body = network_report([calm(), shortest()], 0.9)
    chart = body.split('id="chart"')[1].split('id="works"')[0]
    assert len(re.findall(r"<polyline", chart)) == 2
    assert 'id="chart-dot"' in chart
    assert "<table" in chart
    assert chart.count("<tr>") >= 11


def test_fr17_11_the_report_holds_no_survey_text():
    lines = [{"work": None, "ok": True, "line": [[151.0, -33.0], [151.001, -33.0]]}]
    head, body = network_report([calm(lines), shortest()], 0.9)
    assert "survey" not in (head + body).lower()


def test_fr17_5_no_fix_links_are_listed_by_option_and_street():
    gap = {"street": "Rail Rd", "links": [[1, 2, 0]], "km": 0.4}
    head, body = network_report(
        [option("Calm streets", [0, 50], [0, 1], ["Ash St"], no_fix=[gap])], 0.9
    )
    section = body.split('id="no-fix"')[1].split('id="quality"')[0]
    assert "Rail Rd" in section
    assert "Calm streets" in section


def test_fr17_6_works_of_the_pick_are_listed_by_street_to_the_recommended_step():
    head, body = network_report([shortest(99.5)], 0.9)
    section = body.split('id="works"')[1].split('id="no-fix"')[0]
    assert "Bay St" in section
    assert "Elm St" in section
    assert "Fir St" not in section


LINES = {
    "calm": [
        {"work": None, "ok": True, "line": [[151.000, -33.000], [151.001, -33.000]]},
        {"work": 0, "ok": False, "line": [[151.001, -33.000], [151.002, -33.000]]},
        {"work": 1, "ok": False, "line": [[151.002, -33.000], [151.003, -33.000]]},
        {"work": None, "ok": False, "line": [[151.003, -33.000], [151.004, -33.000]]},
    ],
    "shortest": [
        {"work": 0, "ok": False, "line": [[151.000, -33.001], [151.001, -33.001]]},
    ],
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    head, body = network_report([calm(LINES["calm"]), shortest(95.0, LINES["shortest"])], 0.9)
    path = tmp_path_factory.mktemp("network") / "report.html"
    path.write_text(f"<!DOCTYPE html><html><head>{head}</head><body>{body}</body></html>")
    return path


def open_page(path, scripts=True):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    if not scripts:
        options.add_experimental_option(
            "prefs", {"profile.managed_default_content_settings.javascript": 2}
        )
    driver = webdriver.Chrome(options=options)
    driver.get(path.resolve().as_uri())
    driver.implicitly_wait(5)
    return driver


@pytest.fixture(scope="module")
def browser(built):
    driver = open_page(built)
    yield driver
    driver.quit()


def states(browser):
    return browser.execute_script(
        "return Array.from(document.querySelectorAll('#network-map path[data-state]'))"
        ".map(p => [p.getAttribute('data-state'), p.getAttribute('stroke')])"
    )


def set_step(browser, value):
    browser.execute_script(
        "const s = document.getElementById('disruption-slider');"
        f"s.value = {value}; s.dispatchEvent(new Event('input'));"
    )


def test_fr17_9_the_switch_opens_on_the_pick_and_the_slider_on_the_recommended_step(browser):
    assert browser.find_element(By.ID, "option-calm").is_selected()
    assert browser.find_element(By.ID, "disruption-slider").get_attribute("value") == "3"


def test_fr17_9_the_slider_changes_the_styles_and_totals_to_the_saved_step_values(browser):
    set_step(browser, 1)
    assert [state for state, _ in states(browser)] == ["today", "made", "still", "still"]
    assert "40.0" in browser.find_element(By.ID, "step-totals").text
    set_step(browser, 3)
    assert [state for state, _ in states(browser)] == ["today", "made", "made", "still"]
    assert [colour for _, colour in states(browser)][:2] == [COLOURS["today"], COLOURS["made"]]
    assert "100.0" in browser.find_element(By.ID, "step-totals").text


def test_fr17_9_the_switch_changes_the_drawn_links(browser):
    browser.find_element(By.ID, "option-shortest").click()
    assert len(states(browser)) == 1
    assert "Shortest" in browser.find_element(By.ID, "step-totals").text
    browser.find_element(By.ID, "option-calm").click()
    assert len(states(browser)) == 4


def test_fr17_9_the_page_makes_no_network_call(browser):
    logs = [e for e in browser.get_log("browser") if "ERR_" in e["message"]]
    assert logs == []


def test_fr17_10_with_scripts_off_the_opening_table_and_step_totals_show(built):
    driver = open_page(built, scripts=False)
    try:
        text = driver.find_element(By.TAG_NAME, "body").text
        assert "My pick" in text
        assert "Calm streets" in text
        assert driver.find_element(By.ID, "step-totals").is_displayed()
        assert len(driver.find_elements(By.CSS_SELECTOR, "#chart table tr")) >= 11
    finally:
        driver.quit()
