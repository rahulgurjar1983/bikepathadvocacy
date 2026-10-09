import csv
import hashlib
import html
import importlib.util
import io
import json
import re
from datetime import date
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import linemerge, transform

from bikeplan.config import ConfigError, Profile, Region
from bikeplan.network import bike_segments
from bikeplan.stress import score_edges
from bikeplan.width import fuse

SOURCES = [
    {
        "name": "OpenStreetMap contributors",
        "licence": "ODbL 1.0",
        "request": "network.osm.gz and boundary.geojson in the snapshot folder",
    }
]
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
ASSETS = Path(__file__).parent / "assets"
STATION_TAGS = (
    ("railway", "station"),
    ("railway", "halt"),
    ("railway", "tram_stop"),
    ("public_transport", "station"),
    ("amenity", "ferry_terminal"),
)
MAP_FIGURE = (
    "F4",
    "Street piece drawn on the map",
    "spec 13",
    "I join street segments that touch and share a name, street type, stress level, safety and "
    "fix. I draw each joined piece once. I count the pieces I drew.",
)
MAP_RECIPE = "import json;print(len(json.load(open('map.json'))['segments']))"
LEVEL_KEYS = (
    ("1", "Level one: the calmest (pale blue)"),
    ("2", "Level two: calm (dark blue)"),
    ("3", "Level three: busy (pale red)"),
    ("4", "Level four: the busiest (dark red)"),
)
HEADER = ["segment_id", "length_m", "lts", "aaa", "width_source", "fix"]
FIGURES = [
    (
        "F1",
        "Street a bike may use",
        "spec 03",
        "I add up the length of every street segment inside the boundary where a bike may ride.",
        "True",
    ),
    (
        "F2",
        "Street that is safe for a child to ride alone (AAA)",
        "spec 04",
        "I score each edge for stress and keep the segments where every edge is AAA.",
        "r['aaa'] == '1'",
    ),
    (
        "F3",
        "Street with no width estimate",
        "spec 05",
        "I try each width source in rank order. I count the segments where none gave a width.",
        "r['width_source'] == 'none'",
    ),
]
KEEP = {
    "F1": lambda r: True,
    "F2": lambda r: r["aaa"] == "1",
    "F3": lambda r: r["width_source"] == "none",
}
RECIPE = (
    "import csv;"
    "print(round(sum(float(r['length_m']) for r in csv.DictReader(open('segments.csv')) if {test})"
    "/1000,3))"
)


def segment_rows(graph, profile: Profile, fixes: dict) -> list[list]:
    scores = score_edges(graph, profile)
    rows = []
    for segment_id, segment in bike_segments(graph).items():
        keys, datas = zip(*segment["edges"], strict=True)
        found = fuse(datas[0], profile)
        rows.append(
            [
                str(segment_id),
                f"{segment['inside_m']:.3f}",
                max(scores[key]["lts"] for key in keys),
                int(all(scores[key]["aaa"] for key in keys)),
                found["width_source"] or "none",
                fixes.get(segment_id) or "",
            ]
        )
    return sorted(rows)


def segments_text(rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buffer.getvalue()


def first(value) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return "" if value is None else str(value)


def map_lines(segment, graph, to_lonlat) -> list[list[list[float]]]:
    (u, v, _), data = segment["edges"][0]
    line = data.get("geometry") or LineString(
        [(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
    )
    inside = line.intersection(graph.graph["boundary"])
    parts = [inside] if isinstance(inside, LineString) else getattr(inside, "geoms", [])
    lines = []
    for part in parts:
        if isinstance(part, LineString) and not part.is_empty:
            lonlat = transform(to_lonlat.transform, part)
            lines.append([[round(lat, 5), round(lon, 5)] for lon, lat in lonlat.coords])
    return lines


def place_kind(tags: dict) -> str | None:
    if tags.get("amenity") == "school":
        return "school"
    if any(tags.get(key) == value for key, value in STATION_TAGS):
        return "station"
    return None


def map_places(snapshot: Path) -> list[dict]:
    path = snapshot / "places.json"
    if not path.is_file():
        return []
    places = []
    for element in json.loads(path.read_text())["elements"]:
        tags = element.get("tags", {})
        point = element if "lat" in element else element.get("center")
        kind = place_kind(tags)
        if kind and point:
            places.append(
                {
                    "kind": kind,
                    "name": first(tags.get("name")),
                    "lat": round(point["lat"], 5),
                    "lon": round(point["lon"], 5),
                }
            )
    return sorted(places, key=lambda p: (p["kind"], p["lat"], p["lon"], p["name"]))


def merge_pieces(pieces: list[dict]) -> list[dict]:
    groups: dict = {}
    for item in pieces:
        key = (item["name"], item["highway"], item["lts"], item["aaa"], item["fix"] or "")
        groups.setdefault(key, []).extend(LineString(line) for line in item["lines"])
    merged = []
    for key in sorted(groups):
        name, highway, lts, aaa, fix = key
        joined = linemerge(sorted(groups[key], key=lambda line: list(line.coords)))
        for line in getattr(joined, "geoms", [joined]):
            coords = [list(point) for point in line.coords]
            merged.append(
                {
                    "name": name,
                    "highway": highway,
                    "lts": lts,
                    "aaa": aaa,
                    "fix": fix or None,
                    "lines": [coords],
                }
            )
    return sorted(merged, key=lambda item: (item["lines"][0], item["name"], item["highway"]))


def map_data(graph, rows: list[list], snapshot: Path, projects: dict) -> dict:
    to_lonlat = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    scored = {row[0]: row for row in rows}
    segments = []
    for segment_id, segment in bike_segments(graph).items():
        lines = map_lines(segment, graph, to_lonlat)
        if not lines:
            continue
        row = scored[str(segment_id)]
        data = segment["edges"][0][1]
        segments.append(
            {
                "name": first(data.get("name")),
                "highway": first(data.get("highway")),
                "lts": row[2],
                "aaa": bool(row[3]),
                "fix": row[5] or None,
                "lines": lines,
            }
        )
    boundary = json.loads((snapshot / "boundary.geojson").read_text())
    return {
        "boundary": boundary,
        "places": map_places(snapshot),
        "projects": projects,
        "segments": merge_pieces(segments),
    }


def figure_list(text: str, map_text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text)))
    digest = hashlib.sha256(text.encode()).hexdigest()
    figures = []
    for figure_id, label, spec, method, test in FIGURES:
        km = sum(float(r["length_m"]) for r in rows if KEEP[figure_id](r)) / 1000
        figures.append(
            {
                "id": figure_id,
                "label": label,
                "value": round(km, 3),
                "unit": "km",
                "spec": spec,
                "method": method,
                "inputs": [{"name": "segments.csv", "sha256": digest}],
                "sources": SOURCES,
                "recipe": RECIPE.format(test=test),
            }
        )
    figure_id, label, spec, method = MAP_FIGURE
    pieces = len(json.loads(map_text)["segments"])
    figures.append(
        {
            "id": figure_id,
            "label": label,
            "value": pieces,
            "unit": "pieces",
            "spec": spec,
            "method": method,
            "inputs": [
                {"name": "map.json", "sha256": hashlib.sha256(map_text.encode()).hexdigest()}
            ],
            "sources": SOURCES,
            "recipe": MAP_RECIPE,
        }
    )
    return figures


def link(item: dict) -> str:
    return f'<a href="#{item["id"]}">{item["value"]} {item["unit"]} ({item["id"]})</a>'


def entry(item: dict) -> str:
    inputs = "".join(
        f"<li>{html.escape(part['name'])}, sha256 <code>{part['sha256']}</code></li>"
        for part in item["inputs"]
    )
    sources = "".join(
        f"<li>{html.escape(part['name'])}, licence {html.escape(part['licence'])}, "
        f"request: {html.escape(part['request'])}</li>"
        for part in item["sources"]
    )
    return (
        f'<article id="{item["id"]}"><h3>{item["id"]}: {html.escape(item["label"])}</h3>'
        f"<dl><dt>Value</dt><dd>{item['value']} {item['unit']}</dd>"
        f"<dt>Method</dt><dd>{html.escape(item['spec'])}. {html.escape(item['method'])}</dd>"
        f"<dt>Files</dt><dd><ul>{inputs}</ul></dd>"
        f"<dt>Sources</dt><dd><ul>{sources}</ul></dd>"
        "<dt>Recipe: run it with python3 -c in a folder that holds the release files</dt>"
        f"<dd><pre>{html.escape(item['recipe'])}</pre></dd></dl></article>"
    )


STYLE = (
    "body{max-width:48rem;margin:0 auto;padding:0 1rem;font-family:sans-serif;line-height:1.5;"
    "overflow-wrap:anywhere}"
    "pre{overflow-x:auto;white-space:pre-wrap;background:#f4f4f4;padding:.5rem}"
    "table{border-collapse:collapse;width:100%;max-width:100%;table-layout:fixed}"
    "td,th{border:1px solid #444;padding:.25rem .5rem;text-align:left}"
    "svg{max-width:100%;height:auto}fieldset{min-width:0}input{max-width:100%}"
    "#report-map-canvas{height:24rem;background:#fff;border:1px solid #444}"
    "#report-map fieldset{border:1px solid #444;margin:.5rem 0}"
    "#report-map label{display:block}"
    "@media print{body{max-width:none;font-size:11pt}a{color:inherit}"
    "article,table,svg{break-inside:avoid}}"
)
GLOSSARY = {
    "ADT": "average daily traffic: how many motor vehicles use a street in a day.",
    "AAA": "All Ages and Abilities: a street that is safe for a child or an older rider.",
    "access": "how many needed places a home can reach by bike.",
    "bike": "a bicycle, including an electric bicycle.",
    "claim": "a plan statement that route data can check.",
    "disruption": "what a change takes from people who drive or park today.",
    "Furth": "Peter Furth, who wrote the stress tables that I use.",
    "km": "a kilometre, which is one thousand metres.",
    "method": "the steps and measures used to get a result.",
    "OpenStreetMap": "the free map of the world that volunteers keep up to date.",
    "profile": "the list of rules and numbers that I use for one country.",
    "project": "a set of street and junction changes that I propose together.",
    "reserve": "the strip of land beside a street that the public owns.",
    "snapshot": "one saved copy of the open data that I read.",
    "council": "the local government that runs the streets in an area.",
    "data": "facts and numbers that I read from a file.",
    "width": "how wide a street or lane is, in metres.",
}
BAR_FILLS = ("#1b5e8a", "#2e7d32", "#8a5a00")


def glossary_section(terms: dict[str, str]) -> str:
    items = "".join(
        f"<dt>{html.escape(term)}</dt><dd>{html.escape(meaning)}</dd>"
        for term, meaning in terms.items()
    )
    return f'<section id="report-glossary"><h2>Words I use</h2><dl>{items}</dl></section>'


def has_stage(name: str) -> bool:
    return importlib.util.find_spec(f"bikeplan.{name}") is not None


def map_section(by_id: dict, proposed_ready: bool) -> str:
    keys = "".join(
        f'<label><input type="checkbox" id="layer-lts-{level}" checked> {text}</label>'
        for level, text in LEVEL_KEYS
    )
    disabled = "" if proposed_ready else " disabled"
    note = (
        ""
        if proposed_ready
        else "Proposed changes stay off. The code does not rank projects yet, so there are none "
        "to draw."
    )
    return (
        '<section id="map"><section id="report-map"><h2>Map of every street a bike may use</h2>'
        f"<p>Each line is one street segment. The map draws {link(by_id['F4'])} of street. "
        "Hover over a line, or tap it, to read the street name, its type, its stress level and "
        "whether it is safe for all ages. The dashed line is the council boundary.</p>"
        f"<fieldset><legend>Layers</legend>{keys}"
        '<label><input type="checkbox" id="layer-aaa"> Only streets that are safe for all '
        "ages</label>"
        '<label><input type="checkbox" id="layer-stations"> Stations (white dots)</label>'
        '<label><input type="checkbox" id="layer-schools"> Schools (yellow dots)</label>'
        f'<label><input type="checkbox" id="layer-proposed"{disabled}> Proposed changes</label>'
        '<label><input type="checkbox" id="layer-survey"> Survey options</label>'
        f'<p id="proposed-note">{note}</p></fieldset>'
        '<div id="report-map-canvas" role="region" aria-label="Map of the streets"></div>'
        "</section></section>"
    )


def map_scripts(map_text: str, data_script: str) -> str:
    safe = map_text.replace("</", "<\\/")
    return (
        f"<style>{(ASSETS / 'leaflet.css').read_text()}</style>"
        f"<script>{(ASSETS / 'leaflet.js').read_text()}</script>"
        f"{data_script}"
        f'<script type="application/json" id="map-data">{safe}</script>'
        f"<script>{(ASSETS / 'map.js').read_text()}</script>"
    )


def chart(figures: list[dict]) -> str:
    top = max(item["value"] for item in figures) or 1
    bars = "".join(
        f'<text x="0" y="{index * 40 + 14}">{html.escape(item["label"])}</text>'
        f'<rect x="0" y="{index * 40 + 20}" width="{item["value"] / top * 100:.1f}%" '
        f'height="14" fill="{BAR_FILLS[index % len(BAR_FILLS)]}"/>'
        for index, item in enumerate(figures)
    )
    rows = "".join(
        f"<tr><td>{html.escape(item['label'])}</td><td>{link(item)}</td></tr>" for item in figures
    )
    return (
        '<section id="chart"><h2>Street length at a glance</h2>'
        f'<svg id="chart-length" role="img" width="100%" height="{len(figures) * 40}" '
        'aria-labelledby="chart-length-title">'
        '<title id="chart-length-title">Bar chart of street length in kilometres for each group'
        f"</title>{bars}</svg>"
        '<table data-for="chart-length"><caption>The same lengths as a table</caption>'
        f"<tr><th>Group</th><th>Length</th></tr>{rows}</table></section>"
    )


TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def leaks(text: str, folders) -> list[str]:
    found = [str(folder) for folder in folders if str(folder) != "/" and str(folder) in text]
    return found + TIMESTAMP.findall(text)


def snapshot_date(region: Region) -> str:
    day = date.fromisoformat(region.snapshot.osm_date[:10])
    return f"<time>{day.day} {MONTHS[day.month - 1]} {day.year}</time>"


def page(
    region: Region,
    figures: list[dict],
    map_text: str,
    details: str,
    data_script: str,
    change: str = "",
    change_head: str = "",
    opening: str = "",
):
    by_id = {item["id"]: item for item in figures}
    appendix = "".join(entry(item) for item in figures)
    area = region.name.split(",")[0]
    terms = {area: "the council area this report covers.", **GLOSSARY}
    author = f"<p>By {html.escape(region.report.author)}</p>" if region.report.author else ""
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Bike paths in {html.escape(region.name)}</title>"
        f"<style>{STYLE}</style>{map_scripts(map_text, data_script)}{change_head}</head><body>"
        f"<h1>Bike paths in {html.escape(region.name)}</h1>"
        f"{author}"
        f"{opening}"
        f"{map_section(by_id, has_stage('propose'))}"
        f"{change}"
        '<section id="neighbourhoods"><h2>Neighbourhood benefits and impacts</h2>'
        "<p>Area-level trips and space changes are unknown. Area boundaries and resident unions "
        'still need proof. See the <a href="#street-plans">local works</a>.</p></section>'
        '<section id="street-plans"><h2>Street plans</h2>'
        "<p>Local plans for the selected proposal are pending. The "
        '<a href="#projects">old minimum-gain shortlist</a> and '
        '<a href="#sheets">its project sheets</a> are separate evidence. '
        "They may differ from the selected curve and do not prove its local impacts.</p></section>"
        '<section id="delivery"><h2>Delivery and next decision</h2>'
        "<p>I seek studies and a costed concept design before detailed design or construction. "
        "Costs, upkeep, owner, approvals, first build stage and funding are unknown. "
        'Dates are not commitments. See my <a href="#council-ask">council ask</a>.</p></section>'
        '<section id="evidence"><h2>Evidence and model limits</h2>'
        f"<p>I checked {link(by_id['F1'])} of street that a bike may use. "
        f"{link(by_id['F2'])} meets the model's all-ages criteria. "
        f"For {link(by_id['F3'])} I have no width. A model result does not prove field safety.</p>"
        "<p>Model scores and type gains follow in the selected totals. Before is the baseline; "
        "after is the selected step. Type gains are not a unique resident count. "
        "The calm first-leg allowance is a model assumption, "
        "not a confirmed complete trip.</p></section>"
        f"{glossary_section(terms)}"
        f'<section id="appendix"><h2>How to check every number</h2>'
        f"<p>This report uses the data snapshot of {snapshot_date(region)}.</p>{appendix}"
        f"{details}</section>"
        "</body></html>\n"
    )


def check_leaks(html_text: str, out, snapshot) -> None:
    found = leaks(html_text, [Path(out).resolve(), Path(snapshot).resolve(), Path.cwd().resolve()])
    if found:
        raise ConfigError(f"the report holds a time stamp or path: {found}")
