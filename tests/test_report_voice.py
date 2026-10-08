import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from gates.readability import neutralizer, parse_glossary, score
from tests.test_report import output as _output  # noqa: F401
from tests.test_report import snapshot  # noqa: F401


@pytest.fixture(scope="module")
def report(request):
    return request.getfixturevalue("_output")


SKIP = {"script", "style", "pre", "code", "head"}


class Visible(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.skip = 0
        self.parts = []
        self.ids = {}
        self.stack = []
        self.svgs = []
        self.tags = []
        self.rules = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag in SKIP:
            self.skip += 1
        if tag == "svg":
            self.svgs.append({"title": "", "id": attrs.get("id"), "in_title": False})
        if tag == "title" and self.svgs and self.depth_svg():
            self.svgs[-1]["in_title"] = True
        if tag in {"svg", "section"}:
            self.stack.append((tag, attrs.get("id")))
        if tag == "section" and attrs.get("id"):
            self.ids[attrs["id"]] = []

    def depth_svg(self):
        return any(tag == "svg" for tag, _ in self.stack)

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip -= 1
        if tag == "title" and self.svgs:
            self.svgs[-1]["in_title"] = False
        if tag in {"svg", "section"} and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.svgs and self.svgs[-1]["in_title"]:
            self.svgs[-1]["title"] += data
        if self.skip:
            return
        self.parts.append(data)
        for tag, ident in self.stack:
            if tag == "section" and ident:
                self.ids[ident].append(data)


def parse(output):
    parser = Visible()
    parser.feed((output / "report.html").read_text())
    return parser


def markup(output):
    html = (output / "report.html").read_text()
    assert 'id="map-data"' in html
    return re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.DOTALL)


def words_of(text):
    return re.findall(r"[A-Za-z][A-Za-z'-]*", text)


def test_fr13_4_the_visible_text_passes_the_reading_gate(report):
    text = " ".join(parse(report).parts)
    neutralize = neutralizer([term for term, _ in parse_glossary()])
    passed, message = score("report", text, neutralize, 0, 11)
    assert "skip" not in message
    assert passed, message


def test_fr13_4_each_project_word_in_the_text_has_a_report_glossary_entry(report):
    page = parse(report)
    entries = " ".join(page.ids["report-glossary"])
    assert entries.strip()
    outside = " ".join(
        part
        for ident, part in ((i, " ".join(p)) for i, p in page.ids.items())
        if ident not in {"report-glossary", "appendix"}
    )
    shown = {w.lower() for w in words_of(outside)}
    terms = [term for term, _ in parse_glossary() if term.isalpha()]
    used = [term for term in terms if term.lower() in shown]
    assert used
    for term in used:
        assert re.search(rf"\b{re.escape(term)}\b", entries, re.IGNORECASE), term


def test_fr13_4_the_glossary_comes_after_the_opening_that_uses_its_words(report):
    ids = list(parse(report).ids)
    assert ids.index("report-glossary") > ids.index("opening")


BANNED = [
    line[2:].strip()
    for line in Path("VOICE.md").read_text().split("## Banned words")[1].split("##")[0].splitlines()
    if line.startswith("- ")
]


def test_fr13_5_the_opening_asks_council_in_the_first_person(report):
    text = " ".join(parse(report).ids["opening"])
    assert BANNED
    assert re.search(r"\bI ask council\b", text)
    assert re.search(r"\bI checked\b", text)


def test_fr13_5_no_banned_word_appears_in_the_report(report):
    text = " ".join(parse(report).parts)
    assert "I ask council" in text
    for banned in BANNED:
        pattern = re.escape(banned) if banned == "!" else rf"\b{re.escape(banned)}\b"
        assert not re.search(pattern, text, re.IGNORECASE), banned


def test_fr13_5_the_report_shows_no_phone_email_or_street_address_of_the_author(report):
    page = parse(report)
    assert "Rahul Gurjar, Kogarah" in " ".join(page.parts)
    assert "I ask council" in " ".join(page.parts)
    text = markup(report)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    assert not re.search(
        r"\+?\d[\d ()-]{8,}\d", re.sub(r"\d{4}-\d{2}-\d{2}|[0-9a-f]{64}", "", text)
    )
    assert not re.search(r"\b\d+\s+[A-Z][a-z]+ (Street|St|Road|Rd|Avenue|Ave)\b", text)


def test_fr13_6_the_page_sets_the_viewport_stops_sideways_scroll_and_prints(report):
    html = (report / "report.html").read_text()
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    assert "@media print" in html
    style = re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)
    assert "overflow-x:auto" in style.replace(" ", "")
    assert "overflow-wrap" in style
    assert "max-width" in style


def test_fr13_6_each_svg_has_a_title_and_a_matching_data_table(report):
    page = parse(report)
    assert page.svgs
    for svg in page.svgs:
        assert svg["title"].strip()
        assert svg["id"]
        tables = [
            attrs
            for tag, attrs in page.tags
            if tag == "table" and attrs.get("data-for") == svg["id"]
        ]
        assert len(tables) == 1


def test_fr13_6_each_bar_has_a_text_label_so_colour_is_not_the_only_signal(report):
    html = markup(report)
    svg = re.search(r"<svg.*?</svg>", html, re.DOTALL).group(0)
    bars = re.findall(r"<rect\b", svg)
    labels = re.findall(r"<text\b[^>]*>([^<]+)</text>", svg)
    assert bars
    assert len(labels) >= len(bars)
    assert all(label.strip() for label in labels)
