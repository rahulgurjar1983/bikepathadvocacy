import html
import json

from bikeplan.page import ASSETS, calendar_dates, sheet


def project_views(record, frontier):
    features = frontier["shapes"]["features"]
    views = {}
    for block in record["project_sheets"]:
        name = block["scenario"]
        views[name] = {}
        for project in block["sheets"]:
            namespace = f"selected-{name}-"
            target = f"project-{namespace}{project['id']}"
            link = (
                f'<li><a href="#{html.escape(target, quote=True)}" '
                f'data-project-id="{html.escape(project["id"], quote=True)}">'
                f"{html.escape(project['name'])}</a></li>"
            )
            views[name][project["id"]] = {
                "rank": project["rank"],
                "link": link,
                "sheet": sheet(calendar_dates(project), features, namespace),
            }
    selected = record["selected"]
    identity = selected["identity"]
    key = f"{identity['scenario']}:{identity['rank']}"
    chosen = sorted(
        (views[identity["scenario"]][pid] for pid in selected["project_ids"]),
        key=lambda project: project["rank"],
    )
    body = "".join(
        project["sheet"].replace("<article ", f'<article data-package="{key}" ')
        for project in chosen
    )
    section = (
        f'<section id="selected-projects" data-package="{key}"><h2>Selected project plans</h2>'
        f'<p id="selected-package-label">{key}: {selected["kind"]} package, '
        f"{selected['evidence_mode']} evidence.</p>"
        "<p>These plans use this package's model choices. Site checks still need proof.</p>"
        f'<p id="selected-project-empty"{" hidden" if chosen else ""}>'
        "No new works are selected.</p>"
        f'<ol id="selected-project-list">{"".join(p["link"] for p in chosen)}</ol>'
        f'<div id="selected-project-sheets">{body}</div>'
        '<p><a href="#projects">Old minimum-gain shortlist</a> and '
        '<a href="#sheets">its sheets</a> are separate evidence, with their own choices.</p>'
        "</section>"
    )
    data = json.dumps(views, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    scripts = (
        f'<script type="application/json" id="package-view-data">{data}</script>'
        f"<script>{(ASSETS / 'proposal_views.js').read_text()}</script>"
    )
    return section, scripts


def evidence_view(record):
    selected = record["selected"]
    identity = selected["identity"]
    key = f"{identity['scenario']}:{identity['rank']}"
    return (
        f'<section id="selected-evidence" data-package="{html.escape(key, quote=True)}">'
        "<h2>Evidence gaps in the selected package</h2>"
        '<p id="evidence-package"><code>' + html.escape(key) + "</code></p>"
        "<p>These limits belong to this choice. Route gaps name unproved trips, not "
        "a ranked survey plan. Missing school and area proof stays unknown. Model "
        "criteria do not prove field safety. The full curve tables are separate "
        "evidence for all packages.</p>"
        '<p><a href="#F25">Route gap scope and source</a></p>'
        '<p><code id="evidence-summary">'
        + html.escape(json.dumps(selected["evidence_limits"], sort_keys=True))
        + "</code></p></section>"
    )
