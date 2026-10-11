import json

import pytest
from selenium.webdriver.common.by import By

from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser
from tests.test_report_change import move

TOTAL_KEYS = (
    "score",
    "disruption",
    "parking_spaces",
    "lane_km",
    "speed_km",
    "signals",
    "refuges",
    "km_by_fix",
    "unique_people",
    "unique_people_by_type",
    "gains_by_type",
)


def test_fr16_1_saved_model_totals_have_full_precision_units_scope_and_sources(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    for package in record["packages"]:
        identity = package["identity"]
        curve = next(c for c in frontier["scenarios"] if c["id"] == identity["scenario"])
        pick = curve["picks"][identity["rank"]]
        assert set(package["model_totals"]) == set(TOTAL_KEYS)
        for key in TOTAL_KEYS:
            metric = package["model_totals"][key]
            assert metric["value"] == pick[key]
            assert metric["scope"] == {"region": record["region"], "package": identity}
            assert metric["source"] == package["evidence"]
            assert metric["unit"] and metric["method"]
            assert metric["evidence_status"] == "modelled"
        assert (
            package["model_totals"]["score"]["value"] == package["metrics"]["access_score"]["value"]
        )


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_map_opening_and_totals_use_saved_package_offline(browser, built, name):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 1})
    changed["model_totals"]["score"]["value"] = 12.345678901
    changed["metrics"]["access_score"]["value"] = 12.345678901
    browser.execute_script(
        "const node=document.getElementById('package-export-data');"
        "const data=JSON.parse(node.textContent);"
        "data.packages[arguments[0]].record=arguments[1];"
        "node.textContent=JSON.stringify(data);",
        f"{name}:1",
        changed,
    )
    for rank in (0, 1, 2, 0):
        move(browser, rank)
        identity = {"scenario": name, "rank": rank}
        package = next(p for p in record["packages"] if p["identity"] == identity)
        key = f"{name}:{rank}"
        assert browser.find_element(By.ID, "report-map").get_attribute("data-package") == key
        assert key in browser.find_element(By.ID, "map-package-label").text
        assert browser.find_element(By.ID, "change-totals").get_attribute("data-package") == key
        paths = browser.find_elements(By.CSS_SELECTOR, "#report-map .change-project")
        ids = [p.get_attribute("data-element-id") for p in paths]
        assert sorted(ids) == package["element_ids"]
        assert len(ids) == len(set(ids))
        assert all(p.get_attribute("data-package") == key for p in paths)
        assert {p.get_attribute("data-project-id") for p in paths} <= set(package["project_ids"])
        for cell in browser.find_elements(
            By.CSS_SELECTOR,
            "#change-totals [data-total], #change-totals [data-measure], [data-opening]",
        ):
            measure = (
                cell.get_attribute("data-opening")
                or cell.get_attribute("data-measure")
                or cell.get_attribute("data-total")
            )
            kind, _, part = measure.partition(".")
            field = {"people": "unique_people_by_type", "km": "km_by_fix"}.get(kind, kind)
            value = package["model_totals"][field]["value"]
            if part:
                value = value.get(part, 0)
            digits = (
                0
                if field
                in ("parking_spaces", "unique_people", "unique_people_by_type", "gains_by_type")
                else 3
                if field in ("km_by_fix", "lane_km", "speed_km")
                else 1
            )
            assert float(cell.text) == pytest.approx(round(value, digits), abs=10**-digits)
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href)"
            ".then(r=>r.json()).then(arguments[0]);"
        )
        assert payload["selected"] == package
        for field in TOTAL_KEYS:
            assert payload["curve_totals"][field] == package["model_totals"][field]["value"]
        assert (
            "Old minimum-gain shortlist"
            in browser.find_element(By.CSS_SELECTOR, "label:has(#layer-proposed)").text
        )
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
