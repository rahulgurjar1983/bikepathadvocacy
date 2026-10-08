import hashlib
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml
from selenium import webdriver

from bikeplan import main
from gates.readability import neutralizer, parse_glossary, score
from tests.route_helpers import SNAPSHOT, densify, lonlat, write_gpx_track
from tests.test_report import REGION as AUTHOR_REGION
from tests.test_report_voice import BANNED, Visible, words_of

CLAIMS = [
    {
        "id": "safe",
        "quote": "Most of the route is safe for all ages.",
        "source": "https://example.org/plan",
        "measure": "aaa_share",
        "op": ">=",
        "value": 0.5,
    },
    {
        "id": "near",
        "quote": "The route runs on the street the whole way.",
        "source": "https://example.org/plan",
        "measure": "matched_share",
        "op": ">=",
        "value": 0.95,
    },
    {
        "id": "meets",
        "quote": "The route is short.",
        "source": "https://example.org/plan",
        "measure": "route_km",
        "op": "<=",
        "value": 5,
    },
    {
        "id": "cost",
        "quote": "It costs little.",
        "source": "https://example.org/plan",
        "outside": "I do not measure cost.",
    },
]
REPLY = {
    "sent": [
        {
            "to": "The plan author",
            "date": "2026-10-02",
            "what": "The full review and the claims table",
        }
    ],
    "replies": [
        {
            "from": "The plan author",
            "date": "2026-10-05",
            "text": "Thank you. The south end is still a draft.",
        }
    ],
}
COLOURS = {"#5aa9e6", "#16407a", "#f08080", "#a01010"}


def review(tmp_path, name, extra=()):
    route = write_gpx_track(
        tmp_path / "r.gpx", lonlat(densify([(0, 0), (400, 0), (400, 400), (700, 400)]))
    )
    claims = tmp_path / "claims.yaml"
    claims.write_text(yaml.safe_dump(CLAIMS))
    out = tmp_path / name
    args = ["review", str(route), "--claims", str(claims), "--region", AUTHOR_REGION]
    assert main([*args, "--snapshot", SNAPSHOT, "--out", str(out), *extra]) == 0
    return out


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    folder = tmp_path_factory.mktemp("review")
    reply = folder / "reply.yaml"
    reply.write_text(yaml.safe_dump(REPLY))
    return review(folder, "out", ["--reply", str(reply)])


@pytest.fixture(scope="module")
def totals(out):
    return json.loads((out / "route_figures.json").read_text())["total"]


def visible(out):
    parser = Visible()
    parser.feed((out / "report.html").read_text())
    return parser


def test_fr14_8_the_review_writes_every_file_and_the_sums_match(out):
    names = [
        "figures.json",
        "report.html",
        "route_figures.json",
        "route_layer.json",
        "verdicts.json",
    ]
    lines = (out / "SHA256SUMS").read_text().splitlines()
    assert [line.split("  ")[1] for line in lines] == names
    for line in lines:
        digest, name = line.split("  ")
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest


def test_fr14_8_each_recipe_prints_its_value_from_the_release_files(out):
    figures = json.loads((out / "figures.json").read_text())
    assert len(figures) > 10
    for item in figures:
        shown = subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=out,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert float(shown) == pytest.approx(item["value"])
        assert "bikeplan" not in item["recipe"]


class Numbers(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.link = False
        self.appendix = False
        self.quote = False
        self.outside = []
        self.links = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.skip += tag in {"head", "script", "style"}
        self.quote = self.quote or tag == "blockquote"
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        self.appendix = self.appendix or attrs.get("id") == "appendix"
        if tag == "a" and attrs.get("href", "").startswith("#F"):
            self.link = True
            self.links.append(attrs["href"][1:])

    def handle_endtag(self, tag):
        self.skip -= tag in {"head", "script", "style"}
        self.link = self.link and tag != "a"
        self.quote = self.quote and tag != "blockquote"

    def handle_data(self, data):
        if not (self.skip or self.link or self.appendix or self.quote):
            self.outside.append(data)


def test_fr14_8_no_number_outside_a_figure_link_the_appendix_or_a_quote(out):
    page = Numbers()
    page.feed((out / "report.html").read_text())
    assert page.links
    assert not re.findall(r"\d", re.sub(r"<time>.*?</time>", "", " ".join(page.outside)))
    for figure_id in set(page.links):
        assert page.ids.count(figure_id) == 1


def test_fr14_8_the_text_passes_the_reading_gate_and_has_no_banned_word(out):
    text = " ".join(visible(out).parts)
    passed, message = score("review", text, neutralizer([t for t, _ in parse_glossary()]), 0, 11)
    assert passed, message
    for banned in BANNED:
        pattern = re.escape(banned) if banned == "!" else rf"\b{re.escape(banned)}\b"
        assert not re.search(pattern, text, re.IGNORECASE), banned


def test_fr14_8_the_review_speaks_as_the_author_and_each_glossary_word_has_an_entry(out):
    page = visible(out)
    assert "Rahul Gurjar, Kogarah" in " ".join(page.parts)
    assert re.search(r"\bI checked\b", " ".join(page.ids["opening"]))
    entries = " ".join(page.ids["report-glossary"])
    outside = " ".join(
        " ".join(p) for i, p in page.ids.items() if i not in {"report-glossary", "appendix"}
    )
    shown = {w.lower() for w in words_of(outside)}
    used = [t for t, _ in parse_glossary() if t.isalpha() and t.lower() in shown]
    assert used
    for term in used:
        assert re.search(rf"\b{re.escape(term)}\b", entries, re.IGNORECASE), term


def test_fr14_8_each_claim_shows_its_quote_source_verdict_and_two_figure_links(out):
    page = visible(out)
    text = " ".join(page.ids["verdicts"])
    for claim in CLAIMS:
        assert claim["quote"] in text
        assert claim["source"] in (out / "report.html").read_text()
    for word in ("does not hold", "partly", "holds", "outside this tool"):
        assert word in text
    verdicts = json.loads((out / "verdicts.json").read_text())
    assert [v["verdict"] for v in verdicts] == [
        "does not hold",
        "partly",
        "holds",
        "outside this tool",
    ]
    links = re.findall(r'href="#(F\d+)"', (out / "report.html").read_text())
    assert len(set(links)) >= 2 * 3


def test_fr14_8_the_verdict_figures_are_the_measured_and_claimed_values(out, totals):
    figures = {i["id"]: i for i in json.loads((out / "figures.json").read_text())}
    html = (out / "report.html").read_text()
    section = re.search(r'<section id="verdicts">.*?</section>', html, re.S).group(0)
    shown = [figures[i] for i in re.findall(r'href="#(F\d+)"', section)]
    measured = round(totals["km_aaa"] / totals["route_km"], 3)
    assert any(f["value"] == measured and "share" in f["unit"] for f in shown)
    assert any(f["value"] == 0.5 for f in shown)


def test_fr14_8_the_right_of_reply_lists_what_was_sent_and_the_reply_in_their_words(out):
    page = visible(out)
    text = " ".join(page.ids["reply"])
    assert "The full review and the claims table" in text
    assert "2 October 2026" in text
    assert "5 October 2026" in text
    html = (out / "report.html").read_text()
    assert "<blockquote>Thank you. The south end is still a draft.</blockquote>" in html
    assert "judge claims" in text


def test_fr14_8_the_right_of_reply_says_so_when_nothing_was_sent(tmp_path):
    out = review(tmp_path, "bare")
    text = " ".join(visible(out).ids["reply"])
    assert "I have not sent this review" in text
    assert "No reply" in text


def test_fr14_8_the_route_layer_holds_matched_and_off_network_lines(out, totals):
    layer = json.loads((out / "route_layer.json").read_text())
    assert {item["lts"] for item in layer["lines"] if not item["off"]} <= {1, 2, 3, 4}
    assert any(item["off"] for item in layer["lines"])
    assert len(layer["breaks"]) == len(totals["breaks"]) > 0
    unsignalised = [c for c in totals["crossings"] if not c["signal"]]
    assert len(layer["crossings"]) == len(unsignalised) == totals["crossings_unsignalised"]


def test_fr14_8_the_review_report_has_the_same_bytes_when_built_twice(out, tmp_path):
    again = review(tmp_path, "again")
    first, second = [(folder / "SHA256SUMS").read_text() for folder in (out, again)]
    assert "report.html" in first
    html = (again / "report.html").read_text()
    assert str(tmp_path) not in html
    assert re.search(r"<time>\d+ \w+ \d{4}</time>", html)
    assert "1 October 2026" in html
    bare = {k: v for k, v in (line.split("  ")[::-1] for line in first.splitlines())}
    assert bare["route_layer.json"] in second


def test_fr14_8_a_missing_author_fails_and_names_the_key(tmp_path, capsys):
    route = write_gpx_track(tmp_path / "r.gpx", lonlat(densify([(0, 0), (200, 0)])))
    claims = tmp_path / "claims.yaml"
    claims.write_text(yaml.safe_dump(CLAIMS))
    code = main(
        [
            "review",
            str(route),
            "--claims",
            str(claims),
            "--region",
            "regions/test-grid.yaml",
            "--snapshot",
            SNAPSHOT,
            "--out",
            str(tmp_path / "o"),
        ]
    )
    assert code == 1
    assert "report.author" in capsys.readouterr().err


def test_fr14_8_an_unknown_measure_fails_and_names_it(tmp_path, capsys):
    route = write_gpx_track(tmp_path / "r.gpx", lonlat(densify([(0, 0), (200, 0)])))
    claims = tmp_path / "claims.yaml"
    claims.write_text(
        yaml.safe_dump(
            [{"id": "x", "quote": "q", "source": "s", "measure": "vibes", "op": ">=", "value": 1}]
        )
    )
    code = main(
        [
            "review",
            str(route),
            "--claims",
            str(claims),
            "--region",
            AUTHOR_REGION,
            "--snapshot",
            SNAPSHOT,
            "--out",
            str(tmp_path / "o"),
        ]
    )
    assert code == 1
    assert "vibes" in capsys.readouterr().err


@pytest.fixture(scope="module")
def browser(out):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.get((Path(out) / "report.html").resolve().as_uri())
    driver.implicitly_wait(5)
    yield driver
    driver.quit()


def paths(browser, name):
    return browser.execute_script(
        "return Array.from(document.querySelectorAll("
        f"'#review-map-canvas svg path.{name}')).map(p => ["
        "p.getAttribute('stroke'), p.getAttribute('stroke-dasharray')])"
    )


def test_fr14_8_the_route_layer_paints_in_the_browser_by_stress_with_off_network_dashed(browser):
    lines = paths(browser, "route-line")
    assert lines
    solid = {stroke for stroke, dash in lines if dash is None}
    assert solid and solid <= COLOURS
    assert any(dash for _, dash in lines if dash is not None)
    assert not [e for e in browser.get_log("browser") if e["level"] == "SEVERE"]


def test_fr14_8_the_map_marks_each_break_and_unsignalised_crossing(browser, totals):
    assert len(paths(browser, "route-break")) == len(totals["breaks"])
    assert len(paths(browser, "route-crossing")) == totals["crossings_unsignalised"]
