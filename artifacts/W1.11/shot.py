import json
import re
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

folder, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
page = folder / "map.html"
options = webdriver.ChromeOptions()
for flag in (
    "--headless=new",
    "--no-sandbox",
    "--window-size=1440,900",
    "--proxy-server=http://127.0.0.1:9",
):
    options.add_argument(flag)
options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
options.page_load_strategy = "none"
driver = webdriver.Chrome(options=options)
driver.get(page.as_uri() + "#path-cook-park-trail")
deadline = time.time() + 900
while time.time() < deadline:
    try:
        if (
            driver.execute_script("return document.querySelectorAll('.leaflet-popup a.btn').length")
            >= 2
        ):
            break
    except Exception:
        pass
    time.sleep(3)
time.sleep(3)
driver.save_screenshot(str(out / "map-cook-park-trail.png"))
text = page.read_text()
data = json.loads(
    re.search(r'<script id="data" type="application/json">(.*?)</script>', text, re.S).group(1)
)
summary = {
    "console_errors": [e["message"] for e in driver.get_log("browser") if e["level"] == "SEVERE"],
    "layers": [e.text for e in driver.find_elements(By.CSS_SELECTOR, ".layer")],
    "popup_links": [
        a.get_attribute("href")
        for a in driver.find_elements(By.CSS_SELECTOR, ".leaflet-popup a.btn")
    ],
    "paths_km": data["paths_km"],
    "paths": {
        p["name"]: p["km"]
        for p in data["paths"]
        if p["name"] in ("Cook Park Trail", "M6 Shared Path")
    },
    "street_changes": len(data["changes"]),
    "files": sorted(
        str(p.relative_to(folder))
        for p in [page, folder / "map.kml", *(folder / "map-layers").glob("*.kml")]
    ),
}
driver.quit()
(out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
print(json.dumps(summary, indent=1)[:1500])
