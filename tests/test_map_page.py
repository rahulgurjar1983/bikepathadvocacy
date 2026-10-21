import json
import re
from pathlib import Path

import pytest
from lxml import etree
from pykml.parser import Schema
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from bikeplan import main
from bikeplan.config import load_region
from tests.test_paths_today import REGION, with_paths
from tests.test_report_page import CHOICE, CORRIDOR, JOINED, MARKS, STREETS, open_page, pick

DESIGN = Path("specs/21-design/map.html")
KML = "{http://www.opengis.net/kml/2.2}"
PIN = re.compile(
    r"https://www\.google\.com/maps/search/\?api=1&query=(-?\d+(?:\.\d{1,6})?)%2C(-?\d+(?:\.\d{1,6})?)"
)
STREET_VIEW = re.compile(
    r"https://www\.google\.com/maps/@\?api=1&map_action=pano"
    r"&viewpoint=(-?\d+(?:\.\d{1,6})?)%2C(-?\d+(?:\.\d{1,6})?)"
)
RIDE = re.compile(
    r"https://www\.google\.com/maps/dir/\?api=1&origin=(-?\d+(?:\.\d{1,6})?)%2C(-?\d+(?:\.\d{1,6})?)"
    r"&destination=(-?\d+(?:\.\d{1,6})?)%2C(-?\d+(?:\.\d{1,6})?)&travelmode=bicycling"
)
BIKE_LAYER = re.compile(
    r"https://www\.google\.com/maps/@\?api=1&map_action=map"
    r"&center=(-?\d+(?:\.\d{1,6})?)%2C(-?\d+(?:\.\d{1,6})?)&zoom=13&layer=bicycling"
)
BOUNDARY = {
    "type": "Polygon",
    "coordinates": [
        [[151.0, -34.0], [151.2, -34.0], [151.2, -33.8], [151.0, -33.8], [151.0, -34.0]]
    ],
}
PATHS = [
    {
        "id": "path-bay-trail",
        "name": "Bay Trail",
        "kind": "path",
        "km": 2.0,
        "on_pick": 0.5,
        "share": 0.25,
        "mid": [-33.95, 151.15],
        "ends": [[-33.95, 151.14], [-33.95, 151.16]],
        "lines": [[[-33.95, 151.14], [-33.95, 151.15], [-33.95, 151.16]]],
    },
    {
        "id": "path-park-link",
        "name": "Park Link",
        "kind": "path",
        "km": 0.4,
        "on_pick": 0.0,
        "share": 0.0,
        "mid": [-33.94, 151.12],
        "ends": [[-33.94, 151.11], [-33.94, 151.13]],
        "lines": [[[-33.94, 151.11], [-33.94, 151.13]]],
    },
    {
        "id": "lane-lane-road",
        "name": "Lane Road",
        "kind": "lane",
        "km": 0.7,
        "on_pick": 0.0,
        "share": 0.0,
        "mid": [-33.93, 151.17],
        "ends": [[-33.93, 151.16], [-33.93, 151.18]],
        "lines": [[[-33.93, 151.16], [-33.93, 151.18]]],
    },
]
HOSTILE = '</script><script>document.title="x"</script> & "quoted"'


def rich_pick():
    found = pick()
    found["works"] += [
        {**found["works"][0], "km": 1.0, "parking_spaces": 2, "lane_km": 0.4, "speed_km": 0.3},
        {**found["works"][0], "km": 0.5, "parking_spaces": 1},
    ]
    found["steps"][1]["works"] = [0, 3]
    found["steps"][3]["works"] = [2, 4]
    for index, at in ((3, (151.2, -33.8)), (4, (151.3, -33.7))):
        found["lines"].append(
            {
                "work": index,
                "ok": False,
                "line": [list(at), [at[0] + 0.001, at[1] + 0.001]],
            }
        )
    return found


def map_data_for(**more):
    from bikeplan.map_data import map_data
    from bikeplan.report_page import report_data

    given = {
        "options": [rich_pick()],
        "choice": CHOICE,
        "marks": MARKS,
        "joined": JOINED,
        "streets": STREETS,
        "corridor": CORRIDOR,
        "boundary": BOUNDARY,
    }
    given |= {key: value for key, value in more.items() if key in given}
    report = report_data(**given, paths=PATHS)
    region = load_region("regions/au-nsw-bayside.yaml")
    return map_data(report, given["options"][0], PATHS, region, "snap-1") | {
        key: value for key, value in more.items() if key not in given
    }


def page_text(data):
    from bikeplan.map_page import map_page

    return map_page(load_region("regions/au-nsw-bayside.yaml"), data)


@pytest.fixture(scope="module")
def data():
    return map_data_for()


@pytest.fixture(scope="module")
def page(data, tmp_path_factory):
    path = tmp_path_factory.mktemp("map") / "map.html"
    path.write_text(page_text(data))
    return path


def embedded(text):
    found = re.search(r'<script id="data" type="application/json">(.*?)</script>', text, re.S)
    return json.loads(found.group(1).replace("<\\/", "</"))


def head_ids(text):
    return re.findall(r'<h2 id="(h-[a-z]+)"', text)


def root_tokens(text):
    block = re.search(r":root\{(.*?)\}", text, re.S).group(1)
    return dict(re.findall(r"(--[a-z0-9-]+):([^;]+);", block))


def test_fr21_3_street_changes_join_the_works_of_one_street_fix_and_stage(data):
    changes = data["changes"]
    assert [(c["id"], c["street"], c["fix"], c["stage"]) for c in changes] == [
        ("ash-street-quietway-1", "Ash Street", "quietway", 1),
        ("ash-street-quietway-2", "Ash Street", "quietway", 2),
    ]
    first, second = changes
    assert (first["km"], first["park"], first["lane"], first["slow"]) == (5.0, 6, 0.4, 0.3)
    assert (second["km"], second["park"]) == (0.5, 1)
    assert len(first["lines"]) == 2


def test_fr21_3_a_street_change_gives_its_two_farthest_ends_and_a_middle_point(data):
    first = data["changes"][0]
    ends = sorted(first["ends"])
    assert ends[0] == pytest.approx([151.11, -33.91], abs=1e-5)
    assert ends[1] == pytest.approx([151.201, -33.799], abs=1e-5)
    assert first["at"] in ([151.1105, -33.9095], [151.2005, -33.7995])


def test_fr21_3_the_data_holds_the_paths_the_spots_and_the_totals(data):
    assert [(p["id"], p["name"], p["km"], p["on_pick"]) for p in data["paths"]] == [
        ("path-bay-trail", "Bay Trail", 2.0, 0.25),
        ("path-park-link", "Park Link", 0.4, 0.0),
    ]
    assert data["paths"][0]["at"] == [151.15, -33.95]
    assert data["paths"][0]["ends"] == [[151.14, -33.95], [151.16, -33.95]]
    assert [p["name"] for p in data["lanes"]] == ["Lane Road"]
    assert (data["paths_km"], data["paths_on_pick_km"], data["lanes_km"]) == (2.4, 0.5, 0.7)
    assert [(s["n"], s["street"], s["kind"]) for s in data["spots"]] == [
        (1, "Forest Road", "signals"),
        (2, "Bay Street", "zebra"),
    ]
    assert len(data["today"]) == 1 and len(data["blockers"]) == 1
    assert data["tag"] == "snap-1"
    assert data["plain"]["quietway"] and data["kind"]["zebra"]


def test_fr21_3_the_page_keeps_the_target_sections_in_order(data):
    target = head_ids(DESIGN.read_text())
    assert target[-1] == "h-council"
    assert head_ids(page_text(data)) == target[:-1]


def test_fr21_3_a_run_with_a_council_plan_has_the_council_section(data):
    council = [
        {
            "id": "R1",
            "name": "Bay route",
            "km": 3.0,
            "share": 0.5,
            "v": "partly",
            "lines": [[[151.1, -33.9], [151.2, -33.9]]],
        }
    ]
    text = page_text(data | {"council": council, "council_km": 3.0, "council_share": 0.5})
    assert head_ids(text) == head_ids(DESIGN.read_text())
    assert 'id="council"' in text
    assert 'id="council"' not in page_text(data)


def test_fr21_3_a_run_without_street_changes_leaves_out_their_section():
    text = page_text(map_data_for(options=[pick() | {"works": [], "lines": []}]))
    assert "h-changes" not in head_ids(text)
    assert "h-paths" in head_ids(text)


def test_fr21_3_the_page_has_the_target_colour_tokens(data):
    assert root_tokens(page_text(data)) == root_tokens(DESIGN.read_text())
    assert len(root_tokens(DESIGN.read_text())) > 30


def test_fr21_3_the_page_fills_the_run_words_and_escapes_the_data():
    hostile = rich_pick() | {"name": HOSTILE}
    hostile["works"][0] = hostile["works"][0] | {"street": HOSTILE}
    text = page_text(map_data_for(options=[hostile]))
    assert "{{" not in text
    assert text.count("<script id=") == 1
    assert embedded(text)["changes"][0]["street"] == HOSTILE
    assert "Bayside" in text and "Rahul Gurjar, Kogarah" in text
    assert "<title>Bayside Bike Plan Map</title>" in text
    assert BIKE_LAYER.search(text.replace("&amp;", "&"))


def test_fr21_3_the_page_draws_every_layer_with_no_network(page, data):
    driver = open_page(page)
    try:
        WebDriverWait(driver, 10).until(lambda d: d.find_elements(By.CSS_SELECTOR, ".layer"))
        labels = [e.text for e in driver.find_elements(By.CSS_SELECTOR, ".layer .lab")]
        assert labels == [
            "First stage changes",
            "Full plan changes",
            "All ages today on my pick",
            "Bike paths today",
            "Painted bike lanes today",
            "Spots",
            "Not fixed yet",
            "Schools, stations, town centres",
            "TfNSW strategic corridors",
        ]
        counts = [e.text for e in driver.find_elements(By.CSS_SELECTOR, ".layer .n")]
        assert counts == [
            "1",
            "1",
            f"{data['stages']['today']['km']:.1f} km",
            "2.4 km",
            "0.7 km",
            "2",
            "1",
            "1",
            "1",
        ]
        for box in driver.find_elements(By.CSS_SELECTOR, ".layer input:not(:checked)"):
            driver.execute_script("arguments[0].click()", box)
        assert len(driver.find_elements(By.CSS_SELECTOR, ".leaflet-marker-icon")) == 3
        assert driver.find_elements(By.CSS_SELECTOR, "canvas.leaflet-zoom-animated")
        logs = [e for e in driver.get_log("browser") if e["level"] == "SEVERE"]
        assert logs == []
        requests = driver.execute_script(
            "return performance.getEntriesByType('resource').map(e=>e.name)"
        )
        assert [n for n in requests if n.startswith("http")] == []
    finally:
        driver.quit()


def popup_links(driver):
    WebDriverWait(driver, 10).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, ".leaflet-popup a.btn")
    )
    return [
        a.get_attribute("href")
        for a in driver.find_elements(By.CSS_SELECTOR, ".leaflet-popup a.btn")
    ]


def test_fr21_4_the_hash_opens_a_street_change_with_ride_and_street_view_links(page, data):
    first = data["changes"][0]
    driver = open_page(page)
    try:
        driver.get(page.resolve().as_uri() + "#" + first["id"])
        driver.refresh()
        links = popup_links(driver)
        assert len(links) == 2
        ride = RIDE.fullmatch(links[0])
        view = STREET_VIEW.fullmatch(links[1])
        assert ride and view
        origin = [float(ride.group(1)), float(ride.group(2))]
        assert origin in [[e[1], e[0]] for e in first["ends"]]
        assert [float(view.group(1)), float(view.group(2))] == [first["at"][1], first["at"][0]]
        assert "Ash Street" in driver.find_element(By.CSS_SELECTOR, ".leaflet-popup").get_attribute(
            "textContent"
        )
    finally:
        driver.quit()


def test_fr21_4_the_hash_opens_a_bike_path_with_ride_and_street_view_links(page):
    driver = open_page(page)
    try:
        driver.get(page.resolve().as_uri() + "#path-bay-trail")
        driver.refresh()
        links = popup_links(driver)
        ride, view = RIDE.fullmatch(links[0]), STREET_VIEW.fullmatch(links[1])
        assert ride and view
        assert (float(ride.group(1)), float(ride.group(2))) == (-33.95, 151.14)
        assert (float(ride.group(3)), float(ride.group(4))) == (-33.95, 151.16)
        assert (float(view.group(1)), float(view.group(2))) == (-33.95, 151.15)
        assert "Bay Trail" in driver.find_element(By.CSS_SELECTOR, ".leaflet-popup").text
    finally:
        driver.quit()


def test_fr21_4_a_spot_and_a_place_open_a_pin_and_street_view(page, data):
    driver = open_page(page)
    try:
        marker = driver.find_element(By.CSS_SELECTOR, ".pmark")
        ActionChains(driver).move_to_element(marker).click().perform()
        links = popup_links(driver)
        assert PIN.fullmatch(links[0]) and STREET_VIEW.fullmatch(links[1])
        popup = driver.find_element(By.CSS_SELECTOR, ".leaflet-popup")
        assert "Oak School" in popup.get_attribute("textContent")
        driver.execute_script("document.querySelector('.leaflet-popup-close-button').click()")
        WebDriverWait(driver, 10).until(
            lambda d: not d.find_elements(By.CSS_SELECTOR, ".leaflet-popup")
        )
        driver.find_element(By.CSS_SELECTOR, "#spots .item").click()
        links = popup_links(driver)
        spot = data["spots"][0]
        pin, view = PIN.fullmatch(links[0]), STREET_VIEW.fullmatch(links[1])
        assert pin and view
        assert [float(pin.group(1)), float(pin.group(2))] == [spot["at"][1], spot["at"][0]]
    finally:
        driver.quit()


def test_fr21_4_the_google_maps_card_links_the_bike_layer_at_the_middle_of_the_boundary(page):
    driver = open_page(page)
    try:
        link = driver.find_element(By.CSS_SELECTOR, ".gm .files a").get_attribute("href")
        found = BIKE_LAYER.fullmatch(link)
        assert found
        assert (float(found.group(1)), float(found.group(2))) == (-33.9, 151.1)
    finally:
        driver.quit()


def kml_files(data):
    from bikeplan.map_kml import kml_layers

    return kml_layers(data)


def placemarks(blob):
    return etree.fromstring(blob).findall(f".//{KML}Placemark")


def hrefs(placemark):
    text = placemark.find(f"{KML}description").text
    return re.findall(r'href="([^"]+)"', text.replace("&amp;", "&"))


def test_fr21_5_each_layer_file_is_kml_22_and_holds_the_counted_placemarks(data):
    layers = kml_files(data)
    assert list(layers) == [
        "street-changes",
        "spots",
        "all-ages-today",
        "bike-paths-today",
        "painted-lanes-today",
        "places",
        "tfnsw-corridors",
    ]
    counts = {name: len(placemarks(blob)) for name, blob in layers.items()}
    assert counts == {
        "street-changes": 2,
        "spots": 2,
        "all-ages-today": 1,
        "bike-paths-today": 2,
        "painted-lanes-today": 1,
        "places": 1,
        "tfnsw-corridors": 1,
    }
    schema = Schema("ogckml22.xsd")
    for blob in layers.values():
        schema.assertValid(etree.fromstring(blob))


def test_fr21_5_a_placemark_holds_the_same_google_links_as_the_page(data):
    layers = kml_files(data)
    first = data["changes"][0]
    street = next(
        p for p in placemarks(layers["street-changes"]) if p.find(f"{KML}name").text == "Ash Street"
    )
    links = hrefs(street)
    ride, view = RIDE.fullmatch(links[0]), STREET_VIEW.fullmatch(links[1])
    assert ride and view
    assert [float(ride.group(i)) for i in (1, 2, 3, 4)] == [
        first["ends"][0][1],
        first["ends"][0][0],
        first["ends"][1][1],
        first["ends"][1][0],
    ]
    assert [float(view.group(1)), float(view.group(2))] == [first["at"][1], first["at"][0]]
    spot = placemarks(layers["spots"])[0]
    assert PIN.fullmatch(hrefs(spot)[0]) and STREET_VIEW.fullmatch(hrefs(spot)[1])
    place = placemarks(layers["places"])[0]
    assert PIN.fullmatch(hrefs(place)[0]) and STREET_VIEW.fullmatch(hrefs(place)[1])
    path = next(
        p
        for p in placemarks(layers["bike-paths-today"])
        if p.find(f"{KML}name").text == "Bay Trail"
    )
    assert RIDE.fullmatch(hrefs(path)[0])
    assert "Bay Trail" in path.find(f"{KML}description").text
    assert "2.00 km" in path.find(f"{KML}description").text


def test_fr21_5_the_whole_map_file_holds_one_folder_for_each_layer_file(data):
    from bikeplan.map_kml import map_kml

    layers = kml_files(data)
    whole = etree.fromstring(map_kml(layers))
    Schema("ogckml22.xsd").assertValid(whole)
    folders = whole.findall(f".//{KML}Folder")
    assert len(folders) == len(layers)
    for folder, blob in zip(folders, layers.values(), strict=True):
        assert len(folder.findall(f"{KML}Placemark")) == len(placemarks(blob))


def test_fr21_5_a_layer_of_2001_placemarks_or_over_5_mb_fails():
    from bikeplan.map_kml import kml_problems

    def planted(count, pad=""):
        root = etree.Element(f"{KML}kml", nsmap={None: KML[1:-1]})
        document = etree.SubElement(root, f"{KML}Document")
        for index in range(count):
            mark = etree.SubElement(document, f"{KML}Placemark")
            etree.SubElement(mark, f"{KML}name").text = f"P{index}{pad}"
            point = etree.SubElement(mark, f"{KML}Point")
            etree.SubElement(point, f"{KML}coordinates").text = "151.1,-33.9,0"
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    assert kml_problems("ok", planted(2000)) == []
    assert any("2,001" in p for p in kml_problems("many", planted(2001)))
    assert any("5 MB" in p for p in kml_problems("big", planted(10, "x" * 600_000)))
    assert any("not KML" in p for p in kml_problems("bad", b"<kml><oops/>"))


def test_fr21_5_at_most_ten_layer_files(data):
    assert len(kml_files(data)) <= 10


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = with_paths(tmp_path_factory.mktemp("map-snapshot"))
    out = tmp_path_factory.mktemp("map-out")
    assert main(["report", REGION, "--snapshot", str(folder), "--out", str(out)]) == 0
    return out


def test_fr21_3_the_report_run_writes_the_page_the_whole_file_and_the_layer_files(built):
    page = embedded((built / "map.html").read_text())
    names = {p["name"] for p in page["paths"]}
    assert {"Bay Trail", "Park Link"} <= names
    assert "Lane Road" in {p["name"] for p in page["lanes"]}
    layers = sorted(p.name for p in (built / "map-layers").glob("*.kml"))
    assert layers == ["bike-paths-today.kml", "painted-lanes-today.kml"]
    whole = etree.fromstring((built / "map.kml").read_bytes())
    assert len(whole.findall(f".//{KML}Folder")) == len(layers)
    sums = (built / "MAP-SHA256SUMS").read_text()
    assert "  map.html\n" in sums and "  map.kml\n" in sums
    top = (built / "SHA256SUMS").read_text()
    assert "  map.html\n" not in top and "  map.kml\n" not in top
    inner = (built / "map-layers" / "SHA256SUMS").read_text().splitlines()
    assert [line.split("  ")[1] for line in inner] == layers


def test_fr21_3_the_report_run_map_holds_the_bike_path_km_of_the_paths_file(built):
    items = json.loads((built / "paths.json").read_text())["items"]
    page = embedded((built / "map.html").read_text())
    total = sum(i["km"] for i in items if i["kind"] == "path")
    assert page["paths_km"] == pytest.approx(total, abs=0.05)
    assert [p["id"] for p in page["paths"]] == [i["id"] for i in items if i["kind"] == "path"]
    assert all(len(p["ends"]) == 2 for p in page["paths"])


def test_fr21_5_a_council_placemark_holds_its_plan_verdict_and_share(data):
    council = [
        {
            "id": "R1",
            "name": "Bay route",
            "km": 3.0,
            "share": 0.5,
            "v": "partly",
            "lines": [[[151.1, -33.9], [151.2, -33.9]]],
        }
    ]
    layers = kml_files(data | {"council": council})
    mark = placemarks(layers["council-plan"])[0]
    text = "".join(mark.find(f"{KML}description").itertext())
    assert "Verdict: partly" in text
    assert "On my pick: 50%" in text
