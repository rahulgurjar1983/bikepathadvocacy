import json
import re

import pytest
from selenium.webdriver.common.by import By
from shapely.geometry import box

from bikeplan.config import load_region
from bikeplan.edition import edition, edition_page, street_overlay
from bikeplan.options import Joined
from bikeplan.report import figure_list, model_data, model_segment_rows, segment_rows, segments_text
from tests.test_checks_opening import OLD, REGION
from tests.test_edition_browser import open_page
from tests.test_network_report import calm, shortest
from tests.test_overlays import LINES, PIECES, four, toggle
from tests.test_safety_evidence import PROFILE, path_graph


def unknown_width_graph():
    graph = path_graph(width=None)
    graph.graph.update(crs="EPSG:32756", boundary=box(-10, -10, 110, 10))
    graph[1][2][0]["length_m"] = 100.0
    return graph


def test_fr20_1_model_rows_rate_an_unknown_width_path_all_ages_while_confirmed_rows_do_not():
    graph = unknown_width_graph()
    assert segment_rows(graph, PROFILE, {})[0][3] == 0
    rows = model_segment_rows(graph, PROFILE)
    assert rows[0][:2] == ["path", "100.000"]
    assert rows[0][3] == 1


def test_fr20_1_model_pieces_carry_model_all_ages_and_a_modelled_km_total():
    graph = unknown_width_graph()
    result = model_data(graph, model_segment_rows(graph, PROFILE))
    assert [item["model_all_ages"] for item in result["pieces"]] == [True]
    assert all("aaa" not in item for item in result["pieces"])
    assert result["km"] == {"aaa": 0.1}


def test_fr20_1_the_overlay_keeps_confirmed_pieces_and_adds_the_modelled_ones():
    rows = [["1", "1500.0", 1, 0], ["2", "500.0", 3, 0]]
    model = {
        "pieces": [{**PIECES[0], "model_all_ages": True}],
        "km": {"aaa": 2.0},
    }
    result = street_overlay(PIECES, rows, model)
    assert result["km"]["aaa"] == 0
    assert result["model_pieces"] == model["pieces"]
    assert result["model_km"] == {"aaa": 2.0}
    assert result["pieces"] == PIECES


def test_fr20_1_f2_is_labelled_as_the_confirmed_count():
    graph = unknown_width_graph()
    text = segments_text(segment_rows(graph, PROFILE, {}))
    label = next(item for item in figure_list(text, '{"segments": []}') if item["id"] == "F2")
    assert "confirmed" in label["label"].lower()
    assert "model" not in label["label"].lower()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    region = load_region(REGION)
    joined = Joined([], [], {"school": {"joined": 0, "unjoined": 0}})
    rows = [["1", "1000.0", 1, 0], ["2", "500.0", 3, 0]]
    model_pieces = [
        {**PIECES[0], "model_all_ages": True},
        {**PIECES[3], "model_all_ages": False},
    ]
    for item in model_pieces:
        del item["aaa"]
    model = {"pieces": model_pieces, "km": {"aaa": 1.0}}
    streets = street_overlay([{**item, "aaa": False} for item in PIECES], rows, model)
    options = [calm(LINES), shortest(95.0, LINES), four()[2], four()[3]]
    head, body, made, _ = edition(region, options, [], joined, 0.9, [OLD], streets)
    path = tmp_path_factory.mktemp("one-rating") / "report.html"
    path.write_text(edition_page(region, head, body, [OLD, *made], ""))
    return path


def test_fr20_1_the_page_data_holds_the_modelled_pieces_and_km(built):
    text = built.read_text()
    data = json.loads(re.search(r'id="network-data">(.*?)</script>', text, re.S).group(1))
    assert data["streets"]["model_km"] == {"aaa": 1.0}
    assert [item["model_all_ages"] for item in data["streets"]["model_pieces"]] == [True, False]


def test_fr20_1_the_all_ages_switch_follows_the_modelled_rating(built):
    driver = open_page(built, 1280)
    try:
        toggle(driver, "streets")
        toggle(driver, "aaa")
        drawn = driver.execute_script(
            "return Array.from(document.querySelectorAll('#network-map path.street-line'))"
            ".map(p => Number(p.getAttribute('data-level')))"
        )
        assert drawn == [1]
        assert driver.find_element(By.ID, "network-map")
    finally:
        driver.quit()


def test_fr20_1_the_five_minute_page_never_falls_back_to_the_confirmed_pieces():
    from tests.test_report_page import data_for

    confirmed = [
        {"name": "Ash Street", "aaa": True, "lines": [[[-33.91, 151.11], [-33.9, 151.12]]]}
    ]
    assert data_for(streets={"pieces": confirmed, "km": {"aaa": 9.0}})["streets"] == []
    modelled = [
        {"name": "Ash Street", "model_all_ages": True, "lines": [[[-33.8, 151.1], [-33.7, 151.2]]]}
    ]
    both = {"pieces": confirmed, "model_pieces": modelled, "model_km": {"aaa": 1.0}}
    assert data_for(streets=both)["streets"] == [[[151.1, -33.8], [151.2, -33.7]]]


def test_fr20_22_the_page_data_packs_each_modelled_street_as_whole_number_steps(built):
    text = built.read_text()
    data = json.loads(re.search(r'id="network-data">(.*?)</script>', text, re.S).group(1))
    packed = data["streets"]["model_pieces"]
    assert all("lines" not in item for item in packed)
    assert packed[0]["d"] == [[-3390000, 15115000, 0, 200]]
    assert packed[0]["model_all_ages"] is True
