import dataclasses
import html
import json
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
METHOD = [
    "The tool reads one snapshot of OpenStreetMap and the other open data named under credits. "
    "It makes no network call.",
    "It builds the street network and gives every street a stress level from 1 to 4 by the "
    "Furth tables. A street is safe for all ages when it meets the AAA rules of the profile.",
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
    return f"<td>{html.escape(str(value))}</td>"


def table(head: list[str], rows: list[list]) -> str:
    top = "".join(f"<th>{html.escape(name)}</th>" for name in head)
    body = "".join(f"<tr>{''.join(cell(value) for value in row)}</tr>" for row in rows)
    return f"<table><thead><tr>{top}</tr></thead><tbody>{body}</tbody></table>"


def summary_section(summary: dict) -> str:
    score = summary["score"]
    fixes = summary["km_by_fix"]
    fix_rows = [[name, f"{km:.3f}"] for name, km in sorted(fixes.items())] or [["none", "0.000"]]
    disruption = [[label, summary["disruption"][key]] for key, label in DISRUPTION_LABELS]
    people = [[kind, f"{count}"] for kind, count in sorted(summary["safe_people_gain"].items())]
    return (
        '<section id="summary"><h2>Summary</h2>'
        f"<p>Access score {score['before']} before and {score['after']} after "
        f"{summary['projects']} projects.</p>"
        "<h3>Kilometres by fix</h3>"
        f"{table(['Fix', 'km'], fix_rows)}"
        "<h3>Disruption</h3>"
        f"{table(['Item', 'Total'], disruption)}"
        "<h3>People who gain safe reach, by place type</h3>"
        f"{table(['Place type', 'People'], people)}</section>"
    )


def map_section() -> str:
    boxes = "".join(
        f'<label><input type="checkbox" id="layer-{name}"{checked}> {text}</label>'
        for name, text, checked in (
            ("lts", "Stress level", " checked"),
            ("aaa", "Safe for all ages", ""),
            ("places", "Places", ""),
            ("projects", "Projects", " checked"),
        )
    )
    return (
        '<section id="map"><h2>Map</h2>'
        f"<fieldset><legend>Layers</legend>{boxes}</fieldset>"
        '<div id="report-map-canvas" style="height: 480px"></div></section>'
    )


def projects_section(records: list[dict]) -> str:
    rows = [
        [
            record["rank"],
            record["name"],
            record["gain"],
            record["score_after"],
            sum(record["people"].values()),
        ]
        for record in records
    ]
    head = ["Rank", "Project", "Gain", "Score after", "People gaining safe reach"]
    return f'<section id="projects"><h2>Projects, ranked</h2>{table(head, rows)}</section>'


def sheet(record: dict) -> str:
    elements = [
        [
            item["id"],
            item["street"],
            item["fix"],
            item["robust"],
            item["width_source"] or "none",
            item["length_m"],
        ]
        for item in record["elements"]
    ]
    head = ["Element", "Street", "Fix", "Robustness", "Width source", "Length m"]
    people = [[kind, count] for kind, count in sorted(record["people"].items())]
    return (
        f'<article id="project-{html.escape(record["id"])}">'
        f"<h3>{html.escape(record['name'])}</h3>"
        f"<p>Gain {record['gain']}. Score after {record['score_after']}.</p>"
        f"{table(head, elements)}"
        f"{table(['Place type', 'People'], people)}</article>"
    )


def sheets_section(records: list[dict]) -> str:
    body = "".join(sheet(record) for record in records)
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


def data_block(payload: dict) -> str:
    text = json.dumps(payload, sort_keys=True).replace("</", "<\\/")
    return f'<script type="application/json" id="page-data">{text}</script>'


def render(summary: dict, records: list[dict], profile, payload: dict) -> str:
    title = html.escape(summary["region"])
    sections = [
        summary_section(summary),
        map_section(),
        projects_section(records),
        sheets_section(records),
        method_section(),
        assumptions_section(profile),
        credits_section(summary["credits"]),
        rebuild_section(summary),
    ]
    head = (
        '<meta charset="utf-8">'
        f"<title>Bike path plan: {title}</title>"
        f"<style>{(ASSETS / 'leaflet.css').read_text()}</style>"
    )
    scripts = (
        f"<script>{(ASSETS / 'leaflet.js').read_text()}</script>"
        f"{data_block(payload)}"
        f"<script>{(ASSETS / 'page_map.js').read_text()}</script>"
    )
    return (
        f'<!DOCTYPE html>\n<html lang="en">\n<head>{head}</head>\n<body>'
        f"<h1>Bike path plan: {title}</h1>{''.join(sections)}{scripts}</body>\n</html>\n"
    )
