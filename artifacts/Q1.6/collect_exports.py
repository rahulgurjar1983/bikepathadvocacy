import csv
import hashlib
import io
import json
import shutil
import subprocess
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

out = Path("/tmp/bikeplan-Q1.6-exports")
proof = Path("artifacts/Q1.6")
downloads = out / "downloads"
downloads.mkdir(exist_ok=True)
record = json.loads((out / "proposal.json").read_text())
frontier = json.loads((out / "frontier.json").read_text())
assert record["region"] == "au-nsw-bayside"
assert (out / "report.html").stat().st_size <= 8_000_000


def leaves(data, prefix=""):
    result = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(leaves(value, path))
        else:
            result[path] = value
    return result


options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
    options.add_argument(flag)
options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
cases = []
with webdriver.Chrome(options=options) as browser:
    browser.execute_cdp_cmd(
        "Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)}
    )
    browser.get((out / "report.html").resolve().as_uri())
    browser.implicitly_wait(5)
    for curve in frontier["scenarios"]:
        name = curve["id"]
        browser.find_element(By.ID, f"scenario-{name}").click()
        for rank in sorted({0, curve["recommended_stop"] or 0, len(curve["picks"]) - 1}):
            browser.execute_script(
                "const s=document.getElementById('change-slider'); s.value=arguments[0];"
                "s.dispatchEvent(new Event('input', {bubbles:true}));",
                rank,
            )
            identity = {"scenario": name, "rank": rank}
            expected = next(p for p in record["packages"] if p["identity"] == identity)
            saved = {}
            for kind in ("json", "csv"):
                link = browser.find_element(By.ID, f"package-export-{kind}")
                assert link.get_attribute("data-package") == f"{name}:{rank}"
                filename = f"proposal-{name}-{rank}.{kind}"
                assert link.get_attribute("download") == filename
                path = downloads / filename
                path.unlink(missing_ok=True)
                link.click()
                end = time.monotonic() + 10
                while not path.exists() and time.monotonic() < end:
                    time.sleep(0.05)
                saved[kind] = path.read_bytes()
            exported = json.loads(saved["json"])
            assert exported["selected"] == expected
            assert exported["curve_totals"] == curve["picks"][rank]
            for key in ("schema_version", "region", "snapshot", "code", "input_hashes"):
                assert exported[key] == record[key]
            rows = list(csv.DictReader(io.StringIO(saved["csv"].decode())))
            assert len({r["field"] for r in rows}) == len(rows)
            assert {r["field"]: json.loads(r["value_json"]) for r in rows} == leaves(exported)
            assert expected["metrics"]["capital_cost"]["value"] is None
            assert expected["metrics"]["capital_cost"]["reason"]
            assert browser.find_element(By.ID, "opening").get_attribute("data-package") == (
                f"{name}:{rank}"
            )
            browser.execute_script("arguments[0].scrollIntoView()", link)
            browser.save_screenshot(str(proof / "exports-browser.png"))
            cases.append(
                {
                    "identity": identity,
                    "project_ids": expected["project_ids"],
                    "element_ids": expected["element_ids"],
                    "download_sha256": {
                        kind: hashlib.sha256(value).hexdigest() for kind, value in saved.items()
                    },
                }
            )
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
outputs = []
for line in (out / "outputs.sha256").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    outputs.append({"path": name, "sha256": digest})
saved = {
    "build_command": (
        "/usr/bin/time -v -o /tmp/q16-exports-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-Q1.6-exports"
    ),
    "check_command": "uv run --frozen python artifacts/Q1.6/collect_exports.py",
    "build_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "snapshot": record["snapshot"],
    "code": record["code"],
    "input_hashes": record["input_hashes"],
    "report_bytes": (out / "report.html").stat().st_size,
    "cases": cases,
    "outputs": outputs,
    "scope": (
        "Offline curve exports only. Empty confirmed curves prove honest empty selection "
        "and unknowns, not real works. Nonempty baseline/rank switches are tested in "
        "test_proposal_exports.py. Shared list and sheets, goal/stage packages and full "
        "multi-rank browser acceptance remain open. This proof does not prove performance."
    ),
}
(proof / "archive-exports.json").write_text(json.dumps(saved, sort_keys=True, indent=2) + "\n")
shutil.copyfile("/tmp/q16-exports-time.txt", proof / "exports-time-full.txt")
print("Fresh offline exports match archive packages and curve totals; hashes match")
