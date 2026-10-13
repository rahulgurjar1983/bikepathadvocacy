import hashlib
import html
import json

from pyproj import Transformer

from bikeplan.access import in_scope_places, places
from bikeplan.fit import segment_fit
from bikeplan.ladder import build_ladder, link_fixes, link_streets
from bikeplan.network import bike_segments
from bikeplan.network_report import choose, network_report
from bikeplan.options import build_options, join_places, link_table
from bikeplan.rating import model_ratings
from bikeplan.report import GLOSSARY, SOURCES, STYLE, entry, glossary_section, snapshot_date

SPEC = "spec 17"
PICK = (
    "import json;d=json.load(open('options.json'));o=d['options'];"
    "b=max(x['steps'][-1]['score'] for x in o);"
    "p=o[min((x['steps'][-1]['disruption']['score'],i) for i,x in enumerate(o) "
    "if x['steps'][-1]['score']>=b-1)[1]];"
    "s=[t['score'] for t in p['steps']];"
    "r=next(i for i,v in enumerate(s) if v>=s[0]+d['share']*(s[-1]-s[0])-1e-9);"
)
LOAD = "import json;d=json.load(open('options.json'));o=d['options'];"
SPENT = {
    "parking_spaces": ("parking spaces", "spaces", 0),
    "lane_km": ("traffic-lane km", "km", 2),
    "speed_km": ("lower-speed km", "km", 2),
    "path_km": ("path km", "km", 2),
    "score": ("disruption score", "points", 1),
}
TERMS = {
    "safety score": "a number from zero to one hundred for how many trips are safe for all ages.",
    "step": "one stage of works for an option; each step makes at least one more trip safe.",
}


def number(value, places_shown):
    return round(value) if places_shown == 0 else round(value, places_shown)


def street_overlay(pieces: list[dict], rows: list[list]) -> dict:
    metres = {str(level): 0.0 for level in (1, 2, 3, 4)} | {"aaa": 0.0}
    for row in rows:
        metres[str(row[2])] += float(row[1])
        if row[3]:
            metres["aaa"] += float(row[1])
    return {
        "pieces": [{key: value for key, value in item.items() if key != "fix"} for item in pieces],
        "km": {key: round(value / 1000, 3) for key, value in metres.items()},
    }


def option_data(item: dict) -> dict:
    return {
        "id": item["id"],
        "name": item["name"],
        "same_as": item["same_as"],
        "km": item["km"],
        "steps": [
            {
                "score": step["totals"]["score"],
                "trips": step["totals"]["trips"],
                "safe_trips": step["totals"]["safe_trips"],
                "km_all_ages": step["totals"]["km_all_ages"],
                "assumed_share": step["totals"]["assumed_share"],
                "places_safe": step["totals"]["places_safe"],
                "disruption": step["disruption"],
                "works": step["works"],
            }
            for step in item["steps"]
        ],
        "works": [
            {key: work[key] for key in ("street", "fix", "km", *SPENT)} for work in item["works"]
        ],
        "no_fix": [
            {"street": gap["street"], "km": gap["km"], "links": len(gap["links"])}
            for gap in item["no_fix"]
        ],
    }


def options_text(options: list[dict], share: float, joined) -> str:
    data = {
        "share": share,
        "options": [option_data(item) for item in options],
        "joined": joined.counts,
        "unjoined": joined.unjoined,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"


def build_options_report(graph, region, profile, snapshot, scores) -> tuple[list, list, object]:
    weights = region.proposals.disruption_weights
    fits = {
        segment_id: segment_fit(segment, profile, weights)
        for segment_id, segment in bike_segments(graph).items()
    }
    ratings = model_ratings(graph, scores, fits)
    to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
    to_lonlat = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    found = places(snapshot)
    for place in found:
        place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
    found = in_scope_places(found, graph.graph["boundary"], region.analysis_buffer_m)
    joined = join_places(graph, found, [], profile.network)
    options = build_options(graph, joined, ratings, profile.network)
    table = link_table(graph, ratings)
    fixes = link_fixes(graph, table, fits, profile, weights)
    streets = link_streets(graph)

    def point(node):
        data = graph.nodes[node]
        lon, lat = to_lonlat.transform(data["x"], data["y"])
        return [round(lon, 5), round(lat, 5)]

    report = []
    for item in options:
        ladder = build_ladder(table, item["links"], joined.joined, fixes, weights, streets)
        owner = {link: n for n, work in enumerate(ladder["works"]) for link in work["links"]}
        report.append(
            {
                "id": item["id"],
                "name": item["name"],
                "same_as": item["same_as"],
                "km": item["km"],
                "steps": ladder["steps"],
                "works": ladder["works"],
                "no_fix": ladder["no_fix"],
                "lines": [
                    {
                        "work": owner.get(link),
                        "ok": table[link]["all_ages"],
                        "line": [point(link[0]), point(link[1])],
                    }
                    for link in item["links"]
                ],
            }
        )
    marks = [
        {
            "lon": point(place["node"])[0],
            "lat": point(place["node"])[1],
            "type": place["type"],
            "name": place["name"],
        }
        for place in joined.joined
    ]
    return report, marks, joined


def fact(label, value, unit, shown, recipe, method) -> dict:
    return {
        "label": label,
        "value": number(value, shown),
        "unit": unit,
        "recipe": recipe,
        "method": method,
    }


class Figures:
    def __init__(self, options: list[dict], share: float, joined, text: str, first: int):
        self.options = options
        self.joined = joined
        self.choice = choose(options, share)
        self.pick = next(item for item in options if item["id"] == self.choice["pick"])
        self.digest = hashlib.sha256(text.encode()).hexdigest()
        self.next = first
        self.made: dict = {}

    def ref(self, key: tuple, text: str) -> str:
        if key not in self.made:
            item = self.describe(key)
            figure_id = f"F{self.next}"
            self.next += 1
            self.made[key] = {
                "id": figure_id,
                "label": item["label"],
                "value": item["value"],
                "unit": item["unit"],
                "spec": SPEC,
                "method": f"I read {item['method']} from options.json.",
                "inputs": [{"name": "options.json", "sha256": self.digest}],
                "sources": SOURCES,
                "recipe": item["recipe"],
            }
        return f'<a href="#{self.made[key]["id"]}">{text}</a>'

    def listed(self) -> list[dict]:
        return list(self.made.values())

    def describe(self, key: tuple) -> dict:
        kind = key[0]
        if kind in ("km", "today", "full", "places", "spent", "quality"):
            return self.of_option(key)
        return self.of_pick(key)

    def of_option(self, key: tuple) -> dict:
        kind = key[0]
        n = next(n for n, item in enumerate(self.options) if item["id"] == key[1])
        item = self.options[n]
        name = item["name"]
        load = f"{LOAD}x=o[{n}];"
        first, last = item["steps"][0], item["steps"][-1]
        if kind == "km":
            return fact(
                f"{name}: length", item["km"], "km", 1, f"{load}print(round(x['km'],1))", "km"
            )
        if kind == "today":
            return fact(
                f"{name}: safety score today",
                first["totals"]["score"],
                "points",
                1,
                f"{load}print(round(x['steps'][0]['score'],1))",
                "safety score",
            )
        if kind == "full":
            return fact(
                f"{name}: safety score with every work built",
                last["totals"]["score"],
                "points",
                1,
                f"{load}print(round(x['steps'][-1]['score'],1))",
                "safety score",
            )
        if kind == "places":
            return fact(
                f"{name}: {key[2]} places with a safe trip once every work is built",
                last["totals"]["places_safe"][key[2]],
                "places",
                0,
                f"{load}print(x['steps'][-1]['places_safe']['{key[2]}'])",
                "place count",
            )
        if kind == "spent":
            label, unit, shown = SPENT[key[2]]
            read = f"x['steps'][-1]['disruption']['{key[2]}']"
            printed = f"int(round({read}))" if shown == 0 else f"round({read},{shown})"
            return fact(
                f"{name}: {label} with every work built",
                last["disruption"][key[2]],
                unit,
                shown,
                f"{load}print({printed})",
                "disruption total",
            )
        return fact(
            f"{name}: share of km rated from assumed or unknown inputs",
            100 * first["totals"]["assumed_share"],
            "%",
            1,
            f"{load}print(round(100*x['steps'][0]['assumed_share'],1))",
            "assumed share",
        )

    def of_pick(self, key: tuple) -> dict:
        kind = key[0]
        step = self.choice["step"]
        pick = self.pick
        facts = {
            "pickstep": fact(
                "Recommended step of my pick",
                step,
                "step",
                0,
                f"{PICK}print(r)",
                "recommended step",
            ),
            "ask": fact(
                "Streets named in my ask",
                len(self.choice["streets"]),
                "streets",
                0,
                f"{PICK}print(len({{p['works'][w]['street'] for t in p['steps'][1:r+1] "
                "for w in t['works']}))",
                "ask",
            ),
            "step": fact(
                "Safety score of my pick at the recommended step",
                pick["steps"][step]["totals"]["score"],
                "points",
                1,
                f"{PICK}print(round(s[r],1))",
                "step totals",
            ),
            "tenths": fact(
                "Highest safety score in the table, at the full disruption of an option",
                max(item["steps"][-1]["totals"]["score"] for item in self.options),
                "points",
                1,
                f"{LOAD}print(round(max(x['steps'][-1]['score'] for x in o),1))",
                "table",
            ),
            "works": fact(
                "Works of my pick up to the recommended step",
                sum(len(item["works"]) for item in pick["steps"][1 : step + 1]),
                "works",
                0,
                f"{PICK}print(sum(len(t['works']) for t in p['steps'][1:r+1]))",
                "works",
            ),
            "nofix": fact(
                "Km of links with no fix, all options",
                sum(gap["km"] for item in self.options for gap in item["no_fix"]),
                "km",
                2,
                f"{LOAD}print(round(sum(w['km'] for x in o for w in x['no_fix']),2))",
                "links with no fix",
            ),
            "left": fact(
                "Places left out of the options",
                len(self.joined.unjoined),
                "places",
                0,
                "import json;print(len(json.load(open('options.json'))['unjoined']))",
                "places left out",
            ),
        }
        if kind in facts:
            return facts[kind]
        return fact(
            f"Places of type {key[1]}, {key[2]}",
            self.joined.counts[key[1]][key[2]],
            "places",
            0,
            f"import json;print(json.load(open('options.json'))['joined']['{key[1]}']['{key[2]}'])",
            "place counts",
        )


def left_out(joined, ref) -> str:
    counts = "".join(
        f"<li>{html.escape(kind)}: joined {ref(('count', kind, 'joined'), str(found['joined']))}, "
        f"left out {ref(('count', kind, 'unjoined'), str(found['unjoined']))}</li>"
        for kind, found in sorted(joined.counts.items())
    )
    items = "".join(
        f"<li>{ref(('left',), html.escape(item['name']))}: {html.escape(item['reason'])}</li>"
        for item in joined.unjoined
    )
    return (
        '<section id="places"><h2>Places in the options</h2>'
        f"<ul>{counts}</ul>"
        f"<p>Places left out of every option: {ref(('left',), str(len(joined.unjoined)))}.</p>"
        f"<ul>{items or '<li>none</li>'}</ul></section>"
    )


def archive_figures(old: list[dict]) -> str:
    items = "".join(
        f'<li><a href="#{item["id"]}">{item["value"]} {html.escape(item["unit"])}, '
        f"{html.escape(item['label'])}</a></li>"
        for item in old
    )
    return (
        '<section id="archive-figures"><h2>More figures from the data archive</h2>'
        f"<ul>{items}</ul></section>"
    )


def checked(old: list[dict]) -> str:
    street = next(item for item in old if item["id"] == "F1")
    return (
        f'<p>I checked <a href="#F1">{street["value"]} {html.escape(street["unit"])}</a> of '
        "street that a bike may use. I joined every school, station and town centre to it.</p>"
    )


def edition(region, options, marks, joined, share, old, streets=None) -> tuple[str, str, list, str]:
    text = options_text(options, share, joined)
    first = max(int(item["id"][1:]) for item in old) + 1
    figures = Figures(options, share, joined, text, first)
    head, body = network_report(options, share, marks, figures.ref, streets)
    body += left_out(joined, figures.ref) + archive_figures(old)
    cut = body.index("</section>") + len("</section>")
    body = f'<section id="opening">{checked(old)}{body[:cut]}</section>{body[cut:]}'
    return head, body, figures.listed(), text


def edition_page(region, head, body, figures, details) -> str:
    area = region.name.split(",")[0]
    terms = {area: "the council area this report covers.", **GLOSSARY, **TERMS}
    author = f"<p>By {html.escape(region.report.author)}</p>" if region.report.author else ""
    appendix = "".join(entry(item) for item in figures)
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Bike paths in {html.escape(region.name)}</title>"
        f"<style>{STYLE}</style>{head}</head><body>"
        f"<h1>Bike paths in {html.escape(region.name)}</h1>{author}"
        f"{body}{glossary_section(terms)}"
        '<section id="appendix"><h2>How to check every number</h2>'
        f"<p>This report uses the data snapshot of {snapshot_date(region)}.</p>"
        f"{appendix}{details}</section></body></html>\n"
    )
