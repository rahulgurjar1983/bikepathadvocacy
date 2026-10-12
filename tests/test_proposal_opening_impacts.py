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
    return {
        "roads": package["works"]["unique_roads"],
        "parking": package["impacts"]["parking_spaces"]["removed"]["known_subtotal"],
    }


def test_fr16_1_script_free_opening_impacts_use_saved_record_and_keep_limits(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    selected = copy.deepcopy(record["selected"])
    selected["works"]["unique_roads"] = 17
    loss = selected["impacts"]["parking_spaces"]["removed"]
    loss.update(value=None, known_subtotal=12.345, reason="Unknown bay <script>unsafe</script>")
    page = Opening()
    page.feed(proposal_opening(frontier, selected=selected))
    assert {key: float(page.text[key]) for key in values(selected)} == values(selected)
    assert page.links["roads"] == "#F14"
    assert page.links["parking"] == "#F23"
    assert page.text["parking-reason"] == loss["reason"]
    assert page.scripts == 0
    loss.update(value=12.345, reason=None)
    complete = Opening()
    complete.feed(proposal_opening(frontier, selected=selected))
    assert complete.text["parking-reason"] == ""
    selected["works"]["unique_roads"] = None
    loss.update(known_subtotal=None, reason="Loss not yet built")
    missing = Opening()
    missing.feed(proposal_opening(frontier, selected=selected))
    assert missing.text["roads"] == "unknown"
    assert missing.text["parking"] == "unknown"
    assert missing.text["parking-reason"] == loss["reason"]
    saved = Opening()
    saved.feed((built / "report.html").read_text())
    assert {key: float(saved.text[key]) for key in values(record["selected"])} == values(
        record["selected"]
    )


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_opening_impacts_follow_record_exports_and_print(browser, built, name):
    record = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, f"scenario-{name}").click()
    changed = next(p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": 2})
    changed["works"]["unique_roads"] = 17
    changed["impacts"]["parking_spaces"]["removed"].update(
        value=None, known_subtotal=12.345, reason="Unknown bay <script>unsafe</script>"
    )
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
            for key, value in values(package).items():
                element = browser.find_element(By.ID, f"opening-outcome-{key}")
                assert element.is_displayed()
                assert element.text == ("unknown" if value is None else str(value))
                assert element.get_attribute("href").endswith("#F14" if key == "roads" else "#F23")
            loss = package["impacts"]["parking_spaces"]["removed"]
            reason = browser.find_element(By.ID, "opening-outcome-parking-reason")
            assert reason.text == (loss["reason"] if loss["value"] is None else "")
            assert not reason.find_elements(By.TAG_NAME, "script")
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
        payload = browser.execute_async_script(
            "fetch(document.getElementById('package-export-json').href)"
            ".then(r=>r.json()).then(arguments[0]);"
        )
        assert values(payload["selected"]) == values(package)
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
