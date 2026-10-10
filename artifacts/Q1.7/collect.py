import base64
import hashlib
import json
import subprocess
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from bikeplan import main

ROOT = Path("artifacts/Q1.7")
OUT = ROOT / "report"
REGION = "tests/fixtures/test-grid/region.yaml"
SNAPSHOT = "tests/fixtures/test-grid/snapshot"
assert main(["report", REGION, "--snapshot", SNAPSHOT, "--out", str(OUT)]) == 0
options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
    options.add_argument(flag)
driver = webdriver.Chrome(options=options)
proof = {
    "row": "Q1.7",
    "scope": "Fresh test-grid report; no claim of real school coverage or full report conversion",
    "command": "uv run python artifacts/Q1.7/collect.py",
    "code": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "region": REGION,
    "snapshot": SNAPSHOT,
    "views": [],
}
try:
    driver.get((OUT / "report.html").resolve().as_uri())
    for width in (390, 1280):
        driver.set_window_size(width, 1100)
        assert driver.execute_script(
            "return document.documentElement.scrollWidth <= window.innerWidth"
        )
        driver.save_screenshot(str(ROOT / f"view-{width}.png"))
        proof["views"].append({"width": width, "sideways_scroll": False})
    driver.find_element(By.ID, "scenario-shipped").send_keys(Keys.ARROW_RIGHT)
    slider = driver.find_element(By.ID, "change-slider")
    slider.send_keys(Keys.HOME)
    slider.send_keys(Keys.ARROW_RIGHT)
    opening = driver.find_element(By.ID, "opening")
    assert opening.get_attribute("data-package") == "heavy:1"
    proof["keyboard_package"] = opening.get_attribute("data-package")
    proof["announced_status"] = driver.find_element(By.ID, "package-status").text
    frontier = json.loads((OUT / "frontier.json").read_text())
    selected = next(item for item in frontier["scenarios"] if item["id"] == "heavy")["picks"][1]
    proof["selected_impacts"] = {}
    for cell in opening.find_elements(By.CSS_SELECTOR, "[data-opening]"):
        key = cell.get_attribute("data-opening")
        value = float(cell.text)
        assert abs(value - selected[key]) <= (0.5 if key == "parking_spaces" else 0.0005)
        proof["selected_impacts"][key] = value
    driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "print"})
    assert opening.is_displayed()
    assert driver.find_element(By.ID, "change-why").is_displayed()
    pdf = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
    (ROOT / "selected.pdf").write_bytes(base64.b64decode(pdf["data"]))
    proof["report_bytes"] = (OUT / "report.html").stat().st_size
    assert proof["report_bytes"] <= 8_000_000
finally:
    driver.quit()
options.add_experimental_option("prefs", {"profile.managed_default_content_settings.javascript": 2})
driver = webdriver.Chrome(options=options)
try:
    driver.get((OUT / "report.html").resolve().as_uri())
    assert "I ask council" in driver.find_element(By.ID, "opening").text
    table = driver.find_element(By.CSS_SELECTOR, '[data-for="change-chart"]')
    assert not table.is_displayed()
    driver.find_element(By.CSS_SELECTOR, "#curve-table > summary").click()
    assert table.is_displayed()
    driver.save_screenshot(str(ROOT / "scripts-off.png"))
    proof["scripts_off"] = "Default proposal and opened curve table are readable"
finally:
    driver.quit()
proof["hashes"] = [
    {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    for path in sorted(OUT.iterdir())
]
(ROOT / "browser-proof.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
print(json.dumps({key: proof[key] for key in ("report_bytes", "keyboard_package", "views")}))
