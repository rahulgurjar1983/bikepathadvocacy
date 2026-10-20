import html
import json
import re
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from lxml import etree
from selenium import webdriver

from bikeplan.map_kml import NAMESPACE, kml_problems

DATA = re.compile(r'<script id="data" type="application/json">(.*?)</script>', re.S)
COORD = r"-?\d+(?:\.\d{1,6})?%2C-?\d+(?:\.\d{1,6})?"
FORMS = {
    "pin": re.compile(rf"https://www\.google\.com/maps/search/\?api=1&query={COORD}"),
    "street view": re.compile(
        rf"https://www\.google\.com/maps/@\?api=1&map_action=pano&viewpoint={COORD}"
    ),
    "ride": re.compile(
        rf"https://www\.google\.com/maps/dir/\?api=1&origin={COORD}&destination={COORD}"
        r"&travelmode=bicycling"
    ),
    "bike layer": re.compile(
        rf"https://www\.google\.com/maps/@\?api=1&map_action=map&center={COORD}&zoom=13"
        r"&layer=bicycling"
    ),
}
GOOGLE_URL = re.compile(r"https://www\.google\.com/maps[^\s\"'<>]*")
LOCAL = ("file:", "data:", "blob:", "about:")
COUNT_SCRIPT = (
    "return Array.from(document.querySelectorAll('#layers label.layer')).map(label => "
    "[label.querySelector('input').id, label.querySelector('.n').textContent]);"
)


def archive_member(archive: Path, name: str) -> bytes | None:
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if member.name.removeprefix("./") == name and member.isfile():
                return tar.extractfile(member).read()
    return None


def layer_names(archive: Path) -> list[str]:
    with tarfile.open(archive) as tar:
        return sorted(
            member.name.removeprefix("./")
            for member in tar.getmembers()
            if member.isfile()
            and re.fullmatch(r"map-layers/[^/]+\.kml", member.name.removeprefix("./"))
        )


def embedded(text: str) -> dict:
    found = DATA.search(text)
    return json.loads(found[1]) if found else {}


def expected_counts(data: dict) -> dict[str, str]:
    def km(value):
        return f"{value:,.1f} km"

    stage = data["stages"]["today"]["km"]
    sizes = {
        "plan1": len([c for c in data["changes"] if c["stage"] == 1]),
        "plan2": len([c for c in data["changes"] if c["stage"] == 2]),
        "today": km(stage) if data["today"] else 0,
        "paths": km(data["paths_km"]) if data["paths"] else 0,
        "lanes": km(data["lanes_km"]) if data["lanes"] else 0,
        "spots": len(data["spots"]),
        "blockers": len(data["blockers"]),
        "places": len(data["places"]),
        "council": len(data["council"]),
        "tfnsw": len(data["corridors"]),
        "wards": len(data["wards"]),
    }
    return {f"L-{key}": str(value) for key, value in sizes.items() if value}


def browse(page: Path) -> dict:
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)
    try:
        driver.implicitly_wait(5)
        driver.get(page.resolve().as_uri())
        driver.find_element("css selector", "#layers label.layer .n")
        return {
            "log": driver.get_log("browser"),
            "requests": driver.execute_script(
                "return performance.getEntriesByType('resource').map(entry => entry.name);"
            ),
            "counts": driver.execute_script(COUNT_SCRIPT),
            "links": driver.execute_script(
                "return Array.from(document.querySelectorAll('a[href]')).map(a => a.href);"
            ),
        }
    finally:
        driver.quit()


def browser_problems(seen: dict) -> list[str]:
    problems = []
    for url in seen["requests"]:
        if not url.startswith(LOCAL):
            problems.append(f"a network request was made to {url}")
    for entry in seen["log"]:
        message = entry["message"]
        if "net::" in message:
            host = re.search(r"https?://[^\s\"']+", message)
            if not host or host[0] not in seen["requests"]:
                problems.append(f"a network request failed: {message}")
        elif entry["level"] == "SEVERE":
            problems.append(f"a console error: {message}")
    return problems


def count_problems(seen: dict, data: dict) -> list[str]:
    want = expected_counts(data)
    shown = dict(seen["counts"])
    problems = [
        f"layer count for {key.removeprefix('L-')} is {shown.get(key)} on the page, "
        f"{value} in its data"
        for key, value in want.items()
        if shown.get(key) != value
    ]
    problems += [
        f"layer {key.removeprefix('L-')} is on the page but its data is empty"
        for key in shown
        if key not in want
    ]
    return problems


def change_problems(data: dict, report: dict) -> list[str]:
    keys = {(c["street"], c["fix"], c["stage"]) for c in data["changes"]}
    problems = [
        f"work {work['i']} on {work['street']} is in no street change"
        for work in report.get("works", [])
        if (work["street"], work["fix"], work["stage"]) not in keys
        and any(line["w"] == work["i"] and line["s"] in (1, 2) for line in report["lines"])
    ]
    return problems


def path_km_problems(data: dict, figures: list[dict]) -> list[str]:
    found = [f for f in figures if f.get("label") == "Km of bike paths today"]
    if not found:
        return [] if not data["paths"] else ["no bike path km figure to match the map"]
    if round(found[0]["value"], 1) != data["paths_km"]:
        return [f"bike path km is {data['paths_km']} on the map, {found[0]['value']} in the figure"]
    return []


def link_problems(name: str, urls) -> list[str]:
    return [
        f"{name}: Google link {url} matches no form of the spec"
        for url in sorted(set(urls))
        if not any(form.fullmatch(url) for form in FORMS.values())
    ]


def kml_links(blob: bytes) -> list[str]:
    try:
        root = etree.fromstring(blob)
    except etree.XMLSyntaxError:
        return []
    found = []
    for node in root.iter(f"{{{NAMESPACE}}}description"):
        found += [html.unescape(url) for url in GOOGLE_URL.findall(html.unescape(node.text or ""))]
    return found


def files_problems(archive: Path) -> list[str]:
    names = layer_names(archive)
    problems = []
    if len(names) > 10:
        problems.append(f"{len(names)} layer files, over the 10 layers of My Maps")
    blobs = {"map.kml": archive_member(archive, "map.kml")}
    blobs |= {name: archive_member(archive, name) for name in names}
    for name, blob in blobs.items():
        if blob is None:
            problems.append(f"{name} is not in the archive")
            continue
        problems += kml_problems(name, blob)
        problems += link_problems(name, kml_links(blob))
    return problems


def archive_problems(archive: Path) -> list[str]:
    name = archive.name.removesuffix(".tar.gz")
    page = archive_member(archive, "map.html")
    if page is None:
        return [f"{name}: no map.html in the archive"]
    text = page.decode("utf-8")
    data = embedded(text)
    report = embedded((archive_member(archive, "report.html") or b"").decode("utf-8"))
    figures = json.loads(archive_member(archive, "figures.json") or b"[]")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "map.html"
        path.write_bytes(page)
        seen = browse(path)
    found = browser_problems(seen) + count_problems(seen, data)
    found += change_problems(data, report) + path_km_problems(data, figures)
    google = [url for url in seen["links"] if urlparse(url).netloc == "www.google.com"]
    found += link_problems("map.html", google)
    found += files_problems(archive)
    return [f"{name}: {problem}" for problem in found]


def release_problems(release: Path, archive: Path) -> list[str]:
    name = archive.name.removesuffix(".tar.gz")
    problems = []
    for member, kept in (("map.html", f"{name}-map.html"), ("map.kml", f"{name}-map.kml")):
        path = release / kept
        if not path.is_file():
            problems.append(f"{name}: {kept} is not in the release")
        elif path.read_bytes() != archive_member(archive, member):
            problems.append(f"{name}: {kept} differs from {member} in the archive")
    kept = f"{name}-map-layers.zip"
    if not (release / kept).is_file():
        return [*problems, f"{name}: {kept} is not in the release"]
    with zipfile.ZipFile(release / kept) as layers:
        held = {info.filename: layers.read(info) for info in layers.infolist()}
    wanted = {layer.removeprefix("map-layers/"): layer for layer in layer_names(archive)}
    for layer in sorted(wanted.keys() - held.keys()):
        problems.append(f"{name}: {kept} lacks {layer}")
    for layer in sorted(held.keys() - wanted.keys()):
        problems.append(f"{name}: {kept} holds {layer}, which is not in the archive")
    for layer in sorted(held.keys() & wanted.keys()):
        if held[layer] != archive_member(archive, wanted[layer]):
            problems.append(f"{name}: {kept} differs from {layer} in the archive")
    return problems


def map_problems(release: Path) -> list[str]:
    archives = sorted(p for p in release.glob("*.tar.gz") if p.name != "artifacts.tar.gz")
    found = [archive for archive in archives if archive_member(archive, "options.json")]
    if not found:
        return ["no region report in the release holds a map"]
    return [
        problem
        for archive in found
        for problem in archive_problems(archive) + release_problems(release, archive)
    ]
