import hashlib
import html
import json
import re
from datetime import date

from bikeplan.cost import stage_cost, work_cost
from bikeplan.edition import PICK, fact
from bikeplan.report import ASSETS, MONTHS, SOURCES

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


def spot_list(pick: dict, places: dict) -> list:
    spots = []
    for index, item in enumerate(pick["works"]):
        if not item.get("spot") or index not in places:
            continue
        spots.append(
            {
                "w": index,
                "at": places[index],
                "m": item["km"] * 1000,
                "street": item["street"],
                "kind": SPOT_KINDS[item["fix"]],
                "trips": item["trips"],
                "owner": item.get("owner"),
            }
        )
    spots.sort(key=lambda found: (-found["trips"], found["street"], found["w"]))
    return [{"n": number} | found for number, found in enumerate(spots, 1)]


def stage_costs(works: list, built: set, rates: dict) -> dict:
    chosen = [item for index, item in enumerate(works) if index in built]
    found = stage_cost(chosen, rates)
    return {
        "cost": found["likely"],
        "cost_low": found["low"],
        "cost_high": found["high"],
        "cost_text": found["text"],
        "cost_missing": found["missing"],
        "n_works": sum(not item.get("spot") for item in chosen),
        "n_spots": sum(bool(item.get("spot")) for item in chosen),
    }


def report_data(
    options, choice, marks, joined, streets, corridor, boundary, paths=(), rates=None
) -> dict:
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
    if rates:
        for found in works:
            cost = work_cost(pick["works"][found["i"]], rates)
            found["cost"] = None if cost is None else cost / 1_000_000
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
        "paths": [
            {key: item[key] for key in ("id", "name", "km", "share", "lines")}
            for item in paths
            if item["kind"] == "path"
        ],
        "path_km": {
            "all": round(sum(item["km"] for item in paths if item["kind"] == "path"), 1),
            "pick": round(sum(item["on_pick"] for item in paths if item["kind"] == "path"), 1),
        },
        "lines": lines,
        "works": works,
        "spots": spot_list(pick, places),
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
        "before_spots": pick["no_spots"],
        "joined": joined,
        "corridors": [],
    }
    if rates:
        everything = set(range(len(pick["works"])))
        early = {index for index in everything if owner_step.get(index, len(steps)) <= rec}
        for name, built in (("today", set()), ("first", early), ("works", everything)):
            data["stages"][name] |= stage_costs(pick["works"], built, rates)
        data["cost_note"] = rates["note"]
        data["spot_cost"] = sum(
            (work_cost(item, rates) or 0) / 1_000_000 for item in pick["works"] if item.get("spot")
        )
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


def price_works(options, rates) -> None:
    for option in options:
        for item in option["works"]:
            cost = work_cost(item, rates)
            if cost is not None:
                item["price"] = [cost * rates["low"], cost * rates["high"]]


def stage_cost_facts(pick, rec) -> list[dict]:
    built = {
        "first stage": (
            f"w={{i for s in p['steps'][:{rec}+1] for i in s['works']}};",
            {index for step in pick["steps"][: rec + 1] for index in step["works"]},
        ),
        "full plan": ("w=set(range(len(p['works'])));", set(range(len(pick["works"])))),
    }
    facts = []
    for name, (pick_works, chosen) in built.items():
        for end, key in (("low", 0), ("high", 1)):
            total = sum(
                item["price"][key]
                for index, item in enumerate(pick["works"])
                if index in chosen and "price" in item
            )
            facts.append(
                fact(
                    f"Cost of the {name} of my pick, {end} end",
                    total / 1_000_000,
                    "$ million",
                    2,
                    f"{PICK}{pick_works}print(round(sum(x['price'][{key}] "
                    "for i,x in enumerate(p['works']) if i in w and 'price' in x)/1e6,2))",
                    f"the {end} end of the cost of the {name}",
                )
            )
    return facts


def page_figures(options, choice, text, first) -> list[dict]:
    pick = next(item for item in options if item["id"] == choice["pick"])
    spots = [item for item in pick["works"] if item.get("spot")]
    plain = [item for item in pick["works"] if not item.get("spot")]
    digest = hashlib.sha256(text.encode()).hexdigest()
    keep = "w.get('spot')"
    facts = []
    if spots:
        facts += [
            fact(
                "Spots of my pick",
                len(spots),
                "spots",
                0,
                f"{PICK}print(sum(1 for w in p['works'] if {keep}))",
                "the spots",
            ),
            fact(
                "Length of the spots of my pick",
                sum(item["km"] for item in spots),
                "km",
                1,
                f"{PICK}print(round(sum(w['km'] for w in p['works'] if {keep}),1))",
                "the spot lengths",
            ),
            fact(
                "Safety score of my pick without its spots",
                pick["no_spots"],
                "points",
                1,
                f"{PICK}print(round(p['no_spots'],1))",
                "the score without spots",
            ),
            fact(
                "Safety score of my pick with every work built",
                pick["steps"][-1]["totals"]["score"],
                "points",
                1,
                f"{PICK}print(round(p['steps'][-1]['score'],1))",
                "the full plan score",
            ),
        ]
    if spots and "no_spots_safe" in pick:
        last = pick["steps"][-1]["totals"]
        facts.append(
            fact(
                "Share of trips made safe by spots alone",
                (last["safe_trips"] - pick["no_spots_safe"]) / last["trips"] * 100,
                "%",
                1,
                f"{PICK}s=p['steps'][-1];"
                "print(round((s['safe_trips']-p['no_spots_safe'])/s['trips']*100,1))",
                "the trips made safe by the spots",
            )
        )
    if any("price" in item for item in pick["works"]):
        facts += stage_cost_facts(pick, choice["step"])
    for fix in sorted({item["fix"] for item in plain}):
        facts.append(
            fact(
                f"Km of {fix} works of my pick",
                sum(item["km"] for item in plain if item["fix"] == fix),
                "km",
                1,
                f"{PICK}print(round(sum(w['km'] for w in p['works'] "
                f"if not {keep} and w['fix']=={fix!r}),1))",
                f"the {fix} lengths",
            )
        )
    return fact_figures(facts, first, "options.json", digest)


def path_figures(items, text, first) -> list[dict]:
    if not items:
        return []
    digest = hashlib.sha256(text.encode()).hexdigest()
    load = "import json;items=json.load(open('paths.json'))['items'];"
    facts = [
        fact(
            "Km of bike paths today",
            sum(item["km"] for item in items if item["kind"] == "path"),
            "km",
            1,
            f"{load}print(round(sum(i['km'] for i in items if i['kind']=='path'),1))",
            "the length of every bike path today",
        ),
        fact(
            "Km of painted bike lanes today",
            sum(item["km"] for item in items if item["kind"] == "lane"),
            "km",
            1,
            f"{load}print(round(sum(i['km'] for i in items if i['kind']=='lane'),1))",
            "the length of every painted bike lane today",
        ),
        fact(
            "Km of bike paths today on my pick",
            sum(item["on_pick"] for item in items if item["kind"] == "path"),
            "km",
            1,
            f"{load}print(round(sum(i['on_pick'] for i in items if i['kind']=='path'),1))",
            "the length of bike paths within 15 m of my pick",
        ),
    ]
    return fact_figures(facts, first, "paths.json", digest)


def fact_figures(facts, first, name, digest) -> list[dict]:
    return [
        {
            "id": f"F{first + number}",
            "label": item["label"],
            "value": item["value"],
            "unit": item["unit"],
            "spec": "spec 20" if name == "options.json" else "spec 21",
            "method": f"I read {item['method']} from {name}.",
            "inputs": [{"name": name, "sha256": digest}],
            "sources": SOURCES,
            "recipe": item["recipe"],
        }
        for number, item in enumerate(facts)
    ]


PAGE_LABELS = (
    (r"Places of type (\w+), joined", "{}"),
    (r"Spots of my pick", "spots"),
    (r"Length of the spots of my pick", "spotkm"),
    (r"Safety score of my pick without its spots", "nospots"),
    (r"Safety score of my pick with every work built", "fullplan"),
    (r"Km of (\w+) works of my pick", "fix:{}"),
    (r"Corridor segments (covered|partly|missed) by my pick", "tf:{}"),
    (r"Km of bike paths today", "pathkm"),
    (r"Km of bike paths today on my pick", "pickkm"),
)


def place_figures(figures) -> dict:
    found = {}
    for item in figures:
        for pattern, key in PAGE_LABELS:
            match = re.fullmatch(pattern, item["label"])
            if match:
                found[key.format(*match.groups())] = item["id"]
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
