import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
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


def check(browser, package):
    identity = package["identity"]
    key = f"{identity['scenario']}:{identity['rank']}"
    assert browser.find_element(By.ID, "opening").get_attribute("data-package") == key
    loss = package["impacts"]["parking_spaces"]["removed"]
    for name, value, figure in (
        ("roads", package["works"]["unique_roads"], "F14"),
        ("parking", loss["known_subtotal"], "F23"),
    ):
        element = browser.find_element(By.ID, "opening-outcome-" + name)
        assert element.is_displayed()
        assert element.get_attribute("href").endswith("#" + figure)
        assert (element.text == "unknown") if value is None else (float(element.text) == value)
    reason = browser.find_element(By.ID, "opening-outcome-parking-reason")
    assert reason.text == (loss["reason"] if loss["value"] is None else "")
    return key


out = Path("/tmp/bikeplan-Q1.6-opening-impacts")
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
                    browser.execute_script(
                        "document.getElementById('opening-outcomes').scrollIntoView()"
                    )
                    browser.save_screenshot(str(proof / f"opening-impacts-{media}-{width}.png"))
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
                    "works": package["works"],
                    "impacts": package["impacts"],
                }
            )
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
for package in record["packages"]:
    identity = package["identity"]
    curve = next(c for c in frontier["scenarios"] if c["id"] == identity["scenario"])
    source = curve["trip_packages"][identity["rank"]]["works"]
    assert package["works"] == source
    assert package["impacts"]["parking_spaces"] == source["parking_spaces"]
options.add_argument("--blink-settings=scriptEnabled=false")
with webdriver.Chrome(options=options) as browser:
    browser.get((out / "report.html").resolve().as_uri())
    for media in ("screen", "print"):
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
        check(browser, record["selected"])


class Figure(HTMLParser):
    def __init__(self, figure):
        super().__init__()
        self.figure = figure
        self.active = False
        self.pre = False
        self.text = ""
        self.recipe = ""

    def handle_starttag(self, tag, attrs):
        if tag == "article" and dict(attrs).get("id") == self.figure:
            self.active = True
        if self.active and tag == "pre":
            self.pre = True

    def handle_data(self, data):
        if self.active:
            self.text += data
            if self.pre:
                self.recipe += data

    def handle_endtag(self, tag):
        if tag == "pre":
            self.pre = False
        if tag == "article":
            self.active = False


recipes = []
for figure_id, unit, expected in (
    ("F14", "roads", record["selected"]["works"]["unique_roads"]),
    (
        "F23",
        "vehicle spaces",
        record["selected"]["impacts"]["parking_spaces"]["removed"]["known_subtotal"],
    ),
):
    figure = Figure(figure_id)
    figure.feed((out / "report.html").read_text())
    value = float(re.search(r"Value(.*?) " + unit, figure.text).group(1))
    digest = re.search(r"frontier.json, sha256 ([0-9a-f]{64})", figure.text).group(1)
    assert hashlib.sha256((out / "frontier.json").read_bytes()).hexdigest() == digest
    with tempfile.TemporaryDirectory() as folder:
        shutil.copyfile(out / "frontier.json", Path(folder) / "frontier.json")
        result = subprocess.run(
            ["python3", "-I", "-c", figure.recipe],
            cwd=folder,
            capture_output=True,
            text=True,
            check=True,
        )
    assert float(result.stdout) == value == expected
    recipes.append({"figure": figure_id, "value": expected, "recipe_output": result.stdout.strip()})
outputs = []
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    outputs.append({"path": name, "sha256": digest})
saved = {
    "build_command": (
        "/usr/bin/time -v -o /tmp/q16-opening-impacts-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.6-opening-impacts"
    ),
    "check_command": "uv run --frozen python artifacts/Q1.6/collect_opening_impacts.py",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "snapshot": record["snapshot"],
    "code": record["code"],
    "input_hashes": record["input_hashes"],
    "report_bytes": (out / "report.html").stat().st_size,
    "cases": cases,
    "outputs": outputs,
    "recipes": recipes,
    "scope": (
        "Selected opening road counts and known physical parking loss, offline exports, "
        "print and scripts off. Empty real choices prove truthful scope, not useful works "
        "or known inventory. Nonempty fixture choices are unit-tested. Goal/stage packages, "
        "other shared views and full browser acceptance remain open. "
        "This is not performance proof."
    ),
}
(proof / "archive-opening-impacts.json").write_text(
    json.dumps(saved, sort_keys=True, indent=2) + "\n"
)
shutil.copyfile("/tmp/q16-opening-impacts-time.txt", proof / "opening-impacts-time-full.txt")
print("Fresh offline opening road counts and parking loss agree with the selected record")
