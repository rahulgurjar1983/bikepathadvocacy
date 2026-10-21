import hashlib
from pathlib import Path

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

AXE_VERSION = "4.14.0"
AXE_SHA256 = "20c09fe157a8a34a30e241aaa1fcdade657734f08ab379ecfbeb7d45cc46e878"
AXE_FILE = Path(__file__).parent / "assets" / "axe.min.js"
IMPACTS = ("serious", "critical")

RUN = """
const done = arguments[arguments.length - 1];
axe.run(document, {resultTypes: ['violations']}).then(found => done(
  found.violations
    .filter(v => arguments[0].includes(v.impact))
    .map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target.join(' '))}))
));
"""

SETTLED = "return document.getAnimations().length === 0"

STOP = """
const e = document.activeElement;
const s = getComputedStyle(e);
return {
  tag: e.tagName,
  id: e.id,
  cls: e.className,
  data: Object.assign({}, e.dataset),
  ring: e.matches(':focus-visible') && (
    (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2) || s.boxShadow !== 'none'),
  spot: !!e.closest('#spotlist'),
  ward: !!e.closest('#wardcards'),
  body: e === document.body
};
"""


def axe_source() -> str:
    blob = AXE_FILE.read_bytes()
    if hashlib.sha256(blob).hexdigest() != AXE_SHA256:
        raise RuntimeError(f"{AXE_FILE} is not axe-core {AXE_VERSION}")
    return blob.decode()


def violations(driver, impacts=IMPACTS) -> list[dict]:
    WebDriverWait(driver, 30).until(lambda d: d.execute_script(SETTLED))
    driver.execute_script(axe_source())
    return driver.execute_async_script(RUN, list(impacts))


def tab_stops(driver, limit: int) -> list[dict]:
    stops = []
    for _ in range(limit):
        driver.switch_to.active_element.send_keys(Keys.TAB)
        stop = driver.execute_script(STOP)
        if stop.pop("body"):
            break
        stops.append(stop)
    return stops
