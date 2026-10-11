import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

out = Path("/tmp/bikeplan-Q1.6-page-sheets")
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
            for media in ("screen", "print"):
                browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
                for width in (390, 1280):
                    browser.set_window_size(width, 900)
                    assert browser.execute_script(
                        "return document.documentElement.scrollWidth <= window.innerWidth"
                    )
                    browser.execute_script(
                        "document.getElementById('selected-projects').scrollIntoView()"
                    )
                    browser.save_screenshot(str(proof / f"page-sheets-{media}-{width}.png"))
            cases.append(
                {
                    "identity": identity,
                    "project_ids": expected,
                    "element_ids": package["element_ids"],
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
outputs = []
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    outputs.append({"path": name, "sha256": digest})
saved = {
    "build_command": (
        "/usr/bin/time -v -o /tmp/q16-page-sheets-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.6-page-sheets"
    ),
    "check_command": "uv run --frozen python artifacts/Q1.6/collect_page_sheets.py",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "snapshot": record["snapshot"],
    "code": record["code"],
    "input_hashes": record["input_hashes"],
    "report_bytes": (out / "report.html").stat().st_size,
    "cases": cases,
    "outputs": outputs,
    "scope": (
        "Selected curve list and sheets only. Empty real curves prove honest empty selection, "
        "not local works or field safety. Two disconnected test-only grids prove nonempty "
        "rank selection and sheet plans. Goal/stage packages and full browser acceptance "
        "remain open. This run does not prove performance."
    ),
}
(proof / "archive-page-sheets.json").write_text(json.dumps(saved, sort_keys=True, indent=2) + "\n")
shutil.copyfile("/tmp/q16-page-sheets-time.txt", proof / "page-sheets-time-full.txt")
print("Fresh offline list and sheets agree with selected packages; output hashes match")
