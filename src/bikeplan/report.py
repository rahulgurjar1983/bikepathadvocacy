import csv
import hashlib
import html
import io
import json
from pathlib import Path

from bikeplan.config import ConfigError, Profile, Region
from bikeplan.network import bike_segments
from bikeplan.stress import score_edges
from bikeplan.width import fuse

MISSING_STAGES = ("fit", "access", "propose")
SOURCES = [
    {
        "name": "OpenStreetMap contributors",
        "licence": "ODbL 1.0",
        "request": "network.osm.gz and boundary.geojson in the snapshot folder",
    }
]
HEADER = ["segment_id", "length_m", "lts", "aaa", "width_source"]
FIGURES = [
    (
        "F1",
        "Street a bike may use",
        "spec 03",
        "I add up the length of every street segment inside the boundary where a bike may ride.",
        "True",
    ),
    (
        "F2",
        "Street that is safe for a child to ride alone (AAA)",
        "spec 04",
        "I score each edge for stress and keep the segments where every edge is AAA.",
        "r['aaa'] == '1'",
    ),
    (
        "F3",
        "Street with no width estimate",
        "spec 05",
        "I try each width source in rank order. I count the segments where none gave a width.",
        "r['width_source'] == 'none'",
    ),
]
KEEP = {
    "F1": lambda r: True,
    "F2": lambda r: r["aaa"] == "1",
    "F3": lambda r: r["width_source"] == "none",
}
RECIPE = (
    "import csv;"
    "print(round(sum(float(r['length_m']) for r in csv.DictReader(open('segments.csv')) if {test})"
    "/1000,3))"
)


def segment_rows(graph, profile: Profile) -> list[list]:
    scores = score_edges(graph, profile)
    rows = []
    for segment_id, segment in bike_segments(graph).items():
        keys, datas = zip(*segment["edges"], strict=True)
        found = fuse(datas[0], profile)
        rows.append(
            [
                str(segment_id),
                f"{segment['inside_m']:.3f}",
                max(scores[key]["lts"] for key in keys),
                int(all(scores[key]["aaa"] for key in keys)),
                found["width_source"] or "none",
            ]
        )
    return sorted(rows)


def segments_text(rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buffer.getvalue()


def figure_list(text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text)))
    digest = hashlib.sha256(text.encode()).hexdigest()
    figures = []
    for figure_id, label, spec, method, test in FIGURES:
        km = sum(float(r["length_m"]) for r in rows if KEEP[figure_id](r)) / 1000
        figures.append(
            {
                "id": figure_id,
                "label": label,
                "value": round(km, 3),
                "unit": "km",
                "spec": spec,
                "method": method,
                "inputs": [{"name": "segments.csv", "sha256": digest}],
                "sources": SOURCES,
                "recipe": RECIPE.format(test=test),
            }
        )
    return figures


def link(item: dict) -> str:
    return f'<a href="#{item["id"]}">{item["value"]} {item["unit"]} ({item["id"]})</a>'


def entry(item: dict) -> str:
    inputs = "".join(
        f"<li>{html.escape(part['name'])}, sha256 {part['sha256']}</li>" for part in item["inputs"]
    )
    sources = "".join(
        f"<li>{html.escape(part['name'])}, licence {html.escape(part['licence'])}, "
        f"request: {html.escape(part['request'])}</li>"
        for part in item["sources"]
    )
    return (
        f'<article id="{item["id"]}"><h3>{item["id"]}: {html.escape(item["label"])}</h3>'
        f"<dl><dt>Value</dt><dd>{item['value']} {item['unit']}</dd>"
        f"<dt>Method</dt><dd>{html.escape(item['spec'])}. {html.escape(item['method'])}</dd>"
        f"<dt>Files</dt><dd><ul>{inputs}</ul></dd>"
        f"<dt>Sources</dt><dd><ul>{sources}</ul></dd>"
        "<dt>Recipe: run it with python3 -c in a folder that holds the release files</dt>"
        f"<dd><pre>{html.escape(item['recipe'])}</pre></dd></dl></article>"
    )


def page(region: Region, figures: list[dict]) -> str:
    by_id = {item["id"]: item for item in figures}
    gaps = "".join(
        f"<section><h2>{stage.capitalize()}</h2>"
        f"<p>The {stage} stage is not built yet.</p></section>"
        for stage in MISSING_STAGES
    )
    appendix = "".join(entry(item) for item in figures)
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Bike paths in {html.escape(region.name)}</title></head><body>"
        f"<h1>Bike paths in {html.escape(region.name)}</h1>"
        f"<p>By {html.escape(region.report.author)}</p>"
        f"<section><h2>What the data shows</h2>"
        f"<p>I checked {link(by_id['F1'])} of street that a bike may use. "
        f"{link(by_id['F2'])} of it is safe for a child to ride alone. "
        f"For {link(by_id['F3'])} I have no width.</p></section>"
        f"{gaps}"
        f'<section id="appendix"><h2>How to check every number</h2>{appendix}</section>'
        "</body></html>\n"
    )


def write_report(graph, region: Region, profile: Profile, out) -> list[dict]:
    if region.report.author is None:
        raise ConfigError("report.author is missing: the report needs the name and suburb")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    text = segments_text(segment_rows(graph, profile))
    figures = figure_list(text)
    files = {
        "figures.json": json.dumps(figures, indent=2, sort_keys=True) + "\n",
        "report.html": page(region, figures),
        "segments.csv": text,
    }
    for name, content in files.items():
        (out / name).write_text(content)
    sums = "".join(
        f"{hashlib.sha256(content.encode()).hexdigest()}  {name}\n"
        for name, content in sorted(files.items())
    )
    (out / "SHA256SUMS").write_text(sums)
    return figures
