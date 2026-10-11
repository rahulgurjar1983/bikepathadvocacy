import csv
import io
import json
import time

import pytest
from selenium.webdriver.common.by import By

from tests.test_report_change import browser as browser
from tests.test_report_change import built as built
from tests.test_report_change import frontier as frontier
from tests.test_report_change import move, scenario, shown, step_value


def leaves(record, prefix=""):
    result = {}
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(leaves(value, path))
        else:
            result[path] = value
    return result


def download(browser, folder, kind, identity):
    browser.execute_cdp_cmd(
        "Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(folder)}
    )
    links = browser.find_elements(By.ID, f"package-export-{kind}")
    assert links, f"The selected package needs an offline {kind} export"
    link = links[0]
    name = f"proposal-{identity['scenario']}-{identity['rank']}.{kind}"
    assert link.get_attribute("download") == name
    assert link.get_attribute("data-package") == f"{identity['scenario']}:{identity['rank']}"
    path = folder / name
    path.unlink(missing_ok=True)
    link.click()
    end = time.monotonic() + 10
    while not path.exists() and time.monotonic() < end:
        time.sleep(0.05)
    return path.read_text()


@pytest.mark.parametrize("name", ["light", "heavy"])
def test_fr15_2_offline_exports_follow_baseline_and_selected_rank(
    browser, built, frontier, tmp_path, name
):
    archive = json.loads((built / "proposal.json").read_text())
    chosen = scenario(frontier, name)
    assert len(chosen["picks"]) >= 2
    browser.find_element(By.ID, f"scenario-{name}").click()
    for rank in (0, 1, 0):
        move(browser, rank)
        identity = {"scenario": name, "rank": rank}
        exported = json.loads(download(browser, tmp_path, "json", identity))
        expected = next(p for p in archive["packages"] if p["identity"] == identity)
        assert exported["selected"] == expected
        assert exported["curve_totals"] == chosen["picks"][rank]
        assert browser.find_element(By.ID, "opening").get_attribute("data-package") == (
            f"{name}:{rank}"
        )
        for key, value in shown(browser).items():
            assert value == pytest.approx(step_value(exported["curve_totals"], key))
        assert expected["project_ids"] == sorted(p["id"] for p in chosen["picks"][1 : rank + 1])
        assert expected["element_ids"] == sorted(
            {e["id"] for s in chosen["project_sheets"][:rank] for e in s["elements"]}
        )


def test_fr16_1_csv_and_json_keep_provenance_full_precision_and_unknowns(
    browser, built, frontier, tmp_path
):
    archive = json.loads((built / "proposal.json").read_text())
    browser.find_element(By.ID, "scenario-shipped").click()
    rank = len(scenario(frontier, "shipped")["picks"]) - 1
    move(browser, rank)
    identity = {"scenario": "shipped", "rank": rank}
    exported = json.loads(download(browser, tmp_path, "json", identity))
    for key in ("schema_version", "region", "snapshot", "code", "input_hashes"):
        assert exported[key] == archive[key]
    assert exported["selected"]["metrics"]["capital_cost"]["value"] is None
    assert exported["selected"]["metrics"]["capital_cost"]["reason"]
    rows = list(csv.DictReader(io.StringIO(download(browser, tmp_path, "csv", identity))))
    assert len({r["field"] for r in rows}) == len(rows)
    assert {row["field"]: json.loads(row["value_json"]) for row in rows} == leaves(exported)
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
