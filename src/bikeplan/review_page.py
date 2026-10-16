import hashlib
import html
import json
import math
from pathlib import Path

from bikeplan.config import ConfigError
from bikeplan.report import STYLE
from bikeplan.review_report import day, read_reply, reply_section

HEAD = "import json;v=json.load(open('verdicts.json'));"
VERDICT_NAMES = ("holds", "partly", "does not hold", "outside this tool")
PALETTE = ("#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9", "#444444")
MAP_WIDTH = 800
MAP_PAD = 10


class Figures:
    def __init__(self, verdicts: list, digest: str):
        self.verdicts = verdicts
        self.digest = digest
        self.items: list[dict] = []

    def add(self, label: str, expression: str, method: str) -> dict:
        value = round(eval(expression, {"len": len, "sum": sum}, {"v": self.verdicts}), 3)
        item = {
            "id": f"F{len(self.items) + 1}",
            "label": label,
            "value": value,
            "method": method,
            "recipe": f"{HEAD}print(round({expression},3))",
        }
        self.items.append(item)
        return item


def figure_link(item: dict) -> str:
    return f'<a href="#{item["id"]}">{item["value"]}</a>'


def entry(item: dict, digest: str) -> str:
    return (
        f'<article id="{item["id"]}"><h3>{item["id"]}: {html.escape(item["label"])}</h3>'
        f"<dl><dt>Value</dt><dd>{item['value']}</dd>"
        f"<dt>How I worked</dt><dd>{html.escape(item['method'])}</dd>"
        f"<dt>Input</dt><dd><code>verdicts.json</code>, sha256 <code>{digest}</code></dd>"
        f"<dt>How to check</dt><dd><pre>{html.escape(item['recipe'])}</pre></dd></dl></article>"
    )


def claim_row(figures: Figures, index: int, found: dict) -> str:
    quote = html.escape(found["quote"], quote=False)
    source = html.escape(found["source"])
    if "measure" in found:
        measured = figures.add(
            f"Measured value for: {found['measure']}",
            f"v[{index}]['measured']",
            "I measure the plan with the method of its measure and read the result.",
        )
        claimed = figures.add(
            f"Value that the claim names for: {found['measure']}",
            f"v[{index}]['claimed']",
            "I read the value from the claims file.",
        )
        what = (
            f"{html.escape(found['measure'])}: I measured {figure_link(measured)}. "
            f"The claim says {html.escape(found['op'])} {figure_link(claimed)}."
        )
    else:
        what = f"I do not measure this: {html.escape(found['reason'], quote=False)}"
    return (
        f"<tr><td><blockquote>{quote}</blockquote></td>"
        f'<td><a href="{source}">{source}</a></td>'
        f"<td><strong>{html.escape(found['verdict'])}</strong></td><td>{what}</td></tr>"
    )


def parts(geometry: dict) -> list:
    if geometry["type"] == "LineString":
        return [geometry["coordinates"]]
    return geometry["coordinates"]


def map_section(lines: dict) -> str:
    drawn = [
        (feature["properties"]["layer"], part)
        for feature in lines["features"]
        for part in parts(feature["geometry"])
    ]
    points = [point for _, part in drawn for point in part]
    west = min(x for x, _ in points)
    east = max(x for x, _ in points)
    south = min(y for _, y in points)
    north = max(y for _, y in points)
    scale = (MAP_WIDTH - 2 * MAP_PAD) / max(
        (east - west) * math.cos(math.radians((north + south) / 2)), 1e-9
    )
    stretch = math.cos(math.radians((north + south) / 2)) * scale
    height = round((north - south) * scale + 2 * MAP_PAD)
    names = sorted({name for name, _ in drawn})
    colours = {name: PALETTE[index % len(PALETTE)] for index, name in enumerate(names)}

    def place(point: list) -> str:
        x = MAP_PAD + (point[0] - west) * stretch
        y = MAP_PAD + (north - point[1]) * scale
        return f"{x:.1f} {y:.1f}"

    paths = "".join(
        f'<path d="M{"L".join(place(point) for point in part)}" stroke="{colours[name]}" '
        'fill="none" stroke-width="2"/>'
        for name, part in drawn
    )
    key = "".join(
        f'<li><span style="color:{colours[name]}">&#9632;</span> {html.escape(name)}</li>'
        for name in names
    )
    return (
        '<section id="map"><h2>Where the plan runs in the review area</h2>'
        f'<svg id="route-map" role="img" aria-label="Map of the plan in the review area, north up" '
        f'viewBox="0 0 {MAP_WIDTH} {height}" width="100%">{paths}</svg>'
        f'<ul id="route-map-key">{key}</ul></section>'
    )


def window_section(window: dict) -> str:
    if window["public_after"]:
        text = (
            f"<p>I sent this review on {day(window['sent'])}. "
            f"It stays private for {window['window_days']} days, until "
            f"{day(window['public_after'])}.</p>"
        )
    else:
        text = (
            f"<p>The review stays private. The {window['window_days']} days for a reply "
            "start on the day that I send it.</p>"
        )
    return f'<section id="window"><h2>When this review can go public</h2>{text}</section>'


def build_page(
    verdicts: list,
    window: dict,
    reply: dict,
    manifest: dict,
    digest: str,
    lines: dict | None = None,
) -> str:
    figures = Figures(verdicts, digest)
    judged = figures.add("Claims that I judge", "len(v)", "I count the claims in the claims file.")
    counts = [
        figures.add(
            f"Claims with the verdict: {name}",
            f"sum(x['verdict']=='{name}' for x in v)",
            "I count the claims that have this verdict.",
        )
        for name in VERDICT_NAMES
    ]
    rows = "".join(claim_row(figures, index, found) for index, found in enumerate(verdicts))
    count_text = ", ".join(
        f"{figure_link(item)} {html.escape(name)}"
        for name, item in zip(VERDICT_NAMES, counts, strict=True)
    )
    appendix = "".join(entry(item, digest) for item in figures.items)
    credit = html.escape(manifest["attribution"], quote=False)
    licence = html.escape(manifest["licence"])
    url = html.escape(manifest["url"])
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Private review of a plan</title><style>{STYLE}</style></head><body>"
        "<h1>Private review of a plan</h1>"
        '<section id="opening"><h2>What the data shows</h2>'
        f"<p>I judge {figure_link(judged)} claims: {count_text}.</p>"
        f'<p>Source: <a href="{url}">{url}</a>, saved on '
        f"{html.escape(manifest['retrieved_at'][:10])}. Licence {licence}. Credit: {credit}.</p>"
        "</section>"
        f"{map_section(lines) if lines else ''}"
        '<section id="verdicts"><h2>What I found for each claim</h2>'
        "<table><tr><th>The claim</th><th>Where it was said</th><th>Verdict</th>"
        f"<th>What I measured</th></tr>{rows}</table></section>"
        f"{window_section(window)}{reply_section(reply)}"
        '<section id="appendix"><h2>How to check every number</h2>'
        f"{appendix}</section></body></html>\n"
    )


def write_page(folder, source_manifest, reply, out, lines=None) -> Path:
    private = Path.cwd() / "data/private"
    target = Path(out).absolute()
    if not target.is_relative_to(private) or not target.resolve().is_relative_to(private):
        raise ConfigError("The review page must stay under data/private")
    if target.exists():
        raise ConfigError(f"{target}: already exists; use a new page folder")
    drawing = None
    if lines:
        found = Path(lines).absolute()
        if not found.is_relative_to(private) or not found.resolve().is_relative_to(private):
            raise ConfigError("The lines file must stay under data/private")
        drawing = json.loads(found.read_text())
    source = Path(folder)
    content = (source / "verdicts.json").read_bytes()
    verdicts = json.loads(content)
    window = json.loads((source / "reply-window.json").read_text())
    manifest = json.loads(Path(source_manifest).read_text())
    text = build_page(
        verdicts, window, read_reply(reply), manifest, hashlib.sha256(content).hexdigest(), drawing
    )
    target.mkdir(parents=True)
    (target / "index.html").write_text(text)
    return target
