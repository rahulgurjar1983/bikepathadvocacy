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
        f"<li>{html.escape(part['name'])}, sha256 <code>{part['sha256']}</code></li>"
        for part in item["inputs"]
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


STYLE = (
    "body{max-width:48rem;margin:0 auto;padding:0 1rem;font-family:sans-serif;line-height:1.5;"
    "overflow-wrap:anywhere}"
    "pre{overflow-x:auto;white-space:pre-wrap;background:#f4f4f4;padding:.5rem}"
    "table{border-collapse:collapse;max-width:100%}"
    "td,th{border:1px solid #444;padding:.25rem .5rem;text-align:left}"
    "svg{max-width:100%;height:auto}"
    "@media print{body{max-width:none;font-size:11pt}a{color:inherit}"
    "article,table,svg{break-inside:avoid}}"
)
GLOSSARY = {
    "AAA": "All Ages and Abilities: a street that is safe for a child or an older rider.",
    "access": "how many needed places a home can reach by bike.",
    "Bayside": "Bayside Council, a council in the south of Sydney.",
    "bike": "a bicycle, including an electric bicycle.",
    "council": "the local government that runs the streets in an area.",
    "data": "facts and numbers that I read from a file.",
    "width": "how wide a street or lane is, in metres.",
}
BAR_FILLS = ("#1b5e8a", "#2e7d32", "#8a5a00")


def glossary_section(terms: dict[str, str]) -> str:
    items = "".join(
        f"<dt>{html.escape(term)}</dt><dd>{html.escape(meaning)}</dd>"
        for term, meaning in terms.items()
    )
    return f'<section id="report-glossary"><h2>Words I use</h2><dl>{items}</dl></section>'


def chart(figures: list[dict]) -> str:
    top = max(item["value"] for item in figures) or 1
    bars = "".join(
        f'<text x="0" y="{index * 40 + 14}">{html.escape(item["label"])}</text>'
        f'<rect x="0" y="{index * 40 + 20}" width="{item["value"] / top * 100:.1f}%" '
        f'height="14" fill="{BAR_FILLS[index % len(BAR_FILLS)]}"/>'
        for index, item in enumerate(figures)
    )
    rows = "".join(
        f"<tr><td>{html.escape(item['label'])}</td><td>{link(item)}</td></tr>" for item in figures
    )
    return (
        '<section id="chart"><h2>Street length at a glance</h2>'
        f'<svg id="chart-length" role="img" width="100%" height="{len(figures) * 40}" '
        'aria-labelledby="chart-length-title">'
        '<title id="chart-length-title">Bar chart of street length in kilometres for each group'
        f"</title>{bars}</svg>"
        '<table data-for="chart-length"><caption>The same lengths as a table</caption>'
        f"<tr><th>Group</th><th>Length</th></tr>{rows}</table></section>"
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
        f"<title>Bike paths in {html.escape(region.name)}</title>"
        f"<style>{STYLE}</style></head><body>"
        f"<h1>Bike paths in {html.escape(region.name)}</h1>"
        f"<p>By {html.escape(region.report.author)}</p>"
        f'<section id="opening"><h2>What the data shows</h2>'
        f"<p>I checked {link(by_id['F1'])} of street that a bike may use. "
        f"{link(by_id['F2'])} of it is safe for a child to ride alone. "
        f"For {link(by_id['F3'])} I have no width.</p>"
        f"<p>I ask council to measure the street where I have no width. "
        "Please read the appendix to check every number.</p></section>"
        f"{chart(figures)}"
        f"{gaps}"
        f"{glossary_section(GLOSSARY)}"
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
