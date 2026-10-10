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
        "trip_sources": raw.get("trip_sources", {}),
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
    sources = frontier.get("trip_sources", {})
    compact = {
        **frontier,
        "trip_sources": {
            **sources,
            "population": {
                key: value
                for key, value in sources.get("population", {}).items()
                if key != "shares"
            },
        },
        "scenarios": [
            {
                **{key: value for key, value in curve.items() if key != "works_catalog"},
                "trip_packages": [
                    {
                        key: value
                        for key, value in package.items()
                        if key in {"package", "project_ids", "element_ids"}
                    }
                    | {
                        "resident_outcomes": {
                            key: {
                                name: value
                                for name, value in record.items()
                                if name != "membership"
                            }
                            if isinstance(record, dict)
                            else record
                            for key, record in package.get("resident_outcomes", {}).items()
                        }
                    }
                    for package in curve.get("trip_packages", [])
                ],
            }
            for curve in frontier["scenarios"]
        ],
    }
    data = json.dumps(compact, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
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


def proposal_opening(frontier: dict) -> str:
    chosen = default_scenario(frontier)
    rank = chosen["recommended_stop"] or 0
    pick = chosen["picks"][rank]
    status = f"{chosen['label']} ({chosen['id']}) proposal, rank "
    state = (
        "No new works are selected."
        if rank == 0
        else "I propose the modelled works in this selection."
    )
    fields = [
        ("Modelled parking spaces removed", "parking_spaces", "F7"),
        ("Modelled traffic-lane km removed", "lane_km", "F8"),
        ("Modelled lower-speed street km", "speed_km", "F9"),
    ]
    impacts = "".join(
        f'<dt>{label}</dt><dd><a href="#{figure}" data-opening="{key}">'
        f"{number(pick[key], key)}</a></dd>"
        for label, key, figure in fields
    )
    return (
        f'<section id="opening" data-package="{html.escape(chosen["id"])}:{rank}">'
        "<h2>My proposal and its trade-offs</h2>"
        f'<p id="package-status" role="status" aria-live="polite" aria-atomic="true">'
        f'{html.escape(status)}<a href="#F13">{rank}</a></p>'
        f'<p id="proposal-state">{state}</p>'
        "<p>I checked the modelled route choices. Useful complete trips and school sites served "
        "before, after and newly served are unknown. "
        "Entrance links and return trips still need proof. "
        "Schools, stations and other places are model goals, not a proved joined network.</p>"
        "<p>Modelled route works are in the "
        '<a href="#change-totals">selected model totals</a>. '
        "Crossing works, existing links retained and remaining route gaps still need checks. "
        "I keep these limits beside the lasting space changes.</p>"
        f"<dl>{impacts}</dl>"
        "<p>Parking before, after, added and net change are unknown without an inventory. "
        "These loss estimates do not prove the full parking impact.</p>"
        "<p>Capital cost: unknown. Upkeep cost: unknown. No sourced rates or budget are supplied. "
        "First delivery stage: unknown; no funded date or build order is proved.</p>"
        "<p>Key gaps: useful trips, school coverage, unique resident gains, usable widths, "
        "safe crossing movements and local walking, tree, bus and driveway effects need checks.</p>"
        '<p id="council-ask">I ask council to scope a costed concept design for the selected works '
        "and check their usable widths and crossing movements before a build decision. "
        "For no new works, I ask council to name a useful route goal and seek its missing public "
        "records first. A ranked survey plan tied to those routes is still pending. "
        "The owner, approvals and funding are unknown.</p>"
        '<p>Please see the <a href="#street-plans">local works and their limits</a> '
        'and <a href="#delivery">next decision</a>.</p></section>'
    )


def change_section(frontier: dict, by_id: dict, inventory: str = "") -> str:
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
        '<section id="change"><h2>Options: how much change?</h2>'
        "<p>These curves test weights. They may choose the same works; "
        "they are not distinct route plans.</p>"
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
        '<details id="curve-table"><summary>Full curve tables and street evidence</summary>'
        f"{inventory}{chart_section(frontier)}</details></section>"
    )
