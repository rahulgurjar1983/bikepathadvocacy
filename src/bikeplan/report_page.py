import hashlib
import html
import json
import re
from datetime import date

from shapely.geometry import LineString

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
    ".tile .n,.tile.cost .n{font-size:max(2.5rem,var(--num))}"
    "@media print{#find .wrap>:not(#result),#streets,#plans,#cost,#evidence{display:none!important}}"
)


def round_point(point) -> list[float]:
    return [round(point[0], 5), round(point[1], 5)]


BASE_TOLERANCE = 1e-4
STREET_TOLERANCE = 2e-5


def thinned(points: list, tolerance: float) -> list:
    if len(points) <= 4:
        return points
    return [list(point) for point in LineString(points).simplify(tolerance).coords]


def thinned_layer(layer: list, tolerance: float) -> list:
    if layer and isinstance(layer[0][0], int | float):
        return thinned(layer, tolerance)
    return [thinned_layer(part, tolerance) for part in layer]


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


def stage_km(step: dict, steps: list, streets: dict | None) -> float:
    modelled = ((streets or {}).get("model_km") or {}).get("aaa")
    km = step["totals"]["km_all_ages"]
    if modelled is None:
        return km
    return round(modelled + km - steps[0]["totals"]["km_all_ages"], 3)


def stage_values(step: dict, km: float) -> dict:
    totals = step["totals"]
    return {
        "score": totals["score"],
        "safe": totals["safe_trips"],
        "trips": totals["trips"],
        "km": km,
        "places": totals["places_safe"],
        "park": step["disruption"]["parking_spaces"],
        "lane": step["disruption"]["lane_km"],
        "slow": step["disruption"]["speed_km"],
    }


def street_lines(streets: dict | None) -> list:
    pieces = (streets or {}).get("model_pieces") or []
    return [
        thinned([[round(lon, 5), round(lat, 5)] for lat, lon in line], STREET_TOLERANCE)
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
                "park": item["parking_spaces"],
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


def ward_cards(areas: list, pick: dict, spot_numbers: dict, rates) -> list:
    cards = []
    for area in areas:
        cost = None
        if rates:
            cost = sum(
                (work_cost(pick["works"][index], rates) or 0) * share
                for index, share in area["parts"].items()
            )
            cost /= 1_000_000
        cards.append(
            {key: area[key] for key in ("name", "poly", "plan_km", "works_km", "park")}
            | {"cost": cost, **({"at": area["at"]} if "at" in area else {})}
            | {key: area[key] for key in ("schools", "stations", "centres", "top")}
            | ({"safe": area["safe"]} if "safe" in area else {})
            | {
                "spots": sorted(
                    spot_numbers[index] for index in area["spots"] if index in spot_numbers
                )
            }
        )
    return cards


def place_rows(marks: list, steps: list, rec: int) -> list:
    rows = [
        {"name": mark["name"], "type": mark["type"], "at": round_point([mark["lon"], mark["lat"]])}
        for mark in marks
    ]
    if not all("partners" in step["totals"] for step in steps):
        return rows
    chosen = [steps[0]["totals"], steps[rec]["totals"], steps[-1]["totals"]]
    position = {mark.get("id"): number for number, mark in enumerate(marks)}
    for row, mark in zip(rows, marks, strict=True):
        row["t"] = [len(found["partners"].get(mark.get("id"), [])) for found in chosen]
        row["j"] = [
            position[other]
            for other in chosen[-1]["partners"].get(mark.get("id"), [])
            if other in position
        ]
    return rows


def report_data(
    options,
    choice,
    marks,
    joined,
    streets,
    corridor,
    boundary,
    paths=(),
    rates=None,
    council=None,
    areas=None,
    backdrop=None,
    parking_total=None,
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
    for found in works:
        section = pick["works"][found["i"]].get("section")
        if section:
            found["sec"] = {
                "w": section["width"],
                "b": section["before"],
                "a": section.get("after"),
            }
    if rates:
        for found in works:
            cost = work_cost(pick["works"][found["i"]], rates)
            found["cost"] = None if cost is None else cost / 1_000_000
    data = {
        "base": {
            **{
                layer: thinned_layer((backdrop or {}).get(layer, []), BASE_TOLERANCE)
                for layer in ("water", "park", "air", "outside", "rail")
            },
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
        "places": place_rows(marks, steps, rec),
        "stages": {
            "today": stage_values(steps[0], stage_km(steps[0], steps, streets)),
            "first": stage_values(steps[rec], stage_km(steps[rec], steps, streets)),
            "works": stage_values(steps[-1], stage_km(steps[-1], steps, streets)),
        },
        "steps": [
            {
                "w": step["works"],
                "score": step["totals"]["score"],
                "km": stage_km(step, steps, streets),
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
        if parking_total:
            data["parking_total"] = parking_total
        data["spot_cost"] = sum(
            (work_cost(item, rates) or 0) / 1_000_000 for item in pick["works"] if item.get("spot")
        )
    if council:
        data["council"] = [
            {key: row[key] for key in ("id", "name", "km", "share", "lines")}
            | {"v": row["verdict"]}
            for row in council["routes"]
        ]
        data["council_share"] = council["share"]
        data["council_km"] = council["km"]
        data["council_source"] = {
            "title": council["source"]["title"],
            "url": council["source"]["url"],
            "date": council["source"].get("published", ""),
        }
    if areas:
        numbers = {item["w"]: item["n"] for item in data["spots"]}
        data["wards"] = ward_cards(areas, pick, numbers, rates)
        data["subs"] = {area["name"]: area["subs"] for area in areas}
    if corridor:
        data["corridors"] = [
            {"id": route["id"], "lines": route["lines"]} for route in corridor["routes"]
        ]
        data["corridor_counts"] = corridor["counts"]
        data["corridor_source"] = {
            name: corridor["source"][name] for name in ("title", "date", "url")
        }
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


def drop_last_card(text: str, name: str) -> str:
    return re.sub(
        rf'\s*<div class="card" id="card-{name}">.*?</p>\s*</div>', "", text, count=1, flags=re.S
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


def council_facts(council: dict) -> list[dict]:
    load = "import json;c=json.load(open('options.json'))['council'];"
    facts = [
        fact(
            "Share of the council plan that my pick covers",
            council["share"] * 100,
            "%",
            0,
            f"{load}print(round(c['share']*100))",
            "the share of the council plan that my pick covers",
        ),
        fact(
            "Km of the council plan inside the boundary",
            council["km"],
            "km",
            1,
            f"{load}print(round(c['km'],1))",
            "the km of the council plan",
        ),
        fact(
            "Km of my pick off the council plan",
            council["off_km"],
            "km",
            2,
            f"{load}print(round(c['off_km'],2))",
            "the km of my pick off the council plan",
        ),
    ]
    for name, words in COUNCIL_COUNTS:
        facts.append(
            fact(
                f"Council plan routes {words} by my pick",
                council["counts"][name],
                "routes",
                0,
                f"{load}print(c['counts']['{name}'])",
                "the council plan verdicts",
            )
        )
    for number, row in enumerate(council["routes"]):
        facts.append(
            fact(
                f"Council route {row['id']}: share on my pick",
                row["share"] * 100,
                "%",
                0,
                f"{load}print(round(c['routes'][{number}]['share']*100))",
                f"the share of route {row['id']} on my pick",
            )
        )
    return facts


def ward_facts(wards: dict) -> list[dict]:
    load = "import json;w=json.load(open('options.json'))['wards']['areas']"
    facts = []
    for number, area in enumerate(wards["areas"]):
        for key, words, unit, shown in WARD_VALUES:
            facts.append(
                fact(
                    f"{area['name']}: {words}",
                    area[key],
                    unit,
                    shown,
                    f"{load}[{number}];print(round(w['{key}'],{shown}))",
                    f"{words} in {area['name']}",
                )
            )
        for key, words, unit in SAFE_VALUES:
            for stage, when in enumerate(SAFE_STAGES):
                if "safe" in area:
                    facts.append(
                        fact(
                            f"{area['name']}: {words} with a safe trip {when}",
                            area["safe"][key][stage],
                            unit,
                            0,
                            f"{load}[{number}];print(w['safe']['{key}'][{stage}])",
                            f"{words} with a safe trip {when} in {area['name']}",
                        )
                    )
    return facts


def page_figures(options, choice, text, first, council=None, wards=None) -> list[dict]:
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
    if council:
        facts += council_facts(council)
    if wards:
        facts += ward_facts(wards)
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


COUNCIL_COUNTS = (
    ("covered", "covered"),
    ("partly", "partly covered"),
    ("missed", "missed"),
)
WARD_VALUES = (
    ("plan_km", "km of my pick", "km", 2),
    ("works_km", "km of works", "km", 2),
    ("park", "parking spaces removed", "spaces", 1),
    ("schools", "schools joined", "schools", 0),
    ("stations", "stations joined", "stations", 0),
    ("centres", "town centres joined", "town centres", 0),
    ("spots", "spots", "spots", 0),
)
SAFE_VALUES = (
    ("schools", "schools", "schools"),
    ("stations", "stations", "stations"),
    ("centres", "town centres", "town centres"),
)
SAFE_STAGES = ("today", "at the first stage", "in the full plan")
PAGE_LABELS = (
    (r"Share of the council plan that my pick covers", "council_share"),
    (r"Km of the council plan inside the boundary", "council_km"),
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
        name, _, words = item["label"].partition(": ")
        for key, ward_words, _, _ in WARD_VALUES:
            if words == ward_words:
                found[f"ward:{name}:{key}"] = item["id"]
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
        "plans": bool(data["corridors"] or data.get("council")),
    }
    for name, kept in have.items():
        if not kept:
            text = drop_section(text, name)
    if not data.get("wards"):
        text = drop_section(text, "wards")
        text = drop_button(text, "wards")
    full = data["stages"]["works"]
    if not full.get("n_works", 0) + full.get("n_spots", 0):
        text = drop_section(text, "cost")
    if "cost" not in full:
        text = re.sub(r'<div class="tile cost">.*?</div>', "", text, flags=re.S)
    if not data.get("council"):
        text = drop_button(text, "council")
        text = drop_card(text, "council")
    if not data["corridors"]:
        text = drop_button(text, "tfnsw")
        text = drop_last_card(text, "tfnsw")
    if 'id="ly-' not in text:
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
