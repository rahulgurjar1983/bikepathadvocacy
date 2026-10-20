import pytest
from selenium.webdriver.common.by import By

from bikeplan.ladder import build_ladder, link_fixes
from tests.test_option_ladder import people
from tests.test_report_page import data_for, open_page, page_for, pick
from tests.test_spots import PROFILE, WEIGHTS, along_world, row


def spot_world():
    graph, table, fits = along_world(80.0, 2.5)
    table[2, 3, 0] = row(all_ages=False, length=80.0)
    fits["calm-e"] = {"status": "fix", "fix": "road_diet"}
    fixes = link_fixes(graph, table, fits, PROFILE, WEIGHTS)
    return table, fixes


def ladder_for():
    table, fixes = spot_world()
    return build_ladder(
        table, sorted(table), people((1, 0), (2, 0), (3, 2), (4, 3)), fixes, WEIGHTS
    )


def test_fr20_13_the_score_without_spots_is_recomputed_over_all_trips():
    ladder = ladder_for()
    assert ladder["no_spots"] == pytest.approx(100 / 3)
    assert ladder["ceiling"] == pytest.approx(100.0)
    assert all(
        ladder["no_spots"] != pytest.approx(step["totals"]["score"]) for step in ladder["steps"]
    )


def test_fr20_13_a_spots_trips_are_the_safe_trips_that_pass_through_it():
    works = ladder_for()["works"]
    by_fix = {work["fix"]: work for work in works}
    assert by_fix["short_path_crossing"]["trips"] == 4
    assert "trips" not in by_fix["road_diet"]


def variant():
    found = pick()
    found["works"][1]["fix"] = "short_path_crossing"
    found["works"][1]["trips"] = 1
    return found


def test_fr20_13_the_page_data_holds_the_score_before_the_spots_and_each_spots_trips():
    data = data_for(options=[variant()])
    assert data["before_spots"] == 40.0
    assert [(s["street"], s["kind"], s["trips"]) for s in data["spots"]] == [
        ("Forest Road", "signals", 6),
        ("Bay Street", "path", 1),
    ]


def test_fr20_13_the_page_reads_the_score_before_the_spots_each_spots_fix_and_one_trip(tmp_path):
    path = tmp_path / "report.html"
    path.write_text(page_for(data_for(options=[variant()])))
    driver = open_page(path)
    try:
        text = driver.find_element(By.ID, "spots").text
        assert "Street changes alone make 40%" in text
        assert "Short path and crossing" in text
        assert "Raised zebra crossing" not in text
        assert "1\ntrip" in text
        assert "1\ntrips" not in text
        assert "6\ntrips" in text
    finally:
        driver.quit()
