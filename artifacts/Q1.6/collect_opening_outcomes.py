import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
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


out = Path("/tmp/bikeplan-Q1.6-opening-outcomes")
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
    for section in (
        "selected-evidence",
        "selected-trips",
        "delivery",
        "opening",
        "selected-projects",
        "report-map",
        "change-totals",
        "physical-works",
        "selected-residents",
    ):
        assert browser.find_element(By.ID, section).get_attribute("data-package") == key
    strict = package["outcomes"]["resident_outcomes"]["strict"]
    trips = package["outcomes"]["trip_summary"]["strict_return_trips"]
    for name, value, block, figure in (
        ("trips", trips["value"], trips, "F25"),
        ("residents", strict["unique_residents"]["newly_gained"], strict, "F24"),
    ):
        element = browser.find_element(By.ID, "opening-outcome-" + name)
        assert element.is_displayed()
        assert element.get_attribute("href").endswith("#" + figure)
        assert element.text == "unknown" if value is None else float(element.text) == value
        reason = browser.find_element(By.ID, "opening-outcome-" + name + "-reason")
        assert reason.text == (block.get("reason", "") if value is None else "")
    assert (
        json.loads(browser.find_element(By.ID, "trip-summary").text)
        == package["outcomes"]["trip_summary"]
    )
    assert (
        json.loads(browser.find_element(By.ID, "resident-summary").text)
        == package["outcomes"]["resident_outcomes"]
    )
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
                    browser.execute_script("document.getElementById('opening').scrollIntoView()")
                    browser.save_screenshot(str(proof / f"opening-outcomes-{media}-{width}.png"))
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
                    "outcomes": package["outcomes"],
                    "project_ids": package["project_ids"],
                }
            )
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
for package in record["packages"]:
    identity = package["identity"]
    curve = next(c for c in frontier["scenarios"] if c["id"] == identity["scenario"])
    source = curve["trip_packages"][identity["rank"]]
    assert package["evidence_limits"]["route_gaps"] == source["gaps"]
    for key, value in (
        ("strict_return_trips", len(source["strict"])),
        ("route_groups", len(source["groups"])),
        ("route_gaps", len(source["gaps"])),
    ):
        metric = package["outcomes"]["trip_summary"][key]
        assert metric["value"] == value
        assert metric["scope"]["package"] == identity
options.add_argument("--blink-settings=scriptEnabled=false")
with webdriver.Chrome(options=options) as browser:
    browser.get((out / "report.html").resolve().as_uri())
    for media in ("screen", "print"):
        browser.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": media})
        package = record["selected"]
        identity = package["identity"]
        key = f"{identity['scenario']}:{identity['rank']}"
        assert browser.find_element(By.ID, "selected-evidence").get_attribute("data-package") == key
        assert browser.find_element(By.ID, "evidence-package").text == key
        for name, value in (
            ("trips", package["outcomes"]["trip_summary"]["strict_return_trips"]["value"]),
            (
                "residents",
                package["outcomes"]["resident_outcomes"]["strict"]["unique_residents"][
                    "newly_gained"
                ],
            ),
        ):
            element = browser.find_element(By.ID, "opening-outcome-" + name)
            assert element.is_displayed()
            assert element.text == "unknown" if value is None else float(element.text) == value


class TripFigure(HTMLParser):
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
for figure, unit, expected in (
    (
        "F25",
        "return trips",
        record["selected"]["outcomes"]["trip_summary"]["strict_return_trips"]["value"],
    ),
    (
        "F24",
        "estimated residents",
        record["selected"]["outcomes"]["resident_outcomes"]["strict"]["unique_residents"][
            "newly_gained"
        ],
    ),
):
    entry = TripFigure(figure)
    entry.feed((out / "report.html").read_text())
    value = float(re.search(r"Value(.*?) " + unit, entry.text).group(1))
    digest = re.search(r"proposal.json, sha256 ([0-9a-f]{64})", entry.text).group(1)
    result = subprocess.run(
        ["python3", "-I", "-c", entry.recipe], cwd=out, capture_output=True, text=True, check=True
    )
    assert float(result.stdout) == value == expected
    assert digest == hashlib.sha256((out / "proposal.json").read_bytes()).hexdigest()
    recipes.append({"figure": figure, "value": value, "recipe_output": result.stdout.strip()})
outputs = []
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    outputs.append({"path": name, "sha256": digest})
saved = {
    "build_command": (
        "/usr/bin/time -v -o /tmp/q16-opening-outcomes-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.6-opening-outcomes"
    ),
    "check_command": "uv run --frozen python artifacts/Q1.6/collect_opening_outcomes.py",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "snapshot": record["snapshot"],
    "code": record["code"],
    "input_hashes": record["input_hashes"],
    "report_bytes": (out / "report.html").stat().st_size,
    "cases": cases,
    "outputs": outputs,
    "recipes": recipes,
    "scope": (
        "Selected opening trip and resident outcomes, shared identities, "
        "print and JSON/CSV exports; "
        "scripts-off default. "
        "Empty real packages prove honest unknowns, not useful works, known costs or funding. "
        "Nonempty fixture rank changes are unit-tested. Other shared views, goal/stage "
        "packages and full browser acceptance remain open. This is not performance proof."
    ),
}
(proof / "archive-opening-outcomes.json").write_text(
    json.dumps(saved, sort_keys=True, indent=2) + "\n"
)
shutil.copyfile("/tmp/q16-opening-outcomes-time.txt", proof / "opening-outcomes-time-full.txt")
print("Fresh offline opening outcomes and exports agree with the selected proposal record")
