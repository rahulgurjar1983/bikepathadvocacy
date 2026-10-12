import copy
import json

import pytest
from selenium.webdriver.common.by import By

from bikeplan.change import proposal_opening
from tests.test_proposal_opening_outcomes import Opening
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser
from tests.test_report_change import move


def values(package):
    works = package["works"]
    return {
        "protected": works["km_by_design"]["protected_cycleway"],
        "shared": works["km_by_design"]["shared_path"],
        "quiet": works["km_by_design"]["quiet_street"],
        "unclassified": sum(
            works["km_by_design"][key] for key in ("path_use_unknown", "design_unknown")
        ),
        "crossings": len(works["crossing_upgrades"]),
        "retained": works["existing_links_retained"]["length_m"] / 1000,
    }


def test_fr16_1_script_free_opening_works_read_record_with_figure_links(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    selected = copy.deepcopy(record["selected"])
    selected["works"]["km_by_design"].update(
        protected_cycleway=1.2345,
        shared_path=2.3456,
        quiet_street=3.4567,
        path_use_unknown=4.5678,
        design_unknown=5.6789,
    )
    selected["works"]["crossing_upgrades"] = ["crossing:a", "crossing:b"]
    selected["works"]["existing_links_retained"]["length_m"] = 1234.5
    page = Opening()
    page.feed(proposal_opening(frontier, selected=selected))
    for index, (key, value) in enumerate(values(selected).items(), 26):
        assert float(page.text[key]) == value
        assert page.links[key] == f"#F{index}"
    assert page.scripts == 0
    saved = Opening()
    saved.feed((built / "report.html").read_text())
    assert {key: float(saved.text[key]) for key in values(record["selected"])} == values(
        record["selected"]
    )


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_opening_works_match_saved_record_detailed_view_exports_and_print(
    browser, built, name
):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 2})
    changed["works"]["km_by_design"].update(
        protected_cycleway=1.2345,
        shared_path=2.3456,
        quiet_street=3.4567,
        path_use_unknown=4.5678,
        design_unknown=5.6789,
    )
    changed["works"]["crossing_upgrades"] = changed["works"]["crossing_upgrades"][1:]
    changed["works"]["existing_links_retained"]["length_m"] = 1234.5
    browser.execute_script(
        "const n=document.getElementById('package-export-data');"
        "const d=JSON.parse(n.textContent);d.packages[arguments[0]].record=arguments[1];"
        "n.textContent=JSON.stringify(d);",
        f"{name}:2",
        changed,
    )
    for rank in (0, 1, 2, 0):
        move(browser, rank)
        package = next(
            p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": rank}
        )
        for media in ("screen", "print"):
            browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
            assert (
                browser.find_element(By.ID, "opening").get_attribute("data-package")
                == f"{name}:{rank}"
            )
            for index, (key, value) in enumerate(values(package).items(), 26):
                element = browser.find_element(By.ID, f"opening-outcome-{key}")
                assert element.is_displayed()
                assert float(element.text) == value
                assert element.get_attribute("href").endswith(f"#F{index}")
            works = json.loads(browser.find_element(By.ID, "works-summary").text)
            assert values({"works": works}) == values(package)
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href)"
            ".then(r=>r.json()).then(arguments[0]);"
        )
        assert values(payload["selected"]) == values(package)
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
