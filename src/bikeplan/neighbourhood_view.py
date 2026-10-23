import hashlib
import html

from bikeplan.proposal_record import AREA_LIMITS

PATTERNS = {
    "benefit_and_impact": "Benefits and impacts",
    "benefit_only": "Benefits, no mapped impact",
    "impact_only": "Impacts, no mapped benefit",
    "none": "No works, benefits or impacts here",
}


def selected_areas(proposal):
    return proposal["selected"].get("local_areas")


def words(value):
    return html.escape(str(value).replace("_", " "))


def work_label(key, position):
    return f"{words(key.split(':')[0])} work {position}"


def count(number, noun):
    if number is None:
        return f"unknown {noun}"
    if isinstance(number, list | tuple | set):
        number = len(number)
    return f"{number:,} {noun}"


def source_text(item):
    if "source" in item:
        return str(item["source"])
    return f"{item['title']}, {item['publisher']}, read {item['read_on']}"


def work_links(area):
    roles = area["works"]["routes"]

    def connects(key):
        return words(", ".join(roles.get(key) or ["no proved destination"]))

    return ", ".join(
        f'<a href="#physical-works" data-work-id="{html.escape(key, quote=True)}">'
        f"{work_label(key, position)}</a> (connects {connects(key)})"
        for position, key in enumerate(area["works"]["parking_element_ids"], 1)
    )


def area_facts(area):
    removed = area["parking_spaces"]["removed"]["known_subtotal"]
    schools = area["schools"]
    effects = len(area["access_effects"])
    return (
        f"{count(round(area['works']['length_m']), 'm of works')}; "
        f"{count(removed, 'parking spaces removed')} (known so far); "
        f"{count(area['residents']['newly_gained'], 'residents newly gain a destination')}; "
        f"{count(area['residents']['after'], 'residents reach a destination after')}; "
        f"{count(schools['newly_served'], 'school sites newly served')}, "
        f"{count(schools['served_after'], 'served after')}, "
        f"{count(schools['not_served'], 'not served')}; "
        f"{count(effects, 'works with turn or access changes to resolve')}"
    )


def area_block(area):
    return (
        f'<div data-area-id="{html.escape(area["id"], quote=True)}" '
        f'data-pattern="{area["pattern"]}"><h3>{html.escape(area["name"])}</h3>'
        f"<p>{PATTERNS[area['pattern']]}: {area_facts(area)}.</p>"
        f"<p>Works placed here: {work_links(area) or 'none'}.</p></div>"
    )


def unallocated_block(local):
    loose = local["unallocated"]
    items = "".join(
        f'<li data-unallocated-id="{html.escape(item["id"], quote=True)}">'
        f"{work_label(item['id'], position)}</li>"
        for position, item in enumerate(loose["works"], 1)
    )
    return (
        "<p>Records with no usable location stay out of every area and are never counted "
        f"twice. Unplaced: "
        f"{count(loose['parking_spaces']['removed']['known_subtotal'], 'parking spaces removed')}, "
        f"{count(loose['residents']['newly_gained'], 'residents newly gaining a destination')} and "
        f"{count(loose['schools'], 'school sites')}."
        f"</p><p>Works with no area:</p><ul>{items or '<li>None</li>'}</ul>"
    )


def neighbourhood_section(proposal, residents_ref, works_ref):
    local = selected_areas(proposal)
    if local is None:
        return (
            '<section id="neighbourhoods"><h2>Neighbourhood benefits and impacts</h2>'
            f"<p>{html.escape(AREA_LIMITS[False])}. Area-level benefits and impacts are "
            "unknown.</p></section>"
        )
    sources = "".join(
        f"<li>{html.escape(item['name'])}: {html.escape(source_text(item))}</li>"
        for item in local["area_sources"]
    )
    region = local["region"]
    return (
        '<section id="neighbourhoods"><h2>Neighbourhood benefits and impacts</h2>'
        "<p>Each area shows what it gains beside what it gives up, for the same package "
        "as the works above. A road that crosses two areas is split by its geometry. "
        f'Across the region, <a href="#{works_ref}">works with no area</a> are listed below '
        f'and <a href="#{residents_ref}">residents with a located home who gain a '
        "destination</a> are counted once. "
        f"{html.escape(region['residents']['overlap_note'])}</p>"
        + "".join(area_block(area) for area in local["areas"])
        + unallocated_block(local)
        + f"<p>Area boundaries and their sources:</p><ul>{sources}</ul>"
        f"<p>{html.escape(AREA_LIMITS[True])}. Field safety and parking use are not proved.</p>"
        "</section>"
    )


def figure(number, label, value, unit, text, recipe):
    return {
        "id": f"F{number}",
        "spec": "spec 16",
        "label": label,
        "value": value,
        "unit": unit,
        "inputs": [{"name": "proposal.json", "sha256": hashlib.sha256(text).hexdigest()}],
        "sources": [
            {
                "name": "Sourced area boundaries and saved works catalog",
                "licence": "See area source in proposal.json",
                "request": "local_areas of the selected package in proposal.json",
            }
        ],
        "method": (
            "I read this figure from the neighbourhood block of the selected package in the "
            "saved proposal record. Works are placed by geometry once; residents are a union "
            "over all areas; records without a usable location stay unallocated."
        ),
        "recipe": (
            "import json;a=json.load(open('proposal.json'))['selected']['local_areas'];"
            f"print({recipe})"
        ),
    }


def neighbourhood_figures(proposal, text, number):
    local = selected_areas(proposal)
    if local is None:
        return []
    return [
        figure(
            number,
            "Residents with a located home who newly gain a destination, counted once "
            "across all areas",
            local["region"]["residents"]["located_newly_gained"],
            "people",
            text,
            "a['region']['residents']['located_newly_gained']",
        ),
        figure(
            number + 1,
            "Works with no usable area",
            len(local["unallocated"]["works"]),
            "works",
            text,
            "len(a['unallocated']['works'])",
        ),
    ]
