import csv
import hashlib
import io
import json
import shutil
import subprocess
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def fields(record, prefix=""):
    result = {}
    for name, value in record.items():
        key = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            result.update(fields(value, key))
        else:
            result[key] = value
    return result


out = Path("/tmp/bikeplan-Q1.6-works-selection")
proof = Path("artifacts/Q1.6")
record = json.loads((out / "proposal.json").read_text())
frontier = json.loads((out / "frontier.json").read_text())
assert record["region"] == "au-nsw-bayside"
assert (out / "report.html").stat().st_size <= 8_000_000
options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
    options.add_argument(flag)
options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
cases = []
with webdriver.Chrome(options=options) as browser:
    browser.get((out / "report.html").resolve().as_uri())
    browser.implicitly_wait(5)
    for curve in frontier["scenarios"]:
        name = curve["id"]
        browser.find_element(By.ID, f"scenario-{name}").click()
        for rank in sorted({0, curve["recommended_stop"] or 0, len(curve["picks"]) - 1}):
            browser.execute_script(
                "const s=document.getElementById('change-slider');s.value=arguments[0];"
                "s.dispatchEvent(new Event('input',{bubbles:true}));",
                rank,
            )
            identity = {"scenario": name, "rank": rank}
            key = f"{name}:{rank}"
            package = next(p for p in record["packages"] if p["identity"] == identity)
            assert (
                browser.find_element(By.ID, "selected-projects").get_attribute("data-package")
                == key
            )
            assert browser.find_element(By.ID, "opening").get_attribute("data-package") == key
            assert key in browser.find_element(By.ID, "selected-package-label").text
            assert browser.find_element(By.ID, "report-map").get_attribute("data-package") == key
            assert key in browser.find_element(By.ID, "map-package-label").text
            assert browser.find_element(By.ID, "change-totals").get_attribute("data-package") == key
            works = package["works"]
            expected_summary = {
                field: works[field]
                for field in (
                    "unique_roads",
                    "distinct_sections",
                    "unnamed_roads",
                    "km_by_design",
                    "existing_links_retained",
                    "crossing_upgrades",
                    "parking_spaces",
                )
            } | {"gap_records": len(works["remaining_gaps"])}
            assert (
                browser.find_element(By.ID, "physical-works").get_attribute("data-package") == key
            )
            assert browser.find_element(By.ID, "works-package").text == key
            assert json.loads(browser.find_element(By.ID, "works-summary").text) == expected_summary
            expected_works = [section["id"] for section in works["sections"]] + works[
                "crossing_upgrades"
            ]
            rows = browser.find_elements(By.CSS_SELECTOR, "#works-rows tr")
            assert [row.get_attribute("data-work-id") for row in rows] == expected_works
            assert all(row.get_attribute("data-package") == key for row in rows)
            paths = browser.find_elements(By.CSS_SELECTOR, "#report-map .change-project")
            ids = [p.get_attribute("data-element-id") for p in paths]
            assert sorted(ids) == package["element_ids"]
            assert len(ids) == len(set(ids))
            assert all(p.get_attribute("data-package") == key for p in paths)
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
                assert float(cell.text) == round(value, digits)
            expected = [p["id"] for p in curve["picks"][1 : rank + 1]]
            assert sorted(expected) == package["project_ids"]
            for selector in ("#selected-project-list a", "#selected-project-sheets article"):
                items = browser.find_elements(By.CSS_SELECTOR, selector)
                assert [i.get_attribute("data-project-id") for i in items] == expected
            for article in browser.find_elements(
                By.CSS_SELECTOR, "#selected-project-sheets article"
            ):
                assert article.get_attribute("data-package") == key
                assert article.is_displayed()
            payload = browser.execute_async_script(
                "fetch(document.getElementById('package-export-json').href)"
                ".then(r=>r.json()).then(arguments[0]);"
            )
            assert payload["selected"] == package
            for field, metric in package["model_totals"].items():
                assert payload["curve_totals"][field] == metric["value"]
            WebDriverWait(browser, 10).until(
                lambda driver, package_key=key: (
                    driver.find_element(By.ID, "package-export-csv").get_attribute("data-package")
                    == package_key
                )
            )
            csv_text = browser.execute_async_script(
                "fetch(document.getElementById('package-export-csv').href)"
                ".then(r=>r.text()).then(arguments[0]);"
            )
            rows = list(csv.DictReader(io.StringIO(csv_text)))
            assert len({row["field"] for row in rows}) == len(rows)
            assert {row["field"]: json.loads(row["value_json"]) for row in rows} == fields(payload)
            for media in ("screen", "print"):
                browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
                assert browser.find_element(By.ID, "works-package").is_displayed()
                assert browser.find_element(By.ID, "works-package").text == key
                assert (
                    json.loads(browser.find_element(By.ID, "works-summary").text)
                    == expected_summary
                )
                assert [
                    row.get_attribute("data-work-id")
                    for row in browser.find_elements(By.CSS_SELECTOR, "#works-rows tr")
                ] == expected_works
                for width in (390, 1280):
                    browser.set_window_size(width, 900)
                    assert browser.execute_script(
                        "return document.documentElement.scrollWidth <= window.innerWidth"
                    )
                    browser.execute_script(
                        "document.getElementById('physical-works').scrollIntoView()"
                    )
                    browser.save_screenshot(str(proof / f"works-selection-{media}-{width}.png"))
            cases.append(
                {
                    "identity": identity,
                    "project_ids": expected,
                    "element_ids": package["element_ids"],
                    "works_summary": expected_summary,
                    "works_ids": expected_works,
                }
            )
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
options.add_argument("--blink-settings=scriptEnabled=false")
with webdriver.Chrome(options=options) as browser:
    browser.get((out / "report.html").resolve().as_uri())
    identity = record["selected"]["identity"]
    assert (
        browser.find_element(By.ID, "selected-projects").get_attribute("data-package")
        == f"{identity['scenario']}:{identity['rank']}"
    )
    assert (
        sorted(
            i.get_attribute("data-project-id")
            for i in browser.find_elements(By.CSS_SELECTOR, "#selected-project-sheets article")
        )
        == record["selected"]["project_ids"]
    )
    package = record["selected"]
    works = package["works"]
    expected_summary = {
        field: works[field]
        for field in (
            "unique_roads",
            "distinct_sections",
            "unnamed_roads",
            "km_by_design",
            "existing_links_retained",
            "crossing_upgrades",
            "parking_spaces",
        )
    } | {"gap_records": len(works["remaining_gaps"])}
    assert json.loads(browser.find_element(By.ID, "works-summary").text) == expected_summary
    assert (
        browser.find_element(By.ID, "physical-works").get_attribute("data-package")
        == f"{identity['scenario']}:{identity['rank']}"
    )
    assert [
        row.get_attribute("data-work-id")
        for row in browser.find_elements(By.CSS_SELECTOR, "#works-rows tr")
    ] == [section["id"] for section in works["sections"]] + works["crossing_upgrades"]
outputs = []
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    outputs.append({"path": name, "sha256": digest})
saved = {
    "build_command": (
        "/usr/bin/time -v -o /tmp/q16-works-selection-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.6-works-selection"
    ),
    "check_command": "uv run --frozen python artifacts/Q1.6/collect_works_selection.py",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "snapshot": record["snapshot"],
    "code": record["code"],
    "input_hashes": record["input_hashes"],
    "report_bytes": (out / "report.html").stat().st_size,
    "cases": cases,
    "outputs": outputs,
    "scope": (
        "Selected curve works summary and exact rows, map, totals, list, sheets "
        "and JSON/CSV exports. "
        "Empty real curves prove honest empty selection, "
        "not local works or field safety. Two disconnected test-only grids prove nonempty crossing "
        "rank selection and sheet plans. Goal/stage packages and full browser acceptance "
        "remain open. This run does not prove performance."
    ),
}
(proof / "archive-works-selection.json").write_text(
    json.dumps(saved, sort_keys=True, indent=2) + "\n"
)
shutil.copyfile("/tmp/q16-works-selection-time.txt", proof / "works-selection-time-full.txt")
print("Fresh offline works views agree with selected packages; output hashes match")
