import dataclasses
import html
import json
from datetime import datetime
from pathlib import Path

from bikeplan.config import Num

ASSETS = Path(__file__).parent / "assets"
OSM_CREDIT = {
    "source": "OpenStreetMap contributors",
    "licence": "ODbL 1.0",
    "attribution": "© OpenStreetMap contributors",
    "line": "© OpenStreetMap contributors, ODbL 1.0",
}
DISRUPTION_LABELS = [
    ("parking_spaces", "Parking spaces removed"),
    ("lane_km", "Car lane km taken"),
    ("speed_km", "Speed limit km lowered"),
    ("signals", "Signals added"),
    ("refuges", "Refuges added"),
]
STRIP_COLORS = {
    "parking": "#c9a66b",
    "painted_lane": "#84b6d9",
    "through": "#8b9299",
    "median": "#d8c967",
    "spare": "#e9ecef",
    "cycleway": "#45a66a",
    "separator": "#2e555a",
}
ROBUST_LABELS = {"robust": "holds up", "check on site": "check on site"}
METHOD = [
    "The tool reads one snapshot of OpenStreetMap and the other open data named under credits. "
    "It makes no network call.",
    "It builds the street network and gives every street a stress level from 1 to 4 by the "
    "Furth tables. AAA means it meets the model's all-ages criteria. "
    "This does not guarantee child safety.",
    "It estimates the width of each street from lane tags, width tags and the land reserve, and "
    "keeps the best source. It then tests six fixes against that width.",
    "It measures access: for each home it checks which places a person can reach on safe "
    "streets within the reach limit, and scores that by place type.",
    "It picks projects one at a time. Each project is the set of street and junction fixes with "
    "the best gain in access for its cost, until no project gains enough.",
]


def credits_for(manifest: dict) -> list[dict]:
    found = {
        (entry["source"], entry["licence"], entry["attribution"]) for entry in manifest["files"]
    }
    rows = [
        {
            "source": source,
            "licence": licence,
            "attribution": attribution,
            "line": f"{attribution}, {licence}",
        }
        for source, licence, attribution in found
    ]
    rows.append(dict(OSM_CREDIT))
    unique = {row["line"] + row["source"]: row for row in rows}
    return [unique[key] for key in sorted(unique)]


def profile_rows(item, prefix=""):
    if isinstance(item, Num):
        yield prefix, item.value, item.source, item.assumption
    elif isinstance(item, dict):
        for key, value in item.items():
            yield from profile_rows(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(item, list):
        for index, value in enumerate(item):
            yield from profile_rows(value, f"{prefix}[{index}]")
    elif dataclasses.is_dataclass(item):
        for field in dataclasses.fields(item):
            name = f"{prefix}.{field.name}" if prefix else field.name
            yield from profile_rows(getattr(item, field.name), name)


def cell(value) -> str:
    return f"<td><code>{html.escape(str(value))}</code></td>"


def table(head: list[str], rows: list[list]) -> str:
    top = "".join(f"<th>{html.escape(name)}</th>" for name in head)
    body = "".join(f"<tr>{''.join(cell(value) for value in row)}</tr>" for row in rows)
    return f"<table><thead><tr>{top}</tr></thead><tbody>{body}</tbody></table>"


def summary_section(summary: dict) -> str:
    score = summary["score"]
    fixes = summary["km_by_fix"]
    fix_rows = [[name, f"{km:.3f}"] for name, km in sorted(fixes.items())] or [["none", "0.000"]]
    disruption = [[label, summary["disruption"][key]] for key, label in DISRUPTION_LABELS]
    people = [[kind, f"{count:.0f}"] for kind, count in sorted(summary["safe_people_gain"].items())]
    by_kind = [[kind, count] for kind, count in sorted(summary["projects_by_kind"].items())]
    corridors = summary["corridor_candidates"]
    corridor_rows = [
        [name.replace("_", " "), corridors[name]] for name in ("made", "picked", "not_picked")
    ]
    return (
        '<section id="summary"><h2>Summary</h2>'
        f"<p>Access score {score['before']:.1f} before and {score['after']:.1f} after "
        f"{summary['projects']} projects.</p>"
        "<h3>Projects picked, by kind</h3>"
        f"{table(['Kind', 'Projects'], by_kind)}"
        "<h3>Corridor candidates</h3>"
        f"{table(['Outcome', 'Candidates'], corridor_rows)}"
        "<h3>Kilometres by fix</h3>"
        f"{table(['Fix', 'km'], fix_rows)}"
        "<h3>Disruption</h3>"
        f"{table(['Item', 'Total'], disruption)}"
        "<h3>People who gain safe reach, by place type</h3>"
        f"{table(['Place type', 'People'], people)}</section>"
    )


def projects_section(records: list[dict]) -> str:
    rows = [
        [
            record["rank"],
            record["name"],
            f"{record['gain']:.1f}",
            f"{record['score_after']:.1f}",
            f"{sum(record['people'].values()):.0f}",
        ]
        for record in records
    ]
    head = ["Rank", "Project", "Gain", "Score after", "People gaining safe reach"]
    return f'<section id="projects"><h2>Projects, ranked</h2>{table(head, rows)}</section>'


def project_map(record: dict, features: list[dict]) -> str:
    selected = [item for item in features if item["properties"]["project"] == record["id"]]
    points = []
    lines = []
    for feature in selected:
        geometry = feature["geometry"]
        if geometry["type"] == "Point":
            points.append(geometry["coordinates"])
        elif geometry["type"] == "LineString":
            lines.append(geometry["coordinates"])
        elif geometry["type"] == "MultiLineString":
            lines.extend(geometry["coordinates"])
    points.extend(point for line in lines for point in line)
    if not points:
        return ""
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)

    def project(point):
        x = 12 + (point[0] - min_x) / span_x * 576
        y = 128 - (point[1] - min_y) / span_y * 116
        return x, y

    paths = "".join(
        f'<polyline points="{
            html.escape(
                " ".join(f"{project(point)[0]:.2f},{project(point)[1]:.2f}" for point in line),
                quote=True,
            )
        }" '
        'fill="none" stroke="#176b42" stroke-width="5" stroke-linecap="round" '
        'stroke-linejoin="round"/>'
        for line in lines
    )
    dots = "".join(
        f'<circle cx="{project(point)[0]:.2f}" cy="{project(point)[1]:.2f}" r="5" fill="#a33"/>'
        for feature in selected
        if feature["geometry"]["type"] == "Point"
        for point in [feature["geometry"]["coordinates"]]
    )
    return (
        f'<svg class="project-map" id="project-map-{html.escape(record["id"])}" '
        f'data-project-id="{html.escape(record["id"])}" width="600" height="140" '
        'viewBox="0,0,600,140" '
        f'role="img" aria-label="Map of {html.escape(record["name"])}">'
        f"<title>Map of {html.escape(record['name'])}</title>{paths}{dots}</svg>"
        f'<table data-for="project-map-{html.escape(record["id"])}">'
        "<caption>The same map as a table</caption>"
        "<tr><th>Street</th><th>Fix</th></tr>"
        + "".join(
            f"<tr><td><code>{html.escape(str(item['properties']['street']))}</code></td>"
            f"<td><code>{html.escape(item['properties']['fix'])}</code></td></tr>"
            for item in selected
        )
        + "</table>"
    )


def cross_section(project_id: str, element_id: str, item: dict, phase: str) -> str:
    strips = item[phase]
    total = sum(strip["width_m"] for strip in strips)
    cursor = 0.0
    shapes = []
    labels = []
    for strip in strips:
        width = strip["width_m"]
        label = f"{strip['kind']}: {width:.1f} m"
        safe_label = html.escape(label, quote=True)
        if width < 0:
            boundary = max(total, 0.0) * 40
            shapes.append(
                f'<line x1="{boundary:.3f}" y1="0" x2="{boundary:.3f}" y2="32" '
                f'stroke="#a33" stroke-width="2" data-width-m="{width:.1f}" '
                f'data-label="{safe_label}"><title>{safe_label}</title></line>'
            )
        else:
            scaled = width * 40
            shapes.append(
                f'<rect x="{cursor:.3f}" y="2" width="{scaled:.3f}" height="28" '
                f'fill="{STRIP_COLORS.get(strip["kind"], "#bbb")}" '
                f'data-width-m="{width:.1f}" data-label="{safe_label}">'
                f"<title>{safe_label}</title></rect>"
            )
            cursor += scaled
        labels.append(label)
    view_width = max(cursor, total * 40, 1.0)
    drawing_id = html.escape(f"xs-{project_id}-{element_id}-{item['id']}-{phase}", quote=True)
    label_rows = "".join(f"<tr><td><code>{html.escape(label)}</code></td></tr>" for label in labels)
    return (
        '<figure class="cross-section-figure">'
        f"<figcaption>{phase.title()} cross-section</figcaption>"
        f'<svg class="cross-section" id="{drawing_id}" data-project-id="{html.escape(project_id)}" '
        f'data-element-id="{html.escape(element_id)}" '
        f'data-section-id="{html.escape(item["id"])}" data-phase="{phase}" '
        f'data-total-width-m="{total:.1f}" width="{view_width:.3f}" height="32" '
        f'viewBox="0,0,{view_width:.3f},32" '
        'role="img" aria-label="Cross-section drawn to scale">'
        f"<title>{phase.title()} cross-section drawn to scale</title>{''.join(shapes)}</svg>"
        f'<table class="strip-labels" data-for="{drawing_id}">'
        f"<caption>The same strips as a table</caption>{label_rows}</table></figure>"
    )


def check_links(element: dict) -> str:
    links = element["check_links"]
    return (
        '<p class="check-links">Check location: '
        f'<a href="#" data-check-link="{html.escape(links["street_view"], quote=True)}">'
        "Street View</a> · "
        f'<a href="#" data-check-link="{html.escape(links["mapillary"], quote=True)}">'
        "Mapillary</a></p>"
    )


def sheet(record: dict, features: list[dict]) -> str:
    elements = [
        [
            item["id"],
            item["street"],
            item["fix"],
            ROBUST_LABELS.get(item.get("model_margin") or item["robust"], item["robust"]),
            item["width_source"] or "none",
            item.get("source_confidence") or item["width_confidence"] or "none",
            item["length_m"],
        ]
        for item in record["elements"]
    ]
    head = [
        "Element",
        "Street",
        "Fix",
        "Model margin",
        "Width source",
        "Width confidence / Source confidence",
        "Length m",
    ]
    people = [[kind, f"{count:.0f}"] for kind, count in sorted(record["people"].items())]
    disruption = [[label, record["totals"][key]] for key, label in DISRUPTION_LABELS]
    fixes = [[fix, km] for fix, km in sorted(record["totals"]["km_by_fix"].items())]
    drawings = []
    for element in record["elements"]:
        sections = [element] if "before" in element else element["sections"]
        for section in sections:
            source = section["width_source"] or "none"
            confidence = section["width_confidence"] or "none"
            drawings.append(
                f"<h5><code>{html.escape(section['street'])}</code>; width source "
                f"<code>{html.escape(source)}</code>, source confidence "
                f"<code>{html.escape(confidence)}</code></h5>"
                + "".join(
                    cross_section(record["id"], element["id"], section, phase)
                    for phase in ("before", "after")
                )
            )
    sections = "".join(drawings)
    links = "".join(check_links(item) for item in record["elements"])
    return (
        f'<article id="project-{html.escape(record["id"])}">'
        f"<h3>{html.escape(record['name'])}</h3>"
        f"<p>Gain {record['gain']:.1f}. Score after {record['score_after']:.1f}.</p>"
        f"{project_map(record, features)}"
        f"{table(head, elements)}"
        f"<h4>Disruption totals</h4>{table(['Item', 'Total'], disruption)}"
        f"<h4>Kilometres by fix</h4>{table(['Fix', 'km'], fixes or [['none', 0.0]])}"
        f"<h4>Street cross-sections</h4>{sections}{links}"
        f"{table(['Place type', 'People'], people)}</article>"
    )


def sheets_section(records: list[dict], payload: dict) -> str:
    features = payload["project_shapes"]["features"]
    body = "".join(sheet(record, features) for record in records)
    return f'<section id="sheets"><h2>Project sheets</h2>{body}</section>'


def method_section() -> str:
    items = "".join(f"<li>{html.escape(text)}</li>" for text in METHOD)
    return f'<section id="method"><h2>Method</h2><ol>{items}</ol></section>'


def assumptions_section(profile) -> str:
    rows = [
        [name, value, source, "assumption" if assumed else "sourced"]
        for name, value, source, assumed in profile_rows(profile)
    ]
    head = ["Value", "Setting", "Source", "Kind"]
    return (
        '<section id="assumptions"><h2>Profile values and assumptions</h2>'
        f"<p>Rows marked assumption have no published source.</p>{table(head, rows)}</section>"
    )


def credits_section(credits: list[dict]) -> str:
    items = "".join(
        f"<li>{html.escape(item['source'])}, licence {html.escape(item['licence'])}: "
        f"{html.escape(item['line'])}</li>"
        for item in credits
    )
    return f'<section id="credits"><h2>Data credits</h2><ul>{items}</ul></section>'


def rebuild_section(summary: dict) -> str:
    region = summary["region"]
    lines = [
        f"uv run bikeplan snapshot pull snapshots/{region}/{summary['snapshot']}/manifest.json",
        f"uv run bikeplan run regions/{region}.yaml --snapshot data/cache/{region}/"
        f"{summary['snapshot']} --out out",
        "uv run bikeplan verify out",
    ]
    code = html.escape("\n".join(lines))
    return (
        '<section id="rebuild"><h2>Rebuild this report</h2>'
        f"<p>Snapshot {html.escape(summary['snapshot'])}. "
        f"Config hash {html.escape(summary['config_hash'])}.</p>"
        f"<pre>{code}</pre></section>"
    )


def calendar_dates(value, key=""):
    if isinstance(value, dict):
        return {name: calendar_dates(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [calendar_dates(item) for item in value]
    if key == "date" and isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError:
            return value
    return value


def data_block(payload: dict) -> str:
    kept = {name: payload[name] for name in ("project_shapes", "projects", "summary")}
    text = json.dumps(calendar_dates(kept), sort_keys=True).replace("</", "<\\/")
    return f'<script type="application/json" id="page-data">{text}</script>'


def details(summary: dict, records: list[dict], profile, payload: dict) -> str:
    return "".join(
        [
            summary_section(summary),
            projects_section(records),
            sheets_section(records, payload),
            method_section(),
            assumptions_section(profile),
            credits_section(summary["credits"]),
            rebuild_section(summary),
        ]
    )


def page_scripts(payload: dict) -> str:
    return (
        f"{data_block(payload)}"
        "<script>document.querySelectorAll('[data-check-link]').forEach(link => {"
        "link.href = link.dataset.checkLink;});</script>"
    )
