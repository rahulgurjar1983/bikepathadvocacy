import gzip
import hashlib
import json
import subprocess
import sys

import pytest
from pyproj import Geod
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from bikeplan import main
from tests.report_snapshot import crafted
from tests.test_report import REGION

GEOD = Geod(ellps="WGS84")
NORTH = -33.9435
BAY = [(151.1491, 151.1520), (151.1520, 151.1550)]
TAIL = (151.1550, 151.1570)
EDGE_LAT = -33.9470
EAST = ((151.157511, -33.95282), (151.1577442, -33.9420028))


def metres(lon_a, lon_b, lat):
    return GEOD.line_length([lon_a, lon_b], [lat, lat])


class Osm:
    def __init__(self):
        self.next = 9000
        self.text = ""

    def way(self, points, tags):
        ids = []
        for lon, lat in points:
            self.next += 1
            ids.append(self.next)
            self.text += f'<node id="{self.next}" lat="{lat}" lon="{lon}"></node>\n'
        self.next += 1
        refs = "".join(f'<nd ref="{i}"/>' for i in ids)
        keys = "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items())
        self.text += f'<way id="{self.next}">{refs}{keys}</way>\n'


def build_osm():
    osm = Osm()
    for a, b in BAY:
        osm.way([(a, NORTH), (b, NORTH)], {"highway": "cycleway", "name": "Bay Trail"})
    osm.way([(TAIL[0], NORTH), (TAIL[1], NORTH)], {"highway": "cycleway"})
    osm.way(
        [(151.1500, -33.9428), (151.1512, -33.9428)],
        {"highway": "footway", "bicycle": "designated", "name": "Park Link"},
    )
    osm.way(
        [(151.1500, -33.9431), (151.1512, -33.9431)],
        {"highway": "footway", "name": "Plain Footway"},
    )
    osm.way(
        [(151.1495, -33.9514), (151.1570, -33.9514)],
        {"highway": "residential", "name": "Quay Street"},
    )
    osm.way([(151.1520, -33.9512), (151.1532, -33.9512)], {"highway": "cycleway"})
    osm.way(
        [(151.1495, -33.9424), (151.1520, -33.9424)],
        {"highway": "residential", "name": "Lane Road", "cycleway": "lane"},
    )
    osm.way(
        [(151.1540, -33.9424), (151.1560, -33.9424)],
        {"highway": "residential", "name": "Track Road", "cycleway:left": "track"},
    )
    osm.way(
        [(151.1570, EDGE_LAT), (151.1590, EDGE_LAT)], {"highway": "cycleway", "name": "Edge Path"}
    )
    return osm.text


def with_paths(folder):
    snapshot = crafted(folder, {"elements": []})
    path = snapshot / "network.osm.gz"
    text = gzip.decompress(path.read_bytes()).decode().replace("</osm>", build_osm() + "</osm>")
    path.write_bytes(gzip.compress(text.encode(), mtime=0))
    manifest = json.loads((snapshot / "manifest.json").read_text())
    for entry in manifest["files"]:
        content = (snapshot / entry["path"]).read_bytes()
        entry["bytes"] = len(content)
        entry["sha256"] = hashlib.sha256(content).hexdigest()
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return snapshot


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    return with_paths(tmp_path_factory.mktemp("paths-snapshot"))


@pytest.fixture(scope="module")
def pick_line():
    return [[BAY[0][0], NORTH], [BAY[0][1], NORTH]]


@pytest.fixture(scope="module")
def found(snapshot, pick_line):
    from bikeplan.paths_today import read_paths

    return {"": read_paths(snapshot, [pick_line])}


@pytest.fixture(scope="module")
def items(found):
    return {item["name"]: item for item in found[""] if item["kind"] == "path"}


def lanes(found):
    return {item["name"]: item for item in found[""] if item["kind"] == "lane"}


def test_fr21_1_ways_with_one_name_and_the_unnamed_way_they_touch_form_one_item(items):
    bay = items["Bay Trail"]
    expected = (
        metres(BAY[0][0], BAY[0][1], NORTH)
        + metres(BAY[1][0], BAY[1][1], NORTH)
        + metres(TAIL[0], TAIL[1], NORTH)
    ) / 1000
    assert bay["km"] == pytest.approx(expected, rel=0.01)
    assert not any("nnamed" in name for name in items)


def test_fr21_1_an_unnamed_way_that_touches_nothing_is_named_after_the_nearest_street(items):
    lone = items["Path by Quay Street"]
    assert lone["km"] == pytest.approx(metres(151.1520, 151.1532, -33.9512) / 1000, rel=0.01)


def test_fr21_1_a_footway_is_a_path_only_when_bikes_are_designated(items):
    assert items["Park Link"]["km"] == pytest.approx(
        metres(151.1500, 151.1512, -33.9428) / 1000, rel=0.01
    )
    assert "Plain Footway" not in items


def test_fr21_1_a_road_with_a_cycleway_track_is_a_path_and_one_with_a_lane_is_a_painted_lane(
    found, items
):
    assert items["Track Road"]["km"] == pytest.approx(
        metres(151.1540, 151.1560, -33.9424) / 1000, rel=0.01
    )
    assert set(lanes(found)) == {"Lane Road"}
    assert "Lane Road" not in items
    assert lanes(found)["Lane Road"]["km"] == pytest.approx(
        metres(151.1495, 151.1520, -33.9424) / 1000, rel=0.01
    )


def test_fr21_1_a_path_half_outside_the_boundary_counts_its_inside_half(items):
    (x0, y0), (x1, y1) = EAST
    edge = x0 + (x1 - x0) * (EDGE_LAT - y0) / (y1 - y0)
    assert items["Edge Path"]["km"] == pytest.approx(
        metres(151.1570, edge, EDGE_LAT) / 1000, rel=0.03
    )


def test_fr21_1_the_share_and_km_on_my_pick_come_from_links_within_15_m(items, found):
    bay = items["Bay Trail"]
    on_pick = (metres(BAY[0][0], BAY[0][1], NORTH) + 15) / 1000
    assert bay["on_pick"] == pytest.approx(on_pick, rel=0.02)
    assert bay["share"] == pytest.approx(on_pick / bay["km"], abs=0.02)
    assert sum(item["on_pick"] for item in found[""] if item["kind"] == "path") == pytest.approx(
        on_pick, rel=0.02
    )
    assert items["Park Link"]["share"] == 0


def test_fr21_1_items_sort_by_km_then_name(found):
    paths = [item for item in found[""] if item["kind"] == "path"]
    keys = [(-item["km"], item["name"]) for item in paths]
    assert keys == sorted(keys)


def test_fr21_1_an_item_gives_its_middle_point_its_two_far_ends_and_its_lines(items):
    bay = items["Bay Trail"]
    assert bay["mid"] == pytest.approx([NORTH, 151.1535], abs=0.0002)
    ends = sorted(bay["ends"], key=lambda point: point[1])
    assert ends[0] == pytest.approx([NORTH, BAY[0][0]], abs=0.0002)
    assert ends[1] == pytest.approx([NORTH, TAIL[1]], abs=0.0002)
    assert bay["lines"]
    assert all(len(line) >= 2 for line in bay["lines"])


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = with_paths(tmp_path_factory.mktemp("paths-run"))
    out = tmp_path_factory.mktemp("paths-out")
    assert main(["report", REGION, "--snapshot", str(folder), "--out", str(out)]) == 0
    return out


def figure(built, label):
    figures = json.loads((built / "figures.json").read_text())
    return next(item for item in figures if item["label"] == label)


def test_fr21_1_the_report_holds_the_paths_and_a_figure_for_each_total(built):
    items = json.loads((built / "paths.json").read_text())["items"]
    assert "paths.json" in (built / "SHA256SUMS").read_text()
    totals = {
        "Km of bike paths today": sum(i["km"] for i in items if i["kind"] == "path"),
        "Km of painted bike lanes today": sum(i["km"] for i in items if i["kind"] == "lane"),
        "Km of bike paths today on my pick": sum(
            i["on_pick"] for i in items if i["kind"] == "path"
        ),
    }
    for label, total in totals.items():
        item = figure(built, label)
        assert item["unit"] == "km"
        assert item["value"] == round(total, 1)
        assert item["inputs"][0]["name"] == "paths.json"
        run = subprocess.run(
            [sys.executable, "-c", item["recipe"]], cwd=built, capture_output=True, text=True
        )
        assert run.returncode == 0, run.stderr
        assert float(run.stdout) == item["value"]
    assert figure(built, "Km of bike paths today")["value"] == pytest.approx(1.196, abs=0.03)


@pytest.fixture(scope="module")
def browser(built):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    options.add_argument("--window-size=1440,900")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.get((built / "report.html").resolve().as_uri())
    driver.implicitly_wait(5)
    yield driver
    driver.quit()


TEAL = """
const canvas = document.querySelector('#plan-map canvas');
const ctx = canvas.getContext('2d');
const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
const hits = [];
for (let i = 0; i < data.length; i += 4) {
  const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
  if (a > 200 && r < 70 && g > 90 && Math.abs(g - b) < 25 && g - r > 60) {
    const n = i / 4;
    hits.push([n % canvas.width, Math.floor(n / canvas.width)]);
  }
}
const ratio = canvas.width / canvas.getBoundingClientRect().width;
return {count: hits.length, ratio: ratio, points: hits.filter((_, k) => k % 7 === 0).slice(0, 400)};
"""


def test_fr21_2_the_map_draws_the_bike_paths_in_teal_and_the_key_names_them(browser):
    WebDriverWait(browser, 10).until(lambda d: d.execute_script(TEAL)["count"] > 0)
    key = browser.find_element(By.CSS_SELECTOR, ".legend")
    assert "Bike path today" in key.text
    swatch = browser.find_element(By.CSS_SELECTOR, ".legend .sw.path")
    assert swatch.value_of_css_property("border-top-color") in (
        "rgba(15, 118, 110, 1)",
        "rgba(45, 212, 191, 1)",
    )


def test_fr21_2_the_caption_gives_the_km_of_paths_and_the_km_on_my_pick(built, browser):
    items = json.loads((built / "paths.json").read_text())["items"]
    total = round(sum(i["km"] for i in items if i["kind"] == "path"), 1)
    mine = round(sum(i["on_pick"] for i in items if i["kind"] == "path"), 1)
    note = browser.find_element(By.ID, "pathnote")
    assert note.text == f"{total} km of bike paths are open today; my pick uses {mine} km of them."
    links = note.find_elements(By.CSS_SELECTOR, "a.fig")
    assert [a.get_attribute("href").rsplit("#", 1)[1] for a in links] == [
        figure(built, "Km of bike paths today")["id"],
        figure(built, "Km of bike paths today on my pick")["id"],
    ]


def test_fr21_2_tapping_a_path_opens_its_card_with_name_km_and_share(built, browser):
    names = {i["name"] for i in json.loads((built / "paths.json").read_text())["items"]}
    browser.execute_script("window.scrollTo(0, 0)")
    seen = browser.execute_script(TEAL)
    canvas = browser.find_element(By.CSS_SELECTOR, "#plan-map canvas")
    card = browser.find_element(By.ID, "result")
    for x, y in seen["points"]:
        ActionChains(browser).move_to_element_with_offset(canvas, 0, 0).move_by_offset(
            round(x / seen["ratio"]) - canvas.size["width"] // 2,
            round(y / seen["ratio"]) - canvas.size["height"] // 2,
        ).click().perform()
        if "bike path today" in card.text.lower():
            break
    assert "bike path today" in card.text.lower()
    assert any(name in card.text for name in names)
    assert " km" in card.text
    assert "%" in card.text
    severe = [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
    assert severe == []
