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
SCHOOLS = (
    "pop={};"
    "[pop.__setitem__(s['node'],pop.get(s['node'],0)+s['people']) "
    "for s in d['trip_sources']['population']['shares']];"
    "print(sum(1 for t in p['school_coverage']['sites'] if any("
    "x['destination'] in t['destination_ids'] and x['evidence_status']=='confirmed' "
    "and pop.get(x['origin'],0)>0 for x in p['strict'])))"
)
SELECT = (
    "s=set(p['element_ids']);j=set(p['project_ids']);"
    "m=lambda r:(not r.get('element_ids') and not r.get('project_ids')) "
    "or bool(set(r.get('element_ids',[]))&s or set(r.get('project_ids',[]))&j);"
    "k=d['proposal_metadata']['contents'];"
)
STAGES = "print(len([r for r in k.get('stages',[]) if m(r)]))"
COST = "print(sum(r[{end!r}] for r in k.get('costs',[]) if r['kind']=='capital' and m(r)))"


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


def delivery_figures(frontier, proposal, text, number):
    curve, packages, identity = selected_package(frontier, proposal)
    package = packages[identity["rank"]]
    contents = frontier["proposal_metadata"]["contents"] or {}
    selected = set(package["element_ids"])
    projects = set(package["project_ids"])

    def matches(row):
        elements = set(row.get("element_ids", []))
        refs = set(row.get("project_ids", []))
        return (not elements and not refs) or bool(elements & selected or refs & projects)

    people = {}
    for item in frontier["trip_sources"]["population"]["shares"]:
        people[item["node"]] = people.get(item["node"], 0) + item["people"]
    rows = []
    coverage = package.get("school_coverage")
    if coverage is not None:
        served = sum(
            1
            for site in coverage["sites"]
            if any(
                w["destination"] in site["destination_ids"]
                and w["evidence_status"] == "confirmed"
                and people.get(w["origin"], 0) > 0
                for w in package["strict"]
            )
        )
        rows.append(
            (
                "School sites with a confirmed return trip, from the route list",
                served,
                "school sites",
                SCHOOLS,
                "I count each saved school site that a positive-population origin reaches "
                "with a confirmed return trip in frontier.json.",
            )
        )
    stages = [row for row in contents.get("stages", []) if matches(row)]
    if stages:
        rows.append(
            (
                "Delivery stages that touch the selected works, from the saved stage records",
                len(stages),
                "stages",
                STAGES,
                "I count the stage records whose works or projects overlap the selected package.",
            )
        )
    costs = [row for row in contents.get("costs", []) if row["kind"] == "capital" and matches(row)]
    if costs:
        for end, word in (("low", "Lowest"), ("high", "Highest")):
            rows.append(
                (
                    f"{word} sourced capital cost of the selected works, from the cost records",
                    sum(row[end] for row in costs),
                    contents["costs"][0]["currency"],
                    COST.format(end=end),
                    f"I add the {end} end of each sourced capital cost record that touches the "
                    "selected package. Source exclusions still apply.",
                )
            )
    head = HEAD.format(scenario=identity["scenario"], rank=identity["rank"]) + SELECT
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
