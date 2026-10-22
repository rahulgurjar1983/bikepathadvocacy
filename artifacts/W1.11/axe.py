import json
import re
import sys
import time
from pathlib import Path

from selenium import webdriver

from bikeplan import axe

folder, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
page = folder / "map.html"
text = page.read_text()
data = json.loads(
    re.search(r'<script id="data" type="application/json">(.*?)</script>', text, re.S)
    .group(1)
    .replace("<\\/", "</")
)
change = data["changes"][0]["id"]
report = {"axe": axe.AXE_VERSION, "change": change, "states": []}


def wait_for(driver, script):
    deadline = time.time() + 900
    while time.time() < deadline:
        try:
            if driver.execute_script(script):
                return
        except Exception:
            pass
        time.sleep(3)
    raise SystemExit("page never reached: " + script)


for size in ((390, 844), (1440, 900)):
    for popup in (False, True):
        options = webdriver.ChromeOptions()
        for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
            options.add_argument(flag)
        options.page_load_strategy = "none"
        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": size[0], "height": size[1], "deviceScaleFactor": 1, "mobile": size[0] < 500},
        )
        driver.get(page.as_uri() + ("#" + change if popup else ""))
        wait_for(driver, "return document.querySelectorAll('#layers label.layer .n').length > 0")
        if popup:
            wait_for(driver, "return document.querySelectorAll('.leaflet-popup a.btn').length >= 2")
        found = axe.violations(driver)
        stops = axe.tab_stops(driver, 400) if not popup else []
        report["states"].append(
            {
                "size": list(size),
                "popup": popup,
                "violations": found,
                "tab_stops": len(stops),
                "tab_stops_without_ring": [s for s in stops if not s["ring"]],
            }
        )
        driver.quit()
(out / "axe.json").write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps([(s["size"], s["popup"], len(s["violations"])) for s in report["states"]]))
sys.exit(1 if any(s["violations"] for s in report["states"]) else 0)
