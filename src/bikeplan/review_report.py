import hashlib
import html
import json
from datetime import date
from pathlib import Path

import yaml

from bikeplan.config import ConfigError, Region, load_profile
from bikeplan.network import build
from bikeplan.report import (
    ASSETS,
    GLOSSARY,
    MONTHS,
    SOURCES,
    STYLE,
    check_leaks,
    glossary_section,
    link,
    snapshot_date,
)
from bikeplan.review import SHARES, claim_verdicts, read_claims, route_figures
from bikeplan.route import read_route

HEAD = "import json;t=json.load(open('route_figures.json'));v=json.load(open('verdicts.json'));"
FILES = ["route_figures.json", "verdicts.json"]
SPEC = "spec 14"
SHARE_UNIT = "share of route"
MEASURE_EXPRESSIONS = {
    **{
        name: f"t['total']['{group}']['{key}']/t['total']['route_km']"
        for name, (group, key) in SHARES.items()
    },
    "aaa_share": "t['total']['km_aaa']/t['total']['route_km']",
    "matched_share": "t['total']['matched_share']",
    "route_km": "t['total']['route_km']",
    "crossings_unsignalised": "t['total']['crossings_unsignalised']",
    "parking_spaces_lost": "t['total']['disruption']['parking_spaces']",
    "lane_km_lost": "t['total']['disruption']['lane_km']",
    "homes_gaining_safe_reach": "t['total']['access']['homes_gaining_safe_reach']",
}
MEASURE_UNITS = {
    **dict.fromkeys(MEASURE_EXPRESSIONS, SHARE_UNIT),
    "route_km": "km",
    "crossings_unsignalised": "crossings",
    "parking_spaces_lost": "spaces",
    "lane_km_lost": "km",
    "homes_gaining_safe_reach": "people",
}
MEASURE_LABELS = {
    "separated_share": "Share of the route on a separated path or lane",
    "painted_share": "Share of the route on a painted lane",
    "shared_share": "Share of the route shared with traffic",
    "off_network_share": "Share of the route that is off network",
    "aaa_share": "Share of the route that is safe for all ages",
    "matched_share": "Share of the route that follows a street a bike may use",
    "route_km": "Length of the route",
    "crossings_unsignalised": "Crossings with no signal",
    "parking_spaces_lost": "Parking spaces lost",
    "lane_km_lost": "Traffic lane length lost",
    "homes_gaining_safe_reach": "People who gain a safe way to a needed place",
}
OPERATOR_WORDS = {
    ">=": "at least",
    "<=": "at most",
    ">": "more than",
    "<": "less than",
    "==": "exactly",
}
LEVEL_KEYS = (
    "Level one: quietest (pale blue line)",
    "Level two: quiet (dark blue line)",
    "Level three: busy (pale red line)",
    "Level four: most busy (dark red line)",
    "Off network: the route needs new building (dashed black line)",
    "A break in the safe run (yellow dot)",
    "A crossing with no signal (white dot)",
)
REVIEW_GLOSSARY = {
    "break": "a stretch of the route that is not safe for all ages.",
    "claim": "a statement about a plan that can be checked with route data.",
    "crossing": "a point where a bike route meets or crosses another road.",
    "km": "a kilometre, which is one thousand metres.",
    "method": "the steps and measures used to get a result.",
    "refuge": "an island in a crossing where a person can wait.",
    "reply": "an answer sent by the author of a plan.",
    "route": "the path a person rides along.",
    "section": "one named part of a route file.",
    "signal": "a traffic light.",
    "stress": "how hard traffic makes a street feel to ride on.",
    "verdict": "my finding on one claim: it holds, it holds partly, or it does not hold.",
}
STYLE_EXTRA = (
    "#review-map-canvas{height:24rem;background:#fff;border:1px solid #444}"
    "blockquote{margin:.5rem 0;padding-left:.75rem;border-left:4px solid #444}"
    "blockquote.reply-date{display:inline;margin:0;padding:0;border:0;font-style:normal}"
)


class Figures:
    def __init__(self, figures: dict, verdicts: list, digests: list):
        self.figures = figures
        self.verdicts = verdicts
        self.digests = digests
        self.items: list[dict] = []

    def add(self, label: str, expression: str, unit: str, method: str) -> dict:
        scope = {"t": self.figures, "v": self.verdicts}
        value = round(eval(expression, {"len": len, "sum": sum}, scope), 3)
        item = {
            "id": f"F{len(self.items) + 1}",
            "label": label,
            "value": value,
            "unit": unit,
            "spec": SPEC,
            "method": method,
            "inputs": self.digests,
            "sources": SOURCES,
            "recipe": f"{HEAD}print(round({expression},3))",
        }
        self.items.append(item)
        return item


def dump(data) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def review_entry(item: dict) -> str:
    inputs = "".join(
        f"<li><code>{html.escape(part['name'])}</code>, sha256 <code>{part['sha256']}</code></li>"
        for part in item["inputs"]
    )
    sources = "".join(
        f"<li><code>{html.escape(part['name'])}, licence {html.escape(part['licence'])}, "
        f"request: {html.escape(part['request'])}</code></li>"
        for part in item["sources"]
    )
    return (
        f'<article id="{item["id"]}"><h3>{item["id"]}: {html.escape(item["label"])}</h3>'
        f"<dl><dt>Value</dt><dd>{item['value']} {html.escape(item['unit'])}</dd>"
        f"<dt>How I worked</dt><dd>{html.escape(item['spec'])}. "
        f"{html.escape(item['method'])}</dd>"
        f"<dt>Inputs</dt><dd><ul>{inputs}</ul></dd>"
        f"<dt>Data</dt><dd><ul>{sources}</ul></dd>"
        "<dt>How to check</dt>"
        f"<dd><pre>{html.escape(item['recipe'])}</pre></dd></dl></article>"
    )


def day(value) -> str:
    when = date.fromisoformat(str(value))
    return f"<time>{when.day} {MONTHS[when.month - 1]} {when.year}</time>"


def quoted_day(value) -> str:
    return f'<blockquote class="reply-date">{day(value)}</blockquote>'


def read_reply(path) -> dict:
    found = yaml.safe_load(Path(path).read_text()) or {}
    for name, keys in (("sent", ("to", "date", "what")), ("replies", ("from", "date", "text"))):
        for item in found.get(name, []):
            missing = [key for key in keys if key not in item]
            if missing:
                raise ConfigError(f"reply file: {name} entry needs {', '.join(missing)}")
    return {"sent": found.get("sent", []), "replies": found.get("replies", [])}


def reply_section(reply: dict) -> str:
    if reply["sent"]:
        sent = "".join(
            f"<li>I sent this to {html.escape(item['to'], quote=False)} on "
            f"{quoted_day(item['date'])}: "
            f"{html.escape(item['what'], quote=False)}.</li>"
            for item in reply["sent"]
        )
        sent = f"<ul>{sent}</ul>"
    else:
        sent = "<p>I have not sent this review to the author yet.</p>"
    if reply["replies"]:
        replies = "".join(
            f"<p>{html.escape(item['from'], quote=False)} replied on {quoted_day(item['date'])}, "
            f"in their own words:</p><blockquote>{html.escape(item['text'], quote=False)}"
            "</blockquote>"
            for item in reply["replies"]
        )
    else:
        replies = "<p>No reply has come in yet. I will print any reply here, in full.</p>"
    return (
        '<section id="reply"><h2>Right of reply</h2>'
        "<p>I judge claims, never people. The author of the plan may answer any finding here.</p>"
        f"<h3>What I sent</h3>{sent}<h3>What came back</h3>{replies}</section>"
    )


def claim_figures(figures: Figures, verdicts: list) -> list[str]:
    rows = []
    for index, found in enumerate(verdicts):
        quote = html.escape(found["quote"], quote=False)
        source = html.escape(found["source"])
        if "measure" in found:
            measure = found["measure"]
            unit = MEASURE_UNITS[measure]
            measured = figures.add(
                MEASURE_LABELS[measure],
                MEASURE_EXPRESSIONS[measure],
                unit,
                "I measure the route with the method of the figure and read the result.",
            )
            claimed = figures.add(
                "Value that the claim names for: " + MEASURE_LABELS[measure].lower(),
                f"v[{index}]['claimed']",
                unit,
                "I read the value from the claims file.",
            )
            what = (
                f"{html.escape(MEASURE_LABELS[measure])}: I measured {link(measured)}. "
                f"The claim says {OPERATOR_WORDS[found['op']]} {link(claimed)}."
            )
        else:
            what = f"I do not measure this: {html.escape(found['reason'], quote=False)}"
        rows.append(
            f"<tr><td><blockquote>{quote}</blockquote></td>"
            f'<td><a href="{source}">{source}</a></td>'
            f"<td><strong>{html.escape(found['verdict'])}</strong></td><td>{what}</td></tr>"
        )
    return rows


def verdicts_section(figures: Figures, verdicts: list) -> str:
    rows = "".join(claim_figures(figures, verdicts))
    return (
        '<section id="verdicts"><h2>What I found for each claim</h2>'
        "<p>A claim holds when the measure meets it. It holds partly when the measure misses "
        "by a fifth of the claimed value or less. Otherwise it does not hold.</p>"
        "<table><tr><th>The claim</th><th>Where it was said</th><th>Verdict</th>"
        f"<th>What I measured</th></tr>{rows}</table></section>"
    )


def count_table(rows: list[tuple[str, dict]]) -> str:
    body = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{link(item)}</td></tr>" for name, item in rows
    )
    return f"<table><tr><th>Group</th><th>Length</th></tr>{body}</table>"


def route_section(figures: Figures, total: dict, sections: list) -> str:
    facility = count_table(
        [
            (
                text,
                figures.add(
                    f"Route on {text.lower()}",
                    f"t['total']['km_by_facility']['{key}']",
                    "km",
                    "I add up the matched streets by how they are built, "
                    "and the stretches off the network.",
                ),
            )
            for key, text in (
                ("separated", "A separated path or lane"),
                ("painted", "A painted lane"),
                ("shared", "A street shared with traffic"),
                ("off_network", "No street: the route needs new building"),
            )
        ]
    )
    levels = count_table(
        [
            (
                text,
                figures.add(
                    f"Route at stress level {key}",
                    f"t['total']['km_by_lts']['{key}']",
                    "km",
                    "I add up the matched streets by their stress level.",
                ),
            )
            for key, text in (
                ("1", "Level one"),
                ("2", "Level two"),
                ("3", "Level three"),
                ("4", "Level four"),
            )
        ]
    )
    rows = ""
    for index, section in enumerate(sections):
        prefix = f"t['sections'][{index}]"
        cells = [
            figures.add(label, expression, unit, method)
            for label, expression, unit, method in (
                (
                    "Length of a section",
                    f"{prefix}['route_km']",
                    "km",
                    "I read the length of the section.",
                ),
                (
                    "Safe for all ages in a section",
                    f"{prefix}['km_aaa']",
                    "km",
                    "I add up the streets that are safe for all ages.",
                ),
                (
                    "Breaks in a section",
                    f"len({prefix}['breaks'])",
                    "breaks",
                    "I count the stretches that are not safe for all ages.",
                ),
                (
                    "Crossings with no signal in a section",
                    f"{prefix}['crossings_unsignalised']",
                    "crossings",
                    "I count the crossings with no signal.",
                ),
            )
        ]
        rows += (
            f"<tr><td>{html.escape(section['name'])}</td>"
            + "".join(f"<td>{link(item)}</td>" for item in cells)
            + "</tr>"
        )
    by_section = (
        "<table><tr><th>Section</th><th>Length</th><th>Safe for all ages</th><th>Breaks</th>"
        f"<th>Crossings with no signal</th></tr>{rows}</table>"
    )
    break_rows = []
    for index in range(len(total["breaks"])):
        length = figures.add(
            "Length of a break",
            f"t['total']['breaks'][{index}]['length_m']",
            "m",
            "I join the stretches that are not safe for all ages, "
            "in route order, and read the length.",
        )
        break_rows.append(f"<li>A break of {link(length)}.</li>")
    breaks = "".join(break_rows)
    crossings = "".join(
        f"<li>{html.escape(item['road'])}: {'a signal' if item['signal'] else 'no signal'}.</li>"
        for item in total["crossings"]
    )
    steep = figures.add(
        "Steep stretches",
        "len(t['total']['steep'])",
        "steep stretches",
        "I count the runs of streets at or over the steep limit of the profile.",
    )
    flags = figures.add(
        "Flags for gates, hours or access",
        "len(t['total']['flags'])",
        "flags",
        "I count the streets with opening hours, a gate or access that is not open to the public.",
    )
    return (
        '<section id="route"><h2>What the route is made of</h2>'
        f"<h3>How it is built</h3>{facility}<h3>How busy the streets are</h3>{levels}"
        f"<h3>Each section</h3>{by_section}"
        f"<h3>Breaks in the safe run</h3><ul>{breaks}</ul>"
        f"<h3>Crossings</h3><ul>{crossings}</ul>"
        f"<p>I found {link(steep)} and {link(flags)}. The route figures file lists each one.</p>"
        "</section>"
    )


def fixes_section(figures: Figures) -> str:
    items = [
        (
            "Parking spaces lost",
            "t['total']['disruption']['parking_spaces']",
            "spaces",
            "I add the parking spaces that the fixes remove.",
        ),
        (
            "Traffic lane length lost",
            "t['total']['disruption']['lane_km']",
            "km",
            "I add the traffic lane length that the fixes remove.",
        ),
        (
            "Signals needed",
            "t['total']['disruption']['signals']",
            "signals",
            "I count the crossings that need a signal.",
        ),
        (
            "Refuges needed",
            "t['total']['disruption']['refuges']",
            "refuges",
            "I count the crossings that need a refuge.",
        ),
        (
            "Route with no fix that fits",
            "t['total']['disruption']['no_fit_km']",
            "km",
            "I add the streets where no fix fits.",
        ),
        (
            "Unique people gaining a safe destination",
            "t['total']['access']['access_gains']['unique_people']",
            "people",
            "I make the whole route safe for all ages and count the people who gain a safe way.",
        ),
        (
            "People gaining a safe way for each km",
            "t['total']['access']['gain_per_km']",
            "people",
            "I divide that gain by the route length.",
        ),
        (
            "Projects of the same length that I rank",
            "t['total']['access']['ranked']['projects']",
            "projects",
            "I take ranked projects in order while they fit the route length.",
        ),
    ]
    items.append(
        (
            "Gains counted by type",
            "t['total']['access']['access_gains']['gains_by_type']",
            "people",
            "I count each person once per type gained. People are estimates, not households.",
        )
    )
    for kind in sorted(figures.figures["total"]["access"]["access_gains"]["unique_people_by_type"]):
        items.append(
            (
                f"Unique people by type: {kind.replace('_', ' ')}",
                f"t['total']['access']['access_gains']['unique_people_by_type'][{kind!r}]",
                "people",
                "I count the union of home nodes gaining a destination of this type. "
                "Each node's people share counts once.",
            )
        )
    found = [figures.add(*item) for item in items]
    names = [
        "I would take",
        "The fixes would remove",
    ]
    del names
    lines = "".join(f"<li>{html.escape(item['label'])}: {link(item)}</li>" for item in found)
    surveys = [
        item
        for item in figures.figures["total"]["fixes"]
        if item.get("fit_status") == "needs_survey"
    ]
    survey_note = ""
    if surveys:
        checks = sorted({check for item in surveys for check in item["survey_checks"]})
        survey_note = (
            "<p>These model options need site checks and stay out of confirmed picks.</p><ul>"
            + "".join(f"<li>{html.escape(item['street'])}: needs survey</li>" for item in surveys)
            + "</ul><p>Check "
            + html.escape(", ".join(checks))
            + ".</p>"
        )
    return (
        '<section id="fixes"><h2>What it would take to make the route safe for all ages</h2>'
        "<p>For each stretch that is not safe for all ages I choose the fix that disrupts "
        f"people least and fits the model width.</p>{survey_note}<ul>{lines}</ul></section>"
    )


def map_section() -> str:
    keys = "".join(f"<li>{text}</li>" for text in LEVEL_KEYS)
    return (
        '<section id="map"><h2>Map of the route</h2>'
        "<p>Move over a line or a dot, or tap it, to read what it means.</p>"
        f"<ul>{keys}</ul>"
        '<div id="review-map-canvas" role="region" aria-label="Map of the route"></div></section>'
    )


def page(
    region: Region,
    figures: Figures,
    reply: dict,
    layer: dict,
    total: dict,
    sections: list,
    verdicts: list,
) -> str:
    opening_items = [
        figures.add(
            "Length of the route",
            "t['total']['route_km']",
            "km",
            "I match the route to the streets and add up its length.",
        ),
        figures.add(
            "Route that is safe for all ages",
            "t['total']['km_aaa']",
            "km",
            "I add up the matched streets that are safe for all ages.",
        ),
        figures.add(
            "Breaks in the safe run",
            "len(t['total']['breaks'])",
            "breaks",
            "I join the stretches that are not safe for all ages, in route order, and count them.",
        ),
        figures.add(
            "Crossings with no signal",
            "t['total']['crossings_unsignalised']",
            "crossings",
            "I count the roads that the route crosses or joins where no signal stands.",
        ),
        figures.add(
            "Claims that I judge", "len(v)", "claims", "I count the claims in the claims file."
        ),
    ]
    length, safe, breaks, crossings, claims = opening_items
    verdict_html = verdicts_section(figures, verdicts)
    route_html = route_section(figures, total, sections)
    fixes_html = fixes_section(figures)
    appendix = "".join(review_entry(item) for item in figures.items)
    area = region.name.split(",")[0]
    terms = {area: "the place this review covers.", **GLOSSARY, **REVIEW_GLOSSARY}
    data = json.dumps(layer, sort_keys=True).replace("</", "<\\/")
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Review of a route in {html.escape(region.name)}</title>"
        f"<style>{STYLE}{STYLE_EXTRA}</style>"
        f"<style>{(ASSETS / 'leaflet.css').read_text()}</style>"
        f"<script>{(ASSETS / 'leaflet.js').read_text()}</script>"
        f'<script type="application/json" id="review-data">{data}</script>'
        f"<script>{(ASSETS / 'review_map.js').read_text()}</script></head><body>"
        f"<h1>Review of a route in {html.escape(region.name)}</h1>"
        f"<p>By {html.escape(region.report.author)}</p>"
        '<section id="opening"><h2>What the data shows</h2>'
        f"<p>I checked {link(length)} of route. {link(safe)} of it meets the model's all-ages "
        f"criteria. This does not guarantee child safety. "
        f"I found {link(breaks)} in the safe run and {link(crossings)} with no signal. "
        f"I judge {link(claims)} below.</p>"
        "<p>I ask the author of the plan to read this review and send me a reply. I print every "
        "reply in full. Please read the appendix to check every number.</p></section>"
        f"{map_section()}{verdict_html}{route_html}{fixes_html}{reply_section(reply)}"
        f"{glossary_section(terms)}"
        '<section id="appendix"><h2>How to check every number</h2>'
        f"<p>This review uses the data snapshot of {snapshot_date(region)}.</p>{appendix}"
        "<h3>How to rebuild this review</h3><pre>uv run bikeplan review &lt;route file&gt; "
        "--claims &lt;claims file&gt; --region &lt;region file&gt; "
        "--snapshot &lt;snapshot folder&gt; "
        "--out &lt;folder&gt;</pre></section></body></html>\n"
    )


def build_review(route, claims, region: Region, snapshot, reply=None) -> dict[str, bytes]:
    if region.report.author is None:
        raise ConfigError("report.author is missing: the review needs the name and suburb")
    wanted = read_claims(claims)
    sections = read_route(route)
    profile = load_profile(region.profile, "profiles")
    lines: list = []
    found = route_figures(
        build(snapshot, region, profile), profile, sections, region, snapshot, lines
    )
    verdicts = claim_verdicts(wanted, found["total"])
    texts = {"route_figures.json": dump(found), "verdicts.json": dump(verdicts)}
    digests = [
        {"name": name, "sha256": hashlib.sha256(texts[name].encode()).hexdigest()} for name in FILES
    ]
    total = found["total"]
    layer = {
        "lines": lines,
        "breaks": total["breaks"],
        "crossings": [c for c in total["crossings"] if not c["signal"]],
    }
    figures = Figures(found, verdicts, digests)
    text = page(
        region,
        figures,
        read_reply(reply) if reply else {"sent": [], "replies": []},
        layer,
        total,
        found["sections"],
        verdicts,
    )
    texts |= {
        "route_layer.json": dump(layer),
        "figures.json": dump(figures.items),
        "report.html": text,
    }
    return {name: content.encode() for name, content in texts.items()}


def check_private_paths(route, claims, out, reply=None):
    private = Path.cwd() / "data/private"
    inputs = [Path(path).absolute() for path in (route, claims, reply) if path is not None]
    paths = [*inputs, Path(out).absolute()]
    metadata = sorted(
        {
            folder / "review.yaml"
            for path in inputs
            for folder in (path.parent, path.resolve().parent)
        }
    )
    restricted = any(
        path.is_relative_to(private) or path.resolve().is_relative_to(private) for path in paths
    )
    records = []
    for path in metadata:
        if not path.is_file():
            continue
        try:
            record = yaml.safe_load(path.read_text())
        except yaml.YAMLError as error:
            raise ConfigError(f"{path}: cannot read review settings") from error
        if not isinstance(record, dict) or not isinstance(record.get("public"), bool):
            raise ConfigError(f"{path}: public must be true or false")
        restricted = restricted or record["public"] is False
        records.append(path)
    if restricted:
        for path in [*paths, *records]:
            if not path.is_relative_to(private) or not path.resolve().is_relative_to(private):
                raise ConfigError(f"Private review files must stay under data/private: {path}")


def write_review(route, claims, region: Region, snapshot, out, reply=None) -> list[dict]:
    check_private_paths(route, claims, out, reply)
    files = build_review(route, claims, region, snapshot, reply)
    check_leaks(files["report.html"].decode(), out, snapshot)
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in sorted(files):
        (target / name).write_bytes(files[name])
        lines.append(f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n")
    (target / "SHA256SUMS").write_text("".join(lines))
    return json.loads(files["figures.json"])
