import base64
import re
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

import textstat
from selenium.webdriver.common.print_page_options import PrintOptions

from bikeplan.axe import tab_stops, violations
from bikeplan.shots import offline_driver, remote_requests

MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_WORDS = 1000
MAX_PRINT_PAGES = 4
MAX_GRADE = 8.0
MAX_LINE = 70
ORDER = ("top", "find", "spots", "streets", "wards", "plans", "cost", "ask", "how", "evidence")
PLACES = ("School", "Station", "Town centre")
WORDS = (
    "const map = document.querySelector('#plan-map');"
    "if (map) map.style.display = 'none';"
    "document.querySelectorAll('svg').forEach(s => { s.style.display = 'none'; });"
    "return (document.body.innerText.match(/[A-Za-z0-9]+/g) || []).length;"
)
HERO = r"""
const count = e => e.innerText.trim().split(/\s+/).length;
const tiles = [...document.querySelectorAll('.hero .tile')];
const parts = [document.querySelector('h1'), document.getElementById('lede'), ...tiles];
const map = document.getElementById('plan-map').getBoundingClientRect();
return {
  title: count(parts[0]),
  lede: count(parts[1]),
  tiles: tiles.length,
  empty: tiles.filter(e => !e.querySelector('.n').innerText.trim()).length,
  below: parts.filter(e => e.getBoundingClientRect().bottom > innerHeight).length,
  map: map.top >= innerHeight ? 1 : 0,
};
"""
TEXT = "return document.body.innerText;"
LOOK = """
const body = parseFloat(getComputedStyle(document.body).fontSize);
const big = [...document.querySelectorAll('.tile .n')]
  .map(e => parseFloat(getComputedStyle(e).fontSize));
return {
  side: document.documentElement.scrollWidth - innerWidth,
  body,
  big: big.length ? Math.min(...big) : 0,
  fonts: document.fonts.size,
};
"""
PROSE = """
return [...document.querySelectorAll('h1, h2, h3, p, li, figcaption')]
  .filter(e => !e.closest('details') && e.innerText.trim())
  .map(e => e.innerText.trim());
"""
LINES = """
let longest = 0;
for (const e of document.querySelectorAll('main p, main li')) {
  if (!e.offsetParent || e.closest('details')) continue;
  const walk = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
  const rows = new Map();
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    for (let i = 0; i < n.length; i++) {
      const r = document.createRange();
      r.setStart(n, i);
      r.setEnd(n, i + 1);
      const box = r.getBoundingClientRect();
      if (!box.width) continue;
      const key = Math.round(box.top);
      rows.set(key, (rows.get(key) || 0) + 1);
    }
  }
  longest = Math.max(longest, ...rows.values(), 0);
}
return longest;
"""
IDS = "return [...document.querySelectorAll('[id]')].map(e => e.id);"
EYEBROW = "const e = document.querySelector('#result .eyebrow'); return e ? e.textContent : '';"
CHIPS = "return document.querySelectorAll('#chips button').length;"
CLICK = "document.querySelectorAll('#chips button')[arguments[0]].click();"
NAMED = """
return {
  spots: document.querySelectorAll('#spotlist button').length,
  wards: document.querySelectorAll('#wardcards .ward').length,
};
"""
BANNED = (
    re.compile(r"[A-Za-z]+_[A-Za-z_]+"),
    re.compile(r"\bstep \d", re.I),
    re.compile(r"unnamed", re.I),
    re.compile(r"\bLTS\b"),
    re.compile(r"\bAAA\b"),
    re.compile(r"Steiner", re.I),
)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
PAGES = re.compile(rb"/Count (\d+)")
SPEC_IDS = ("FR-20.7", "FR-20.8", "FR-20.19", "FR-20.20", "FR-20.21", "FR-20.22", "FR-20.25")


def measure(spec_id: str, label: str, name: str, value: float, limit: float) -> dict:
    return {
        "spec": spec_id,
        "line": f"{name}: {label}: {value:,} of at most {limit:,}, "
        + ("met" if value <= limit else "fails"),
        "met": value <= limit,
    }


def grade(parts: list[str]) -> float:
    text = " ".join(part if part[-1] in ".!?" else part + "." for part in parts)
    return round(textstat.flesch_kincaid_grade(text), 1)


def long_numbers(text: str) -> int:
    found = 0
    for number in NUMBER.findall(text):
        if "," in number:
            continue
        if "." not in number and len(number) == 4 and 1900 <= int(number) <= 2100:
            continue
        if len(number.replace(".", "").lstrip("0")) > 3:
            found += 1
    return found


def plain_words_broken(text: str) -> int:
    return sum(len(rule.findall(text)) for rule in BANNED) + long_numbers(text)


def order_breaks(ids: list[str]) -> int:
    seen = [ORDER.index(name) for name in ids if name in ORDER]
    return sum(1 for before, after in pairwise(seen) if after < before)


def view(driver, uri: str, width: int, height: int, mobile: bool) -> None:
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile},
    )
    driver.get(uri)


def printed_pages(driver) -> int:
    options = PrintOptions()
    options.page_width = 21.0
    options.page_height = 29.7
    pdf = base64.b64decode(driver.print_page(options))
    return max(int(count) for count in PAGES.findall(pdf))


def card_violations(driver) -> dict[str, int]:
    found: dict[str, int] = {}
    for index in range(driver.execute_script(CHIPS)):
        driver.execute_script(CLICK, index)
        eyebrow = driver.execute_script(EYEBROW)
        kind = "place" if eyebrow.startswith(PLACES) else "street" if eyebrow == "Street" else ""
        if kind and kind not in found:
            found[kind] = len(violations(driver))
    return found


def keys_missed(driver) -> tuple[int, int]:
    named = driver.execute_script(NAMED)
    stops = tab_stops(driver, 400)
    reached = (
        sum(stop["id"] in ("q", "play") for stop in stops)
        + sum("stage" in stop["data"] for stop in stops)
        + sum("leaflet-control-zoom" in stop["cls"] for stop in stops)
        + sum(stop["spot"] or stop["ward"] for stop in stops)
    )
    expected = 2 + 3 + 2 + named["spots"] + named["wards"]
    return max(0, expected - reached), sum(not stop["ring"] for stop in stops)


@lru_cache(maxsize=8)
def page_measures(path: str, size: int) -> tuple:
    page = Path(path)
    uri = page.resolve().as_uri()
    name = page.name
    driver = offline_driver(1440, 900, False)
    try:
        driver.get(uri)
        asked = len(remote_requests(driver))
        found = len(violations(driver))
        words = driver.execute_script(WORDS)
        text = driver.execute_script(TEXT)
        level = grade(driver.execute_script(PROSE))
        longest = driver.execute_script(LINES)
        ids = driver.execute_script(IDS)
        hero = {"1440 by 900": driver.execute_script(HERO)}
        cards = card_violations(driver)
        view(driver, uri, 1440, 900, False)
        missed, ringless = keys_missed(driver)
        printed = printed_pages(driver)
        view(driver, uri, 390, 844, True)
        hero["390 by 844"] = driver.execute_script(HERO)
        phone = driver.execute_script(LOOK)
        view(driver, uri, 360, 800, False)
        narrow = driver.execute_script(LOOK)
        view(driver, uri, 1440, 900, False)
        wide = driver.execute_script(LOOK)
    finally:
        driver.quit()
    slots = page.read_text(encoding="utf-8").count("{{")
    big = hero["1440 by 900"]
    out = [
        measure("FR-20.7", "words at load", name, words, MAX_WORDS),
        measure("FR-20.7", "Flesch-Kincaid grade of the prose", name, level, MAX_GRADE),
        measure("FR-20.8", "words in the title", name, big["title"], 10),
        measure("FR-20.8", "words in the opening sentence", name, big["lede"], 25),
        measure(
            "FR-20.8", "hero big numbers missing", name, max(0, 3 - big["tiles"]) + big["empty"], 0
        ),
    ]
    for size_name, got in hero.items():
        label = f"hero parts below the first screen at {size_name}"
        out.append(measure("FR-20.8", label, name, got["below"], 0))
    out.append(measure("FR-20.8", "map below the first screen at 1440 by 900", name, big["map"], 0))
    out += [
        measure("FR-20.19", "plain words broken", name, plain_words_broken(text), 0),
        measure("FR-20.20", "pixels of sideways scroll at 360 px", name, max(0, narrow["side"]), 0),
        measure(
            "FR-20.20", "pixels body text is short of 17", name, max(0, round(17 - wide["body"])), 0
        ),
        measure(
            "FR-20.20",
            "pixels a big number is short of 40 at 390 px",
            name,
            max(0, round(40 - phone["big"])),
            0,
        ),
        measure(
            "FR-20.20",
            "characters the longest line is over 70",
            name,
            max(0, longest - MAX_LINE),
            0,
        ),
        measure("FR-20.20", "font downloads", name, wide["fonts"], 0),
        measure("FR-20.20", "pages printed on A4", name, printed, MAX_PRINT_PAGES),
        measure("FR-20.21", "serious or critical axe-core violations at load", name, found, 0),
    ]
    for kind, label in (("place", "place card"), ("street", "street card")):
        if kind in cards:
            text_label = f"serious or critical axe violations with a {label} open"
            out.append(measure("FR-20.21", text_label, name, cards[kind], 0))
    out += [
        measure("FR-20.21", "named controls the Tab key misses", name, missed, 0),
        measure("FR-20.21", "focus stops without a visible ring", name, ringless, 0),
        measure("FR-20.22", "page size in bytes", name, size, MAX_PAGE_BYTES),
        measure("FR-20.22", "network requests at load", name, asked, 0),
        measure("FR-20.25", "sections out of the mock's order", name, order_breaks(ids), 0),
        measure("FR-20.25", "unfilled slots", name, slots, 0),
    ]
    return tuple(out)


def measures(reports: list[Path]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {spec_id: [] for spec_id in SPEC_IDS}
    for path in reports:
        if not path.name.endswith("-report.html"):
            continue
        for item in page_measures(str(path), path.stat().st_size):
            found[item["spec"]].append(item)
    return found
