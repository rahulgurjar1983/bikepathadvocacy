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


out = Path("/tmp/bikeplan-Q1.6-delivery-selection")
proof = Path("artifacts/Q1.6")
record = json.loads((out / "proposal.json").read_text())
frontier = json.loads((out / "frontier.json").read_text())
assert record["region"] == "au-nsw-bayside"
assert (out / "report.html").stat().st_size <= 8_000_000
options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
    options.add_argument(flag)
options.set_capability("goog:loggingPrefs", {"browser": "ALL"})


def check(browser, package):
    identity = package["identity"]
    key = f"{identity['scenario']}:{identity['rank']}"
    assert browser.find_element(By.ID, "delivery").get_attribute("data-package") == key
    label = browser.find_element(By.ID, "delivery-package")
    assert label.text == key
    link = label.find_element(By.XPATH, "ancestor::a[1]")
    assert link.get_attribute("href").split("#")[-1] == "F13"
    assert browser.find_elements(By.ID, "F13")
    for selector in ("delivery-choice", "opening-delivery"):
        view = browser.find_element(By.ID, selector)
        assert view.is_displayed()
        assert view.get_attribute("data-package") == key
        assert package["decision"]["ask"] in view.text
        for kind in ("capital", "upkeep"):
            cost = package["costs"][kind]
            assert cost["reason"] in view.text
            if cost["low"] is None:
                assert f"{kind.title()} cost: unknown" in view.text
            for group in cost["groups"]:
                assert str(group["low"]) in view.text
                assert str(group["high"]) in view.text
        for field in ("owner", "approvals", "funding"):
            if package[field]["value"] is None:
                assert f"{field.title()}: unknown" in view.text
    return key


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
            package = next(
                p for p in record["packages"] if p["identity"] == {"scenario": name, "rank": rank}
            )
            for media in ("screen", "print"):
                browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
                key = check(browser, package)
                for width in (390, 1280):
                    browser.set_window_size(width, 900)
                    assert browser.execute_script(
                        "return document.documentElement.scrollWidth <= window.innerWidth"
                    )
                    browser.execute_script("document.getElementById('delivery').scrollIntoView()")
                    browser.save_screenshot(str(proof / f"delivery-selection-{media}-{width}.png"))
            browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "screen"})
            payload = browser.execute_async_script(
                "fetch(document.getElementById('package-export-json').href).then(r=>r.json()).then(arguments[0]);"
            )
            assert payload["selected"] == package
            WebDriverWait(browser, 10).until(
                lambda driver, expected=key: (
                    driver.find_element(By.ID, "package-export-csv").get_attribute("data-package")
                    == expected
                )
            )
            csv_text = browser.execute_async_script(
                "fetch(document.getElementById('package-export-csv').href).then(r=>r.text()).then(arguments[0]);"
            )
            rows = list(csv.DictReader(io.StringIO(csv_text)))
            assert len({row["field"] for row in rows}) == len(rows)
            assert {row["field"]: json.loads(row["value_json"]) for row in rows} == fields(payload)
            cases.append(
                {
                    "identity": package["identity"],
                    "decision": package["decision"],
                    "costs": package["costs"],
                    "project_ids": package["project_ids"],
                }
            )
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
options.add_argument("--blink-settings=scriptEnabled=false")
with webdriver.Chrome(options=options) as browser:
    browser.get((out / "report.html").resolve().as_uri())
    for media in ("screen", "print"):
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
        check(browser, record["selected"])
outputs = []
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    outputs.append({"path": name, "sha256": digest})
saved = {
    "build_command": (
        "/usr/bin/time -v -o /tmp/q16-delivery-selection-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.6-delivery-selection"
    ),
    "check_command": "uv run --frozen python artifacts/Q1.6/collect_delivery_selection.py",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "snapshot": record["snapshot"],
    "code": record["code"],
    "input_hashes": record["input_hashes"],
    "report_bytes": (out / "report.html").stat().st_size,
    "cases": cases,
    "outputs": outputs,
    "scope": (
        "Selected curve delivery, opening, print and JSON/CSV exports; scripts-off default. "
        "Empty real packages prove honest unknowns, not useful works, known costs or funding. "
        "Nonempty fixture rank changes are unit-tested. Other shared views, goal/stage "
        "packages and full browser acceptance remain open. This is not performance proof."
    ),
}
(proof / "archive-delivery-selection.json").write_text(
    json.dumps(saved, sort_keys=True, indent=2) + "\n"
)
shutil.copyfile("/tmp/q16-delivery-selection-time.txt", proof / "delivery-selection-time-full.txt")
print("Fresh offline delivery, opening and exports agree with the selected proposal record")
