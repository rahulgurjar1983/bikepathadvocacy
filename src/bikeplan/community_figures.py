import hashlib
import html

SOURCES = [
    {
        "name": "Snapshot trip evidence, works catalog and OpenStreetMap contributors",
        "licence": "See snapshot manifest; OpenStreetMap ODbL 1.0",
        "request": "Route witnesses, population shares and works catalog in frontier.json",
    }
]

HEAD = (
    "import json;d=json.load(open('frontier.json'));"
    "c=next(c for c in d['scenarios'] if c['id']=={scenario!r});"
    "p=c['trip_packages'][{rank}];b=c['trip_packages'][0];"
)
RESIDENTS = (
    "pairs=lambda q:{(w['origin'],w['destination']) for w in q['strict']};"
    "new={o for o,_ in pairs(p)-pairs(b)};"
    "print(sum(s['people'] for s in d['trip_sources']['population']['shares'] "
    "if s['people']>0 and s['node'] in new))"
)
ROADS = (
    "k=c['works_catalog'];i=set(p['works']['element_ids']);"
    "print(len({k[x]['road_id'] for x in i if k[x]['kind']=='link'}))"
)
PARKING = (
    "k=c['works_catalog'];i=set(p['works']['element_ids']);"
    "print(sum(k[x]['parking_spaces']['removed'] for x in i "
    "if k[x]['parking_spaces']['removed'] is not None))"
)


def selected_package(frontier, proposal):
    identity = proposal["selected"]["identity"]
    curve = next(c for c in frontier["scenarios"] if c["id"] == identity["scenario"])
    return curve, curve["trip_packages"], identity


def community_figures(frontier, proposal, text, number):
    curve, packages, identity = selected_package(frontier, proposal)
    package, baseline = packages[identity["rank"]], packages[0]
    catalog = curve["works_catalog"]
    ids = set(package["works"]["element_ids"])
    shares = frontier["trip_sources"]["population"]["shares"]

    def pairs(found):
        return {(w["origin"], w["destination"]) for w in found["strict"]}

    gained = {origin for origin, _ in pairs(package) - pairs(baseline)}
    removed = [
        catalog[key]["parking_spaces"]["removed"]
        for key in ids
        if catalog[key]["parking_spaces"]["removed"] is not None
    ]
    rows = [
        (
            "Complete return-trip witnesses in the selected package, from the route list",
            len(package["strict"]),
            "return trips",
            "print(len(p['strict']))",
            "I count the saved route witnesses of the selected package in frontier.json.",
        )
    ]
    if package["resident_outcomes"]["strict"]["unique_residents"]["after"] is not None:
        rows.append(
            (
                "Residents gaining a confirmed return trip, from the population shares",
                sum(
                    item["people"]
                    for item in shares
                    if item["people"] > 0 and item["node"] in gained
                ),
                "estimated residents",
                RESIDENTS,
                "I take the origins of trips the baseline lacks and add each population share "
                "once from frontier.json.",
            )
        )
    rows += [
        (
            "Unique roads with new physical works, from the works catalog",
            len({catalog[key]["road_id"] for key in ids if catalog[key]["kind"] == "link"}),
            "roads",
            ROADS,
            "I count the distinct road ids of the link works in the selected package.",
        ),
        (
            "Parking spaces removed in the known physical works, from the works catalog",
            sum(removed),
            "parking spaces",
            PARKING,
            "I add the known removed spaces of each work in the selected package.",
        ),
    ]
    head = HEAD.format(scenario=identity["scenario"], rank=identity["rank"])
    digest = hashlib.sha256(text.encode()).hexdigest()
    return [
        {
            "id": f"F{number + index}",
            "spec": "spec 16",
            "label": label,
            "value": value,
            "unit": unit,
            "inputs": [{"name": "frontier.json", "sha256": digest}],
            "sources": SOURCES,
            "method": method
            + " It does not read proposal.json, so a changed saved answer cannot hide.",
            "recipe": head + body,
        }
        for index, (label, value, unit, body, method) in enumerate(rows)
    ]


def community_section(figures):
    items = "".join(
        f'<li><a href="#{item["id"]}">{html.escape(item["label"])}</a>: '
        f'<a href="#{item["id"]}">{item["value"]}</a> {html.escape(item["unit"])}.</li>'
        for item in figures
    )
    return (
        '<section id="independent-checks"><h2>Independent checks of the headline numbers</h2>'
        "<p>Each line below is rebuilt by a short program from frontier.json alone. "
        "A match with the saved proposal shows the two agree.</p>"
        f"<ul>{items}</ul></section>"
    )
