import html
import json

from bikeplan.page import ASSETS

COUNTS = (
    ("parking_spaces", "parking spaces", "{:.0f}"),
    ("lane_km", "traffic-lane km", "{:.2f}"),
    ("speed_km", "lower-speed km", "{:.2f}"),
    ("path_km", "path km", "{:.2f}"),
    ("score", "disruption score", "{:.1f}"),
)
PLOT = (40, 10, 350, 200)


def plain(key: tuple, text: str) -> str:
    return text


def choose(options: list[dict], share: float) -> dict:
    best = max(item["steps"][-1]["totals"]["score"] for item in options)
    close = [
        (item["steps"][-1]["disruption"]["score"], index)
        for index, item in enumerate(options)
        if item["steps"][-1]["totals"]["score"] >= best - 1
    ]
    pick = options[min(close)[1]]
    return {"pick": pick["id"], "step": recommended(pick, share)} | asked(
        pick, recommended(pick, share)
    )


def recommended(option: dict, share: float) -> int:
    scores = [item["totals"]["score"] for item in option["steps"]]
    target = scores[0] + share * (scores[-1] - scores[0])
    return next(index for index, score in enumerate(scores) if score >= target - 1e-9)


def asked(option: dict, step: int) -> dict:
    built = [index for item in option["steps"][1 : step + 1] for index in item["works"]]
    streets = sorted({option["works"][index]["street"] for index in built})
    names = ", ".join(streets) if streets else "no street"
    intro = (
        f"I ask council to adopt {option['name']} as its bike network plan and to fund the "
        f"design of the works up to step {step}, on the streets below."
    )
    ask = (
        f"I ask council to adopt {option['name']} as its bike network plan and to fund the "
        f"design of the works up to step {step}: {names}."
    )
    return {"streets": streets, "ask": ask, "built": built, "intro": intro, "names": names}


def tenths(option: dict) -> list[dict]:
    full = option["steps"][-1]["disruption"]["score"]
    rows = []
    for tenth in range(11):
        spent = full * tenth / 10
        reached = [item for item in option["steps"] if item["disruption"]["score"] <= spent + 1e-9]
        rows.append({"share": tenth * 10, "spent": spent, "score": reached[-1]["totals"]["score"]})
    return rows


def totals_text(option: dict, number: int) -> str:
    item = option["steps"][number]
    totals = item["totals"]
    places = ", ".join(f"{kind} {count}" for kind, count in sorted(totals["places_safe"].items()))
    spent = ", ".join(
        f"{label} {pattern.format(item['disruption'][name])}" for name, label, pattern in COUNTS
    )
    return (
        f"{option['name']}, step {number}: safety score {totals['score']:.1f} "
        f"({totals['safe_trips']} of {totals['trips']} trips safe). "
        f"All-ages km {totals['km_all_ages']:.2f}. Places with a safe trip: {places}. "
        f"Disruption: {spent}."
    )


def name_of(options: list[dict], key: str) -> str:
    return next(item["name"] for item in options if item["id"] == key)


def options_row(option: dict, options: list[dict], ref=plain) -> str:
    first, last = option["steps"][0]["totals"], option["steps"][-1]
    key = option["id"]
    places = ", ".join(
        f"{html.escape(kind)} {ref(('places', key, kind), str(count))}"
        for kind, count in sorted(last["totals"]["places_safe"].items())
    )
    spent = ", ".join(
        f"{label} {ref(('spent', key, name), pattern.format(last['disruption'][name]))}"
        for name, label, pattern in COUNTS
    )
    same = (
        f" (same as {html.escape(name_of(options, option['same_as']))})"
        if option["same_as"]
        else ""
    )
    cells = [
        f"{html.escape(option['name'])}{same}",
        ref(("km", key), f"{option['km']:.1f}"),
        ref(("today", key), f"{first['score']:.1f}"),
        ref(("full", key), f"{last['totals']['score']:.1f}"),
        places,
        spent,
    ]
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def opening(options: list[dict], choice: dict, ref=plain) -> str:
    head = (
        "Option",
        "Km",
        "Safety score today",
        "Safety score with every work built",
        "Places with a safe trip",
        "Disruption with every work built",
    )
    top = "".join(f"<th>{name}</th>" for name in head)
    rows = "".join(options_row(item, options, ref) for item in options)
    pick = name_of(options, choice["pick"])
    return (
        '<section id="options"><h2>Network options</h2>'
        f"<p>My pick: <strong>{html.escape(pick)}</strong>, built up to step "
        f"{ref(('pickstep',), str(choice['step']))}.</p>"
        f"<h3>My ask</h3><p>{ref(('ask',), html.escape(choice['intro']))}</p>"
        f"<details><summary>The streets of the works</summary>"
        f"<p>{ref(('ask',), html.escape(choice['names']))}</p></details>"
        f"<table><caption>The options side by side</caption><thead><tr>{top}</tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def plot(option: dict, step: int, top: float) -> tuple[float, float]:
    left, up, wide, high = PLOT
    spent = option["steps"][step]["disruption"]["score"]
    score = option["steps"][step]["totals"]["score"]
    return (
        round(left + wide * (spent / top if top else 0.0), 1),
        round(up + high * (1 - score / 100), 1),
    )


def chart(options: list[dict], choice: dict, top: float, ref=plain) -> str:
    left, up, wide, high = PLOT
    lines = "".join(
        f'<polyline fill="none" stroke="{colour}" stroke-width="2" points="'
        + " ".join("{},{}".format(*plot(item, step, top)) for step in range(len(item["steps"])))
        + '"/>'
        for item, colour in zip(options, ("#1b5e8a", "#2e7d32", "#8a5a00", "#7b3fa0"), strict=False)
    )
    keys = "".join(
        f"<li>{html.escape(item['name'])}: {colour}</li>"
        for item, colour in zip(options, ("blue", "green", "brown", "purple"), strict=False)
    )
    pick = next(item for item in options if item["id"] == choice["pick"])
    x, y = plot(pick, choice["step"], top)
    head = "".join(f"<th>{html.escape(item['name'])}</th>" for item in options)
    body = ""
    for tenth in range(11):
        cells = "".join(
            "<td>{}</td>".format(
                ref(
                    ("tenths",),
                    "{:.1f} at {:.1f}".format(
                        tenths(item)[tenth]["score"], tenths(item)[tenth]["spent"]
                    ),
                )
            )
            for item in options
        )
        body += f"<tr><td>{ref(('tenths',), f'{tenth * 10}%')}</td>{cells}</tr>"
    return (
        '<section id="chart"><h2>Safety against disruption</h2>'
        f'<svg id="chart-safety" role="img" viewBox="0,0,400,230" width="100%" '
        'aria-labelledby="chart-safety-title"><title id="chart-safety-title">Safety score '
        "against disruption score for each option</title>"
        f'<line x1="{left}" y1="{up + high}" x2="{left + wide}" y2="{up + high}" stroke="#444"/>'
        f'<line x1="{left}" y1="{up}" x2="{left}" y2="{up + high}" stroke="#444"/>'
        f'{lines}<circle id="chart-dot" cx="{x}" cy="{y}" r="5" fill="#a01010"/></svg>'
        f"<ul>{keys}</ul>"
        '<table data-for="chart-safety"><caption>Safety score and disruption score at each tenth '
        "of the full "
        f"disruption of each option</caption><tr><th>Share of full disruption</th>{head}</tr>"
        f"{body}</table></section>"
    )


def works_section(option: dict, choice: dict, ref=plain) -> str:
    rows = [
        (option["works"][index], number)
        for number, item in enumerate(option["steps"][1 : choice["step"] + 1], 1)
        for index in item["works"]
    ]
    rows.sort(key=lambda row: (row[0]["street"], row[0]["fix"], row[1]))
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{ref(('works',), cell)}</td>"
            for cell in (
                html.escape(item["street"]),
                html.escape(item["fix"]),
                f"{item['km']:.2f}",
                str(item["parking_spaces"]),
                f"{item['lane_km']:.2f}",
                f"{item['speed_km']:.2f}",
                f"{item['score']:.1f}",
                str(number),
            )
        )
        + "</tr>"
        for item, number in rows
    )
    head = "".join(
        f"<th>{name}</th>"
        for name in (
            "Street",
            "Fix",
            "Km",
            "Parking spaces",
            "Traffic-lane km",
            "Lower-speed km",
            "Disruption score",
            "Step",
        )
    )
    return (
        f'<section id="works"><h2>Works of {html.escape(option["name"])} by street</h2>'
        f"<p>Works up to the recommended step: {ref(('works',), str(len(rows)))}.</p>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></section>"
    )


def no_fix_section(options: list[dict], ref=plain) -> str:
    km = sum(gap["km"] for option in options for gap in option["no_fix"])
    parts = ""
    for option in options:
        rows = "".join(
            "<li>"
            + ref(
                ("nofix",),
                f"{html.escape(item['street'])}: {item['km']:.2f} km, {len(item['links'])} links",
            )
            + "</li>"
            for item in option["no_fix"]
        )
        parts += f"<h3>{html.escape(option['name'])}</h3><ul>{rows or '<li>none</li>'}</ul>"
    return (
        '<section id="no-fix"><h2>Links with no fix</h2>'
        "<p>No design in the tool makes these links safe for all ages. They stay as they are at "
        f"every step. Km of links with no fix, all options: {ref(('nofix',), f'{km:.2f}')}.</p>"
        f"{parts}</section>"
    )


def quality_section(options: list[dict], ref=plain) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(item['name'])}</td>"
        "<td>"
        + ref(
            ("quality", item["id"]),
            f"{100 * item['steps'][0]['totals']['assumed_share']:.1f}%",
        )
        + "</td></tr>"
        for item in options
    )
    return (
        '<section id="quality"><h2>Data quality</h2>'
        "<p>Every rating here is modelled. This is the share of each option's km that rests on "
        "assumed or unknown inputs.</p>"
        f"<table><tr><th>Option</th><th>Share of km</th></tr>{rows}</table></section>"
    )


def map_section(options: list[dict], choice: dict, ref=plain) -> str:
    switch = "".join(
        f'<label><input type="radio" name="option" id="option-{item["id"]}"'
        f"{' checked' if item['id'] == choice['pick'] else ''}> {html.escape(item['name'])}</label>"
        for item in options
    )
    pick = next(item for item in options if item["id"] == choice["pick"])
    return (
        '<section id="map"><h2>Map of the network options</h2>'
        '<div id="map-controls" hidden><fieldset><legend>Option</legend>'
        f"{switch}</fieldset>"
        '<label>How much disruption: <input type="range" id="disruption-slider" min="0" '
        f'max="{len(pick["steps"]) - 1}" value="{choice["step"]}"></label></div>'
        "<p>Green: all ages today. Blue: made all ages by works up to the step. Red: still not "
        'all ages.</p><div id="network-map" role="region" aria-label="Map of the option"></div>'
        f'<p id="step-totals" aria-live="polite">'
        f"{ref(('step',), html.escape(totals_text(pick, choice['step'])))}</p>"
        "</section>"
    )


def map_data(
    options: list[dict], choice: dict, top: float, places: list[dict], share: float
) -> str:
    saved = {
        "pick": choice["pick"],
        "places": places,
        "options": [
            {
                "id": item["id"],
                "rec": choice["step"] if item["id"] == choice["pick"] else recommended(item, share),
                "lines": item["lines"],
                "steps": [
                    {
                        "works": step["works"],
                        "text": totals_text(item, number),
                        "dot": list(plot(item, number, top)),
                    }
                    for number, step in enumerate(item["steps"])
                ],
            }
            for item in options
        ],
    }
    return json.dumps(saved, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")


def network_report(
    options: list[dict], share: float, places: list[dict] | None = None, ref=plain
) -> tuple[str, str]:
    choice = choose(options, share)
    top = max(item["steps"][-1]["disruption"]["score"] for item in options)
    pick = next(item for item in options if item["id"] == choice["pick"])
    head = (
        f"<style>{(ASSETS / 'leaflet.css').read_text()}"
        "#network-map{height:24rem;border:1px solid #444}</style>"
        f"<script>{(ASSETS / 'leaflet.js').read_text()}</script>"
        '<script type="application/json" id="network-data">'
        f"{map_data(options, choice, top, places or [], share)}</script>"
        f"<script>{(ASSETS / 'network.js').read_text()}</script>"
    )
    body = (
        opening(options, choice, ref)
        + map_section(options, choice, ref)
        + chart(options, choice, top, ref)
        + works_section(pick, choice, ref)
        + no_fix_section(options, ref)
        + quality_section(options, ref)
    )
    return head, body
