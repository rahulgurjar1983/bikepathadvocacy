import networkx as nx
from selenium.webdriver.common.by import By
from shapely.geometry import box

from bikeplan.config import load_profile
from bikeplan.cost import load_rates
from tests.test_council_plan import council_block, report_with_areas
from tests.test_report_page import data_for, open_page, page_for
from tests.test_story_parts import words

PROFILE = load_profile("au-nsw")


def parked_graph():
    graph = nx.MultiDiGraph(boundary=box(-10, -10, 2000, 2000), crs="EPSG:32756")
    for node, x in enumerate((0, 600, 900, 1500)):
        graph.add_node(node, x=float(x), y=0.0)
    edges = [
        (0, 1, {"parking:both": "lane", "bike_ok": True, "segment_id": 1}),
        (
            1,
            2,
            {"parking:left": "lane", "parking:right": "no", "bike_ok": True, "segment_id": 2},
        ),
        (2, 3, {"parking:both": "lane", "bike_ok": False, "segment_id": 3}),
    ]
    for u, v, data in edges:
        graph.add_edge(u, v, **data)
    return graph


def test_fr20_16_the_street_parking_total_counts_parked_kerbs_on_the_modelled_streets():
    from bikeplan.report import street_parking

    assert street_parking(parked_graph(), PROFILE) == 175


def test_fr20_16_each_stage_parking_cell_gives_its_share_of_the_street_parking_counted(tmp_path):
    path = tmp_path / "report.html"
    path.write_text(page_for(data_for(parking_total=100, rates=load_rates())))
    driver = open_page(path)
    try:
        cells = {
            row.find_element(By.TAG_NAME, "th").text: [
                cell.text for cell in row.find_elements(By.TAG_NAME, "td")
            ]
            for row in driver.find_elements(By.CSS_SELECTOR, "#compare tbody tr")
        }
        assert cells["Parking spaces that change"] == ["4 (4%)", "10 (10%)"]
        assert "100 street parking spaces" in driver.find_element(By.ID, "cost-note").text
    finally:
        driver.quit()


def test_fr20_15_each_plan_card_gives_two_short_lines_and_one_bar(tmp_path):
    path = tmp_path / "report.html"
    routes, _ = report_with_areas()
    path.write_text(page_for(data_for(council=council_block() | {"routes": routes})))
    driver = open_page(path)
    try:
        for name in ("tfnsw", "council"):
            card = driver.find_element(By.ID, "card-" + name)
            lines = card.find_elements(By.CSS_SELECTOR, "p.line")
            assert len(lines) == 2
            assert all(0 < words(line.text) <= 25 for line in lines)
            assert len(card.find_elements(By.CSS_SELECTOR, ".meter")) == 1
        assert "2" in driver.find_element(By.CSS_SELECTOR, "#card-tfnsw p.line").text
        assert "%" in driver.find_element(By.CSS_SELECTOR, "#card-council p.line").text
    finally:
        driver.quit()
