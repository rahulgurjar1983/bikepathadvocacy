import hashlib
import html
import json
from pathlib import Path

from bikeplan.report import SOURCES, link

ASSETS = Path(__file__).parent / "assets"
PRELUDE = (
    "import json;d=json.load(open('frontier.json'));"
    "s=[c for c in d['scenarios'] if c['id']=={scenario!r}][0];"
    "p=s['picks'][s['recommended_stop'] or 0];print({expr})"
)
STEP_FIGURES = [
    ("F5", "Access score at the recommended stop", "points", "p['score']", lambda p: p["score"]),
    (
        "F6",
        "Disruption score at the recommended stop",
        "points",
        "p['disruption']",
        lambda p: p["disruption"],
    ),
    (
        "F7",
        "Parking spaces taken at the recommended stop",
        "spaces",
        "p['parking_spaces']",
        lambda p: p["parking_spaces"],
    ),
    (
        "F8",
        "Traffic-lane length taken at the recommended stop",
        "km",
        "p['lane_km']",
        lambda p: p["lane_km"],
    ),
    (
        "F9",
        "Street length with a lower speed limit at the recommended stop",
        "km",
        "p['speed_km']",
        lambda p: p["speed_km"],
    ),
    (
        "F10",
        "Unique people gaining a safe destination at the recommended stop",
        "people",
        "p['unique_people']",
        lambda p: p["unique_people"],
    ),
    (
        "F11",
        "Street length changed at the recommended stop",
        "km",
        "round(sum(p['km_by_fix'].values()),3)",
        lambda p: round(sum(p["km_by_fix"].values()), 3),
    ),
]
METHOD = (
    "I take the projects in the order I picked them, and add up what each one costs and gains. "
    "The shown step is the recommended stop of the {label} scenario. The recipe reads that step "
    "from frontier.json; change the rank in it to check any other step. Unique people count the "
    "union of home nodes gaining a safe destination. Unique people by type use a union for each "
    "type. Gains counted by type sum those type counts and can count a person again. People are "
    "population estimates, not households; each node holds a share of its population unit."
)
ROWS = [
    ("Access score", "score", "F5"),
    ("Disruption score", "disruption", "F6"),
    ("Parking spaces taken", "parking_spaces", "F7"),
    ("Traffic-lane km taken", "lane_km", "F8"),
    ("Speed-change km", "speed_km", "F9"),
    ("Unique people gaining a safe destination", "unique_people", "F10"),
    ("Gains counted by type", "gains_by_type", "F14"),
]
STROKES = ("#1b5e8a", "#2e7d32", "#8a5a00", "#7b2cbf", "#a33")
DASHES = ("", "8 4", "2 4", "10 4 2 4", "6 2")
DASH_NAMES = ("solid", "long dashes", "dots", "dash and dot", "short dashes")
WIDTH = 600
HEIGHT = 300
LEFT = 50
TOP = 20
SPAN_X = 520
SPAN_Y = 220


def frontier_data(raw: dict, before: float, kinds: list, shapes: dict) -> dict:
    baseline = {
        "rank": 0,
        "id": None,
        "kind": None,
        "name": "No change",
        "gain": 0.0,
        "cost": 0.0,
        "disruption": 0.0,
        "parking_spaces": 0,
        "lane_km": 0.0,
        "speed_km": 0.0,
        "signals": 0,
        "refuges": 0,
        "km_by_fix": {},
        "score": before,
        "people": dict.fromkeys(kinds, 0),
        "unique_people": 0,
        "unique_people_by_type": dict.fromkeys(kinds, 0),
        "gains_by_type": 0,
    }
    scenarios = [{**item, "picks": [baseline, *item["picks"]]} for item in raw["scenarios"]]
    default = next((item for item in scenarios if item["id"] == "shipped"), scenarios[0])
    return {
        "baseline": before,
        "default": default["id"],
        "scenarios": scenarios,
        "shapes": shapes,
    }


def default_scenario(frontier: dict) -> dict:
    return next(item for item in frontier["scenarios"] if item["id"] == frontier["default"])


def change_figures(frontier: dict, text: str) -> list[dict]:
    digest = hashlib.sha256(text.encode()).hexdigest()
    chosen = default_scenario(frontier)
    stop = chosen["recommended_stop"] or 0
    pick = chosen["picks"][stop]
    base = {
        "spec": "spec 13",
        "inputs": [{"name": "frontier.json", "sha256": digest}],
        "sources": SOURCES,
    }
    method = METHOD.format(label=chosen["label"])
    figures = [
        {
            **base,
            "id": figure_id,
            "label": label,
            "value": value(pick),
            "unit": unit,
            "method": method,
            "recipe": PRELUDE.format(scenario=chosen["id"], expr=expr),
        }
        for figure_id, label, unit, expr, value in STEP_FIGURES
    ]
    measures = [("F14", "Gains counted by type", "p['gains_by_type']", pick["gains_by_type"])]
    measures += [
        (
            f"F{15 + index}",
            f"Unique people by type: {kind.replace('_', ' ')}",
            f"p['unique_people_by_type'][{kind!r}]",
            count,
        )
        for index, (kind, count) in enumerate(sorted(pick["unique_people_by_type"].items()))
    ]
    figures += [
        {
            **base,
            "id": figure_id,
            "label": label,
            "value": value,
            "unit": "people",
            "method": method,
            "recipe": PRELUDE.format(scenario=chosen["id"], expr=expr),
        }
        for figure_id, label, expr, value in measures
    ]
    steps = sum(len(item["picks"]) for item in frontier["scenarios"])
    figures.append(
        {
            **base,
            "id": "F12",
            "label": "Steps drawn on the access against disruption chart",
            "value": steps,
            "unit": "steps",
            "method": "Each scenario draws one point for no change and one for each project I "
            "picked. I count the points of every scenario.",
            "recipe": "import json;print(sum(len(c['picks']) "
            "for c in json.load(open('frontier.json'))['scenarios']))",
        }
    )
    figures.append(
        {
            **base,
            "id": "F13",
            "label": "Projects up to the recommended stop",
            "value": stop,
            "unit": "projects",
            "method": "I divide each pick's gain by its cost plus one, using full precision. "
            "I compare it with the best ratio so far, including this pick. The stop is the "
            f"last rank at least {chosen['recommend_ratio']} times that best ratio, "
            "even after a weaker pick.",
            "recipe": PRELUDE.format(scenario=chosen["id"], expr="s['recommended_stop'] or 0"),
        }
    )
    return figures


PLACES = {"score": 1, "disruption": 1, "parking_spaces": 0, "lane_km": 3, "speed_km": 3}


def places(key: str) -> int:
    if key in ("unique_people", "gains_by_type") or key.startswith("people."):
        return 0
    if key.startswith("km."):
        return 3
    return PLACES[key]


def number(value, key: str) -> str:
    return f"{value:.{places(key)}f}"


def fix_names(frontier: dict) -> list[str]:
    return sorted(
        {
            fix
            for item in frontier["scenarios"]
            for pick in item["picks"]
            for fix in pick["km_by_fix"]
        }
    )


def total_rows(frontier: dict, pick: dict) -> str:
    rows = [(label, key, figure, pick[key]) for label, key, figure in ROWS]
    rows += [
        (
            f"Unique people by type: {kind.replace('_', ' ')}",
            f"people.{kind}",
            f"F{15 + index}",
            count,
        )
        for index, (kind, count) in enumerate(sorted(pick["unique_people_by_type"].items()))
    ]
    rows += [
        (
            f"Km of {fix.replace('_', ' ')}",
            f"km.{fix}",
            "F11",
            pick["km_by_fix"].get(fix, 0),
        )
        for fix in fix_names(frontier)
    ]
    return "".join(
        f'<tr><th scope="row">{html.escape(label)}</th>'
        f'<td><a href="#{figure}" '
        f"{'data-measure' if key in ('unique_people', 'gains_by_type') else 'data-total'}="
        f'"{html.escape(key, quote=True)}">'
        f"{number(value, key)}</a></td></tr>"
        for label, key, figure, value in rows
    )


def chart_scale(frontier: dict) -> tuple[float, float]:
    points = [pick for item in frontier["scenarios"] for pick in item["picks"]]
    top_x = max(pick["disruption"] for pick in points) or 1
    top_y = max(pick["score"] - frontier["baseline"] for pick in points) or 1
    return top_x, top_y


def chart_points(frontier: dict, item: dict) -> list[tuple[float, float]]:
    top_x, top_y = chart_scale(frontier)
    return [
        (
            LEFT + pick["disruption"] / top_x * SPAN_X,
            TOP + SPAN_Y - (pick["score"] - frontier["baseline"]) / top_y * SPAN_Y,
        )
        for pick in item["picks"]
    ]


def chart_section(frontier: dict) -> str:
    chosen = default_scenario(frontier)
    stop = chosen["recommended_stop"] or 0
    curves = []
    labels = []
    rows = []
    for index, item in enumerate(frontier["scenarios"]):
        points = chart_points(frontier, item)
        selected = item["id"] == chosen["id"]
        text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        curves.append(
            f'<polyline id="curve-{html.escape(item["id"])}" points="{text}" fill="none" '
            f'stroke="{STROKES[index % len(STROKES)]}" '
            f'stroke-dasharray="{DASHES[index % len(DASHES)]}" '
            f'stroke-width="{4 if selected else 2}" data-selected="{str(selected).lower()}"/>'
        )
        labels.append(
            f'<text x="{LEFT + 8}" y="{TOP + 14 + index * 16}" '
            f'fill="{STROKES[index % len(STROKES)]}">'
            f"{html.escape(item['label'])} ({DASH_NAMES[index % len(DASH_NAMES)]})</text>"
        )
        rows += [
            f"<tr><td>{html.escape(item['label'])}</td>"
            + "".join(
                f'<td><a href="#F12">{value}</a></td>'
                for value in (
                    pick["rank"],
                    f"{pick['disruption']:.1f}",
                    f"{pick['score'] - frontier['baseline']:.1f}",
                )
            )
            + "</tr>"
            for pick in item["picks"]
        ]
    x, y = chart_points(frontier, chosen)[stop]
    base_y = TOP + SPAN_Y
    return (
        '<svg id="change-chart" role="img" '
        f'viewBox="0,0,{WIDTH},{HEIGHT}" width="100%" aria-labelledby="change-chart-title">'
        '<title id="change-chart-title">Access gained against disruption, one line for each '
        "scenario, with a dot at the step on the slider</title>"
        f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{base_y}" stroke="#444"/>'
        f'<line x1="{LEFT}" y1="{base_y}" x2="{LEFT + SPAN_X}" y2="{base_y}" stroke="#444"/>'
        f'<text x="{LEFT}" y="{HEIGHT - 8}">More disruption, to the right</text>'
        f'<text x="4" y="{TOP - 6}">More access gained, upward</text>'
        f"{''.join(curves)}{''.join(labels)}"
        f'<circle id="change-dot" cx="{x:.2f}" cy="{y:.2f}" r="7" fill="#fff" stroke="#000" '
        f'stroke-width="3" data-step="{stop}"/></svg>'
        '<table data-for="change-chart"><caption>The same lines as a table</caption>'
        "<tr><th>Scenario</th><th>Step</th><th>Disruption</th><th>Access gained</th></tr>"
        f"{''.join(rows)}</table>"
    )


def change_scripts(frontier: dict) -> str:
    data = json.dumps(frontier, sort_keys=True).replace("</", "<\\/")
    return (
        f'<script type="application/json" id="change-data">{data}</script>'
        f"<script>{(ASSETS / 'change.js').read_text()}</script>"
    )


def capped_note(chosen: dict, note_id: str = "change-capped") -> str:
    if not chosen.get("truncated"):
        return ""
    return (
        f'<p id="{html.escape(note_id)}">The {html.escape(chosen["label"])} curve reached '
        f"its cap of {chosen['evaluated_projects']} projects. The curve is cut short, "
        "even if the recommended stop is earlier. More picks may be possible.</p>"
    )


def change_section(frontier: dict, by_id: dict) -> str:
    chosen = default_scenario(frontier)
    stop = chosen["recommended_stop"] or 0
    pick = chosen["picks"][stop]
    radios = "".join(
        f'<label><input type="radio" name="scenario" id="scenario-{html.escape(item["id"])}" '
        f'value="{html.escape(item["id"])}"'
        f"{' checked' if item['id'] == chosen['id'] else ''} disabled> "
        f"{html.escape(item['label'])}</label>"
        for item in frontier["scenarios"]
    )
    return (
        '<section id="change"><h2>How much change?</h2>'
        '<p id="change-why">The slider opens at my recommended stop for the '
        f"{html.escape(chosen['label'])} scenario: {link(by_id['F13'])}. I stop there because "
        "I divide each pick's gain by its cost plus one. I compare that ratio with the "
        "best ratio so far, including this pick. I mark the last rank whose ratio is at least "
        f'<a href="#F13">{chosen["recommend_ratio"]}</a> times that best ratio. '
        "I use full precision, "
        "before rounding the values shown here. A later pick can meet the rule again. "
        "The fixes up to that stop change "
        f"{link(by_id['F11'])} of street. Move the slider to see the cost of doing less or "
        "more.</p>"
        + "".join(
            capped_note(
                item,
                "change-capped" if item["id"] == chosen["id"] else f"change-capped-{item['id']}",
            )
            for item in frontier["scenarios"]
        )
        + f"<fieldset><legend>Scenario</legend>{radios}</fieldset>"
        '<p><label for="change-slider">How much change</label> '
        f'<input type="range" id="change-slider" min="0" max="{len(chosen["picks"]) - 1}" '
        f'value="{stop}" step="1" disabled> <output id="change-step"></output></p>'
        '<table id="change-totals"><caption>Totals for the projects picked so far</caption>'
        f"{total_rows(frontier, pick)}</table>"
        f"{chart_section(frontier)}</section>"
    )
