import html
import json
import re
from datetime import date

from bikeplan.report import ASSETS, MONTHS

TEMPLATE = ASSETS / "report_template.html"
SPOT_KINDS = {
    "raised_zebra_crossing": "zebra",
    "bike_walk_signals": "signals",
    "short_path_crossing": "path",
}
EVIDENCE_CSS = (
    "#evidence .in{overflow-wrap:anywhere}"
    "#evidence .in pre{overflow-x:auto;white-space:pre-wrap;background:#f4f4f4;color:#16213a;"
    "padding:.5rem}"
    "#evidence .in table{border-collapse:collapse;width:100%;max-width:100%;table-layout:fixed}"
    "#evidence .in td,#evidence .in th{border:1px solid #444;padding:.25rem .5rem;text-align:left}"
    "#evidence .in svg{max-width:100%;height:auto}"
    "#evidence .in fieldset{min-width:0;border:1px solid #444;margin:.5rem 0}"
    "#evidence .in input{max-width:100%}#evidence .in label{display:block}"
    "#network-map{height:24rem;border:1px solid #444}"
    ".tiles .tile:last-child:nth-child(odd){grid-column:1/-1}"
)


def round_point(point) -> list[float]:
    return [round(point[0], 5), round(point[1], 5)]


def centre(points: list) -> list[float] | None:
    if not points:
        return None
    return round_point(
        [sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)]
    )


def boundary_polygons(boundary) -> list:
    if not boundary:
        return []
    shape = boundary
    if shape.get("type") == "FeatureCollection":
        shape = shape["features"][0]
    if shape.get("type") == "Feature":
        shape = shape["geometry"]
    polygons = [shape["coordinates"]] if shape["type"] == "Polygon" else shape["coordinates"]
    return [[[round_point(point) for point in ring] for ring in polygon] for polygon in polygons]


def stage_values(step: dict) -> dict:
    totals = step["totals"]
    return {
        "score": totals["score"],
        "safe": totals["safe_trips"],
        "trips": totals["trips"],
        "km": totals["km_all_ages"],
        "places": totals["places_safe"],
        "park": step["disruption"]["parking_spaces"],
        "lane": step["disruption"]["lane_km"],
        "slow": step["disruption"]["speed_km"],
    }


def street_lines(streets: dict | None) -> list:
    pieces = (streets or {}).get("model_pieces") or []
    return [
        [[round(lon, 5), round(lat, 5)] for lat, lon in line]
        for piece in pieces
        for line in piece["lines"]
    ]


def spot_list(pick: dict, owner_step: dict, places: dict) -> list:
    spots = []
    for index, item in enumerate(pick["works"]):
        if not item.get("spot") or index not in places:
            continue
        step = owner_step.get(index)
        gain = 0
        if step:
            before = pick["steps"][step - 1]["totals"]["safe_trips"]
            gain = pick["steps"][step]["totals"]["safe_trips"] - before
            gain = round(gain / len(pick["steps"][step]["works"]))
        spots.append(
            {
                "w": index,
                "at": places[index],
                "m": item["km"] * 1000,
                "street": item["street"],
                "kind": SPOT_KINDS[item["fix"]],
                "trips": gain,
                "owner": item.get("owner"),
            }
        )
    spots.sort(key=lambda found: (-found["trips"], found["street"], found["w"]))
    return [{"n": number} | found for number, found in enumerate(spots, 1)]


def report_data(options, choice, marks, joined, streets, corridor, boundary) -> dict:
    pick = next(item for item in options if item["id"] == choice["pick"])
    rec = choice["step"]
    steps = pick["steps"]
    owner_step: dict = {}
    for number, step in enumerate(steps):
        for index in step["works"]:
            owner_step.setdefault(index, number)
    ends: dict = {}
    for line in pick["lines"]:
        if line["work"] is not None:
            ends.setdefault(line["work"], []).extend(line["line"])
    places = {index: centre(points) for index, points in ends.items()}
    lines = []
    for line in pick["lines"]:
        index = line["work"]
        if line["ok"]:
            state = 0
        elif index is None:
            state = 4
        elif pick["works"][index].get("spot"):
            state = 3
        else:
            state = 1 if owner_step.get(index, len(steps)) <= rec else 2
        lines.append({"c": line["line"], "s": state, "w": index})
    works = [
        {
            "i": index,
            "street": item["street"],
            "fix": item["fix"],
            "km": item["km"],
            "park": item["parking_spaces"],
            "lane": item["lane_km"],
            "slow": item["speed_km"],
            "stage": 1 if owner_step.get(index, len(steps)) <= rec else 2,
            "at": places.get(index),
        }
        for index, item in enumerate(pick["works"])
        if not item.get("spot")
    ]
    data = {
        "base": {
            "water": [],
            "park": [],
            "air": [],
            "outside": [],
            "rail": [],
            "boundary": boundary_polygons(boundary),
        },
        "streets": street_lines(streets),
        "lines": lines,
        "works": works,
        "spots": spot_list(pick, owner_step, places),
        "places": [
            {
                "name": mark["name"],
                "type": mark["type"],
                "at": round_point([mark["lon"], mark["lat"]]),
            }
            for mark in marks
        ],
        "stages": {
            "today": stage_values(steps[0]),
            "first": stage_values(steps[rec]),
            "works": stage_values(steps[-1]),
        },
        "steps": [
            {
                "w": step["works"],
                "score": step["totals"]["score"],
                "km": step["totals"]["km_all_ages"],
                "park": step["disruption"]["parking_spaces"],
                "schools": step["totals"]["places_safe"].get("school", 0),
            }
            for step in steps
        ],
        "rec": rec,
        "ceiling": pick["ceiling"],
        "joined": joined,
        "corridors": [],
    }
    if corridor:
        data["corridors"] = [
            {"id": route["id"], "lines": route["lines"]} for route in corridor["routes"]
        ]
        data["corridor_counts"] = corridor["counts"]
        data["corridor_source"] = {name: corridor["source"][name] for name in ("title", "date")}
    return data


def drop_section(text: str, name: str) -> str:
    return re.sub(rf'<section class="band[^"]*" id="{name}">.*?</section>\n*', "", text, flags=re.S)


def drop_card(text: str, name: str) -> str:
    return re.sub(
        rf'<div class="card" id="card-{name}">.*?(?=<div class="card" id="card-)',
        "",
        text,
        flags=re.S,
    )


def drop_button(text: str, name: str) -> str:
    return re.sub(rf'\s*<button type="button" id="ly-{name}"[^>]*>.*?</button>', "", text)


def author_line(region) -> str:
    author = region.report.author
    if not author:
        return ""
    name = author.split(",")[0]
    initials = "".join(word[0] for word in name.split()[:2]).upper()
    day = date.fromisoformat(region.snapshot.osm_date[:10])
    return (
        f'<div class="author"><span class="av" aria-hidden="true">{html.escape(initials)}</span>'
        f"<span>By {html.escape(author)}. {MONTHS[day.month - 1]} {day.year}.</span></div>"
    )


def credits(data: dict) -> str:
    text = "Map data © OpenStreetMap contributors (ODbL)."
    if "corridor_source" in data:
        source = data["corridor_source"]
        text += f" Corridors: {source['title']}, {source['date']}."
    return html.escape(text)


def place_figures(figures) -> dict:
    found = {}
    for item in figures:
        match = re.fullmatch(r"Places of type (\w+), joined", item["label"])
        if match:
            found[match[1]] = item["id"]
    return found


def five_minute_page(region, data: dict, head: str, inner: str, figures=()) -> str:
    data = data | {"figs": place_figures(figures)}
    area_full = region.name.split(",")[0]
    area = area_full.removesuffix(" Council")
    day = date.fromisoformat(region.snapshot.osm_date[:10])
    text = TEMPLATE.read_text()
    have = {
        "spots": bool(data["spots"]),
        "streets": bool(data["works"]),
        "plans": bool(data["corridors"]),
    }
    for name, kept in have.items():
        if not kept:
            text = drop_section(text, name)
    for name in ("wards", "cost"):
        text = drop_section(text, name)
    if "cost" not in data["stages"]["works"]:
        text = re.sub(r'<div class="tile cost">.*?</div>', "", text, flags=re.S)
    text = drop_button(drop_button(text, "council"), "wards")
    if have["plans"]:
        text = drop_card(text, "council")
    else:
        text = drop_button(text, "tfnsw")
        text = re.sub(r'\s*<div class="mapctl".*?</div>', "", text, count=1, flags=re.S)
    headline = f"All-ages bike routes for {area}\u2019s schools, stations and shops"
    for key, value in {
        "TITLE": f"Bike paths in {html.escape(region.name)}",
        "DESCRIPTION": html.escape(headline),
        "AREA_FULL": html.escape(area_full),
        "AREA": html.escape(area),
        "HEADLINE": html.escape(headline),
        "AUTHOR": author_line(region),
        "SNAPSHOT_DATE": f"{day.day} {MONTHS[day.month - 1]} {day.year}",
        "CREDITS": credits(data),
    }.items():
        text = text.replace("{{" + key + "}}", value)
    for key, value in {
        "EXTRA_CSS": EVIDENCE_CSS,
        "LEAFLET_CSS": (ASSETS / "leaflet.css").read_text(),
        "LEAFLET_JS": (ASSETS / "leaflet.js").read_text(),
        "DATA_JSON": json.dumps(data, sort_keys=True, separators=(",", ":")).replace("</", "<\\/"),
        "EVIDENCE": inner,
    }.items():
        text = text.replace("{{" + key + "}}", value)
    old = (ASSETS / "leaflet.css").read_text(), (ASSETS / "leaflet.js").read_text()
    head = head.replace(old[0], "").replace(f"<script>{old[1]}</script>", "")
    return text.replace("</head>", f"{head}</head>", 1)
