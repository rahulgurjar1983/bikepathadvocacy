import json
import re
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

from bikeplan.report_page import ASSETS, TEMPLATE

released = Path(sys.argv[1]).read_text()
options = json.loads(Path(sys.argv[2]).read_text())
raw = re.search(r'<script id="data" type="application/json">(.*?)</script>', released, re.S)
data = json.loads(raw.group(1).replace("<\\/", "</"))
pick = next(
    item
    for item in options["options"]
    if all(
        item["works"][spot["w"]]["street"] == spot["street"]
        and item["works"][spot["w"]]["trips"] == spot["trips"]
        for spot in data["spots"]
    )
)
for spot in data["spots"]:
    spot["park"] = pick["works"][spot["w"]]["parking_spaces"]
data["council_source"] = {
    key: options["council"]["source"][name]
    for key, name in (("title", "title"), ("url", "url"), ("date", "read_on"))
}
data["corridor_source"] = data["corridor_source"] | {"url": options["corridors"]["source"]["url"]}
text = TEMPLATE.read_text()
for key, value in {
    "LEAFLET_CSS": (ASSETS / "leaflet.css").read_text(),
    "LEAFLET_JS": (ASSETS / "leaflet.js").read_text(),
    "DATA_JSON": json.dumps(data, sort_keys=True, separators=(",", ":")).replace("</", "<\\/"),
    "AREA": "Bayside",
}.items():
    text = text.replace("{{" + key + "}}", value)
text = re.sub(r"\{\{[A-Z_]+\}\}", "", text)
page = Path(sys.argv[3])
page.write_text(text)

driver_options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
    driver_options.add_argument(flag)
driver_options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
driver = webdriver.Chrome(options=driver_options)


def words(text):
    return len(re.findall(r"[A-Za-z0-9]+", text))


try:
    driver.get(page.resolve().as_uri())
    driver.implicitly_wait(10)
    asks = [item.text for item in driver.find_elements(By.CSS_SELECTOR, "#asks li")]
    cards = driver.find_elements(By.CSS_SELECTOR, "#wardcards .ward")
    result = {
        "fix_cards": [
            item.find_element(By.TAG_NAME, "h3").text
            for item in driver.find_elements(By.CSS_SELECTOR, "#fixes .fix")
        ],
        "spot_sentence": driver.find_element(By.ID, "spot-p").text,
        "spots_listed": len(driver.find_elements(By.CSS_SELECTOR, "#spotlist li")),
        "spots_more": driver.find_element(By.ID, "spotmore").text,
        "credits": [item.text for item in driver.find_elements(By.CSS_SELECTOR, "#plans .credit")],
        "ward_card_words": [words(card.text) for card in cards],
        "asks": asks,
        "ask_words": [words(item) for item in asks],
        "severe_log": [m for m in driver.get_log("browser") if m["level"] == "SEVERE"],
    }
finally:
    driver.quit()
print(json.dumps(result, indent=2))
