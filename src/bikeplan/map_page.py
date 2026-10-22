import html
import json
import re
from datetime import date

from bikeplan.map_kml import bike_layer
from bikeplan.report import ASSETS, MONTHS

TEMPLATE = ASSETS / "map_template.html"
SECTIONS = {
    "changes": lambda data: data["changes"],
    "paths": lambda data: data["paths"] or data["lanes"],
    "spots": lambda data: data["spots"],
    "council": lambda data: data["council"],
}


def drop_section(text: str, name: str) -> str:
    return re.sub(
        rf'\s*<section[^>]*aria-labelledby="h-{name}">.*?</section>', "", text, count=1, flags=re.S
    )


def footer(region, data: dict) -> str:
    day = date.fromisoformat(region.snapshot.osm_date[:10])
    lines = []
    if region.report.author:
        lines.append(f"Map by {region.report.author}.")
    lines.append(
        f"Street data © OpenStreetMap contributors, {day.day} {MONTHS[day.month - 1]} {day.year}, "
        f"snapshot {data['tag']}. Ratings are modelled from open data, not measured on site."
    )
    if "corridor_source" in data:
        source = data["corridor_source"]
        lines.append(f"Corridors: {source['title']}, {source['date']}.")
    return "".join(f"<p>{html.escape(line)}</p>" for line in lines)


def map_page(region, data: dict) -> str:
    text = TEMPLATE.read_text()
    for name, found in SECTIONS.items():
        if not found(data):
            text = drop_section(text, name)
    author = region.report.author
    owner = f"{author.split(',')[0]}\u2019s " if author else "the "
    for key, value in {
        "AREA": html.escape(data["area"]),
        "OPTION": html.escape(data["option"]),
        "OWNER": html.escape(owner),
        "BIKE_LINK": html.escape(bike_layer(data["centre"])),
        "FOOTER": footer(region, data),
    }.items():
        text = text.replace("{{" + key + "}}", value)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    for key, value in {
        "LEAFLET_CSS": (ASSETS / "leaflet.css").read_text(),
        "LEAFLET_JS": (ASSETS / "leaflet.js").read_text(),
        "DATA_JSON": payload,
    }.items():
        text = text.replace("{{" + key + "}}", value)
    return text
