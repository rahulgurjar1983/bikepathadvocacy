import json
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
    options.add_argument(flag)
driver = webdriver.Chrome(options=options)
driver.get(Path(sys.argv[1]).resolve().as_uri())
driver.implicitly_wait(5)
count = "return document.querySelectorAll('#network-map path.corridor-line').length"
off = driver.execute_script(count)
driver.find_element(By.ID, "overlay-corridors").click()
on = driver.execute_script(count)
dashes = driver.execute_script(
    "return Array.from(document.querySelectorAll('#network-map path.corridor-line'))"
    ".every(p => p.getAttribute('stroke-dasharray'))"
)
errors = [e for e in driver.get_log("browser") if "ERR_" in e["message"]]
driver.quit()
result = {"off": off, "on": on, "all_dashed": dashes, "network_errors": len(errors)}
Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")
print(result)
