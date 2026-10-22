import json
import re
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from bikeplan.report_page import ASSETS, TEMPLATE

released = Path(sys.argv[1]).read_text()
raw = re.search(r'<script id="data" type="application/json">(.*?)</script>', released, re.S)
data = json.loads(raw.group(1).replace("<\\/", "</"))
text = TEMPLATE.read_text()
for key, value in {
    "LEAFLET_CSS": (ASSETS / "leaflet.css").read_text(),
    "LEAFLET_JS": (ASSETS / "leaflet.js").read_text(),
    "DATA_JSON": json.dumps(data, sort_keys=True, separators=(",", ":")).replace("</", "<\\/"),
    "AREA": "Bayside",
}.items():
    text = text.replace("{{" + key + "}}", value)
text = re.sub(r"\{\{[A-Z_]+\}\}", "", text)
page = Path(sys.argv[2])
page.write_text(text)

options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
    options.add_argument(flag)
driver = webdriver.Chrome(options=options)
result = {"wards": [w["name"] for w in data["wards"]]}
try:
    driver.get(page.resolve().as_uri())
    driver.implicitly_wait(5)
    name = data["wards"][0]["name"]
    box = driver.find_element(By.ID, "q")
    box.send_keys(name[:3])
    WebDriverWait(driver, 10).until(lambda d: d.find_elements(By.CSS_SELECTOR, "#qlist li"))
    box.clear()
    box.send_keys(name)
    box.send_keys(Keys.ENTER)
    found = driver.find_element(By.CSS_SELECTOR, "#result.show")
    shown = [li.text for li in found.find_elements(By.CSS_SELECTOR, ".ward li")]
    onpage = driver.find_elements(By.CSS_SELECTOR, "#wardcards .ward")[0]
    same = [li.text for li in onpage.find_elements(By.CSS_SELECTOR, "li")]
    result |= {
        "searched": name,
        "card_title": found.find_element(By.TAG_NAME, "h3").text,
        "card_values": shown,
        "page_card_values": same,
        "same_values": shown == same,
        "map_polygons": len(found.find_elements(By.CSS_SELECTOR, "svg polygon")),
        "figure_links": len(found.find_elements(By.CSS_SELECTOR, ".ward a.fig")),
        "copy_link": found.find_element(By.CSS_SELECTOR, "button.copy").text,
        "hash": driver.current_url.split("#")[1],
        "words": len(" ".join(shown).split()),
    }
finally:
    driver.quit()
print(json.dumps(result, indent=1))
