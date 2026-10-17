import hashlib
import html
import json
import re
from pathlib import Path

import networkx as nx
import shapely
from pyproj import Transformer
from shapely.geometry import LineString

from bikeplan.access import in_scope_places, places
from bikeplan.corridors import OutsideBox, corridor_report, load_corridors
from bikeplan.fit import segment_fit
from bikeplan.ladder import (
    build_ladder,
    link_fixes,
    link_reasons,
    link_roads,
    link_streets,
)
from bikeplan.network import bike_segments
from bikeplan.network_report import choose, network_report
from bikeplan.options import NEW_PATH_KEY, build_options, join_places, link_table
from bikeplan.propose import corridor_candidates, read_corridors
from bikeplan.rating import longest_trip_m, model_ratings
from bikeplan.report import GLOSSARY, SOURCES, STYLE, entry, glossary_section, snapshot_date
from bikeplan.snapshot import buffered_box

SPEC = "spec 17"
CORRIDORS = Path(__file__).resolve().parents[2] / "references" / "tfnsw-strategic-corridors.yaml"
SPEC_LATE = "spec 17 blockers"
SPEC_CORRIDOR = "spec 19"
CORRIDOR_LABELS = {
    "inside_km": "km of the indicative route inside the council area",
    "near_km": "km within reach of my pick",
    "all_ages_km": "all-ages km today",
    "step_all_ages_km": "all-ages km at the recommended step",
}
LATE = ("blocker", "blockerkm", "ceiling", "askmore")
PICK = (
    "import json;d=json.load(open('options.json'));o=d['options'];"
    "b=max(x['steps'][-1]['score'] for x in o);"
    "p=o[min((x['steps'][-1]['disruption']['score'],i) for i,x in enumerate(o) "
    "if x['steps'][-1]['score']>=b-1)[1]];"
    "s=[t['score'] for t in p['steps']];"
    "r=next(i for i,v in enumerate(s) if v>=s[0]+d['share']*(s[-1]-s[0])-1e-9);"
)
ASK_STREETS = (
    "w=[p['works'][i] for t in p['steps'][1:r+1] for i in t['works']];"
    "s={x['street'] for x in w};"
    "n=[x for x in s if not x.startswith('unnamed ')];"
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


def street_overlay(pieces: list[dict], rows: list[list], model: dict | None = None) -> dict:
    metres = {str(level): 0.0 for level in (1, 2, 3, 4)} | {"aaa": 0.0}
    for row in rows:
        metres[str(row[2])] += float(row[1])
        if row[3]:
            metres["aaa"] += float(row[1])
    found = {
        "pieces": [{key: value for key, value in item.items() if key != "fix"} for item in pieces],
        "km": {key: round(value / 1000, 3) for key, value in metres.items()},
    }
    if model is not None:
        found |= {"model_pieces": model["pieces"], "model_km": model["km"]}
    return found


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
            {
                key: work[key]
                for key in ("street", "fix", "km", *SPENT, "least", "outside")
                if key in work
            }
            for work in item["works"]
        ],
        "no_fix": [
            {"street": gap["street"], "km": gap["km"], "links": len(gap["links"])}
            for gap in item["no_fix"]
        ],
        "blockers": [
            {key: found[key] for key in ("street", "km", "road_type", "trips", "reasons", "owner")}
            | {"links": len(found["links"])}
            for found in item.get("blockers", [])
        ],
        **({"ceiling": item["ceiling"]} if "ceiling" in item else {}),
        **({"links": item["links"]} if "links" in item else {}),
        **({"outside": item["outside"]} if item.get("outside") else {}),
    }


def options_text(options: list[dict], share: float, joined, corridor: dict | None = None) -> str:
    data = {
        "share": share,
        "options": [option_data(item) for item in options],
        "joined": joined.counts,
        "unjoined": joined.unjoined,
        **({"audit": joined.audit} if getattr(joined, "audit", None) else {}),
        **(
            {"corridors": {key: corridor[key] for key in ("source", "counts", "works", "segments")}}
            if corridor
            else {}
        ),
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"


def option_fits(graph, profile, weights) -> dict:
    return {
        segment_id: segment_fit(segment, profile, weights, free_separation=True)
        for segment_id, segment in bike_segments(graph).items()
    }


def unreached(graph, joined) -> list[dict]:
    legal = nx.Graph()
    legal.add_edges_from((u, v) for u, v, data in graph.edges(data=True) if data["bike_ok"])
    main = {item["node"] for item in joined.joined if item["node"] in legal}
    reach = (
        set().union(*(nx.node_connected_component(legal, node) for node in main)) if main else set()
    )
    return [
        {"id": item["id"], "name": item["name"]}
        for item in joined.unjoined
        if item.get("node") in reach
    ]


def build_options_report(graph, region, profile, snapshot, scores) -> tuple[list, list, object]:
    weights = region.proposals.disruption_weights
    fits = option_fits(graph, profile, weights)
    ratings = model_ratings(graph, scores, fits)
    graph.graph["ratings"] = ratings
    to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
    to_lonlat = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    found = places(snapshot)
    for place in found:
        place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
    found = in_scope_places(found, graph.graph["boundary"], region.analysis_buffer_m)
    joined = join_places(graph, found, [], profile.network)
    corridors = read_corridors(snapshot, graph.graph["crs"])
    candidates = None if corridors is None else corridor_candidates(graph, corridors)
    options = build_options(graph, joined, ratings, profile.network, candidates)
    table = link_table(graph, ratings, profile.network, joined.outside or (), candidates or ())
    area = region.name.split(",")[0].removesuffix(" Council")
    label = f"outside {area}"
    fixes = link_fixes(graph, table, fits, profile, weights)
    streets = link_streets(graph)
    roads = link_roads(
        graph, profile.network.state_functions, profile.fit.speed_approval_body.value
    )
    reasons = link_reasons(graph, table, fits, scores, profile)

    def point(node):
        data = graph.nodes[node]
        lon, lat = to_lonlat.transform(data["x"], data["y"])
        return [round(lon, 5), round(lat, 5)]

    def line(link):
        if link[2] >= NEW_PATH_KEY:
            shape = candidates[link[2] - NEW_PATH_KEY]["geometry"]
            return [round(value, 1) for xy in shape.coords for value in xy[:2]]
        key = next(k for k in (link, (link[1], link[0], link[2])) if graph.has_edge(*k))
        data = graph.edges[key]
        shape = data.get("geometry") or LineString(
            [(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in key[:2]]
        )
        return [round(value, 1) for xy in shape.coords for value in xy[:2]]

    report = []
    for item in options:
        ladder = build_ladder(
            table,
            item["links"],
            joined.joined,
            fixes,
            weights,
            streets,
            profile.network.max_trip_km * 1000,
            roads,
            reasons,
        )
        for work in ladder["works"]:
            if work.get("outside"):
                work["outside"] = label
        owner = {link: n for n, work in enumerate(ladder["works"]) for link in work["links"]}
        far = set(item["outside"])
        report.append(
            {
                "id": item["id"],
                "name": item["name"],
                "same_as": item["same_as"],
                "km": item["km"],
                "steps": ladder["steps"],
                "works": ladder["works"],
                "no_fix": ladder["no_fix"],
                "blockers": ladder["blockers"],
                "ceiling": ladder["ceiling"],
                "outside": [index for index, link in enumerate(item["links"]) if link in far],
                "links": [line(link) for link in item["links"]],
                "lines": [
                    {
                        "work": owner.get(link),
                        "ok": table[link]["all_ages"],
                        "line": [point(link[0]), point(link[1])],
                        **({"outside": label} if link in far else {}),
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
    spots = {place["osm_id"]: place for place in found}
    audit = {
        "crs": str(graph.graph["crs"]),
        "boundary": shapely.to_wkt(graph.graph["boundary"], rounding_precision=1),
        "buffer_m": profile.network.boundary_buffer_m,
        "max_trip_km": profile.network.max_trip_km,
        "longest_trip_m": round(
            longest_trip_m(table, joined.joined, profile.network.max_trip_km * 1000), 1
        ),
        "unreached": unreached(graph, joined),
        "places": [
            {key: item[key] for key in ("id", "name", "type")}
            | {"x": round(spots[item["id"]]["x"], 1), "y": round(spots[item["id"]]["y"], 1)}
            for item in sorted([*joined.joined, *joined.unjoined], key=lambda item: item["id"])
        ],
    }
    return report, marks, joined._replace(audit=audit)


def fact(label, value, unit, shown, recipe, method) -> dict:
    return {
        "label": label,
        "value": number(value, shown),
        "unit": unit,
        "recipe": recipe,
        "method": method,
    }


class Figures:
    def __init__(
        self,
        options: list[dict],
        share: float,
        joined,
        text: str,
        first: int,
        corridor: dict | None = None,
    ):
        self.options = options
        self.corridor = corridor
        self.joined = joined
        self.choice = choose(options, share)
        self.pick = next(item for item in options if item["id"] == self.choice["pick"])
        self.digest = hashlib.sha256(text.encode()).hexdigest()
        self.next = first
        self.made: dict = {}
        self.late: list = []

    def ref(self, key: tuple, text: str) -> str:
        if key not in self.made:
            item = self.describe(key)
            kind = key[0]
            late = kind in LATE
            figure_id = f"L{len(self.late)}" if late else f"F{self.next}"
            if late:
                self.late.append(key)
            else:
                self.next += 1
            self.made[key] = {
                "id": figure_id,
                "label": item["label"],
                "value": item["value"],
                "unit": item["unit"],
                "spec": SPEC_CORRIDOR if kind == "corridor" else SPEC_LATE if late else SPEC,
                "method": f"I read {item['method']} from options.json.",
                "inputs": [{"name": "options.json", "sha256": self.digest}],
                "sources": SOURCES,
                "recipe": item["recipe"],
            }
        return f'<a href="#{self.made[key]["id"]}">{text}</a>'

    def listed(self) -> list[dict]:
        for number, key in enumerate(self.late):
            self.made[key]["id"] = f"F{self.next + number}"
        late = [self.made[key] for key in self.late]
        return [item for key, item in self.made.items() if key not in self.late] + late

    def settle(self, body: str) -> str:
        return re.sub(
            r'href="#L(\d+)"',
            lambda found: f'href="#{self.made[self.late[int(found[1])]]["id"]}"',
            body,
        )

    def describe(self, key: tuple) -> dict:
        kind = key[0]
        if kind in LATE:
            return self.of_blockers(key)
        if kind == "corridor":
            return self.of_corridor(key)
        if kind in ("km", "today", "full", "places", "spent", "quality"):
            return self.of_option(key)
        return self.of_pick(key)

    def of_corridor(self, key: tuple) -> dict:
        load = "import json;c=json.load(open('options.json'))['corridors'];"
        if key[1] == "count":
            return fact(
                f"Corridor segments {key[2]} by my pick",
                self.corridor["counts"][key[2]],
                "segments",
                0,
                f"{load}print(c['counts']['{key[2]}'])",
                "corridor verdicts",
            )
        if key[1] == "works":
            return fact(
                "Corridor works: km of my pick's works within reach of the indicative routes",
                self.corridor["works"]["km"],
                "km",
                2,
                f"{load}print(round(c['works']['km'],2))",
                "corridor works",
            )
        _, _, number, name = key
        segment = self.corridor["segments"][number]
        return fact(
            f"Corridor {segment['id']}: {CORRIDOR_LABELS[name]}",
            segment[name],
            "km",
            2,
            f"{load}print(round(c['segments'][{number}]['{name}'],2))",
            "corridor segments",
        )

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

    def of_blockers(self, key: tuple) -> dict:
        kind = key[0]
        pick = self.pick
        if kind == "ceiling":
            return fact(
                f"{pick['name']}: safety score if every blocker were fixed too (a ceiling)",
                pick["ceiling"],
                "points",
                1,
                f"{PICK}print(round(p['ceiling'],1))",
                "ceiling score",
            )
        if kind == "askmore":
            return fact(
                "Streets of the works that my ask does not name",
                self.choice["more"],
                "streets",
                0,
                f"{PICK}{ASK_STREETS}print(len(s)-min(10,len(n)))",
                "ask",
            )
        found = pick["blockers"][key[1]]
        place = f"{pick['name']}: blocker {key[1] + 1}, {found['street']}"
        if kind == "blocker":
            return fact(
                f"{place}, trips it stops",
                found["trips"],
                "trips",
                0,
                f"{PICK}print(p['blockers'][{key[1]}]['trips'])",
                "blocker trips",
            )
        return fact(
            f"{place}, length",
            found["km"],
            "km",
            2,
            f"{PICK}print(round(p['blockers'][{key[1]}]['km'],2))",
            "blocker length",
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
                len(self.choice["named"]),
                "streets",
                0,
                f"{PICK}{ASK_STREETS}print(min(10,len(n)))",
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


def corridor_data(graph, region, profile, snapshot, options) -> dict | None:
    boundary = json.loads((Path(snapshot) / "boundary.geojson").read_text())
    box = buffered_box(boundary, region.analysis_buffer_m)
    try:
        corridors = load_corridors(CORRIDORS, box)
    except OutsideBox:
        return None
    choice = choose(options, profile.network.recommend_share)
    pick = next(item for item in options if item["id"] == choice["pick"])
    return corridor_report(graph, corridors, graph.graph["ratings"], pick, choice, profile.network)


def edition(
    region, options, marks, joined, share, old, streets=None, corridor=None
) -> tuple[str, str, list, str]:
    text = options_text(options, share, joined, corridor)
    first = max(int(item["id"][1:]) for item in old) + 1
    figures = Figures(options, share, joined, text, first, corridor)
    head, body = network_report(options, share, marks, figures.ref, streets, corridor)
    body += left_out(joined, figures.ref) + archive_figures(old)
    made = figures.listed()
    body = figures.settle(body)
    cut = body.index("</section>") + len("</section>")
    body = f'<section id="opening">{checked(old)}{body[:cut]}</section>{body[cut:]}'
    return head, body, made, text


def edition_parts(region, body, figures, details) -> str:
    area = region.name.split(",")[0]
    terms = {area: "the council area this report covers.", **GLOSSARY, **TERMS}
    appendix = "".join(entry(item) for item in figures)
    return (
        f"{body}{glossary_section(terms)}"
        '<section id="appendix"><h2>How to check every number</h2>'
        f"<p>This report uses the data snapshot of {snapshot_date(region)}.</p>"
        f"{appendix}{details}</section>"
    )


def edition_page(region, head, body, figures, details) -> str:
    author = f"<p>By {html.escape(region.report.author)}</p>" if region.report.author else ""
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Bike paths in {html.escape(region.name)}</title>"
        f"<style>{STYLE}</style>{head}</head><body>"
        f"<h1>Bike paths in {html.escape(region.name)}</h1>{author}"
        f"{edition_parts(region, body, figures, details)}</body></html>\n"
    )
