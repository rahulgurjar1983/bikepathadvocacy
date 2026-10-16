import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from bikeplan import main, profile_lines
from bikeplan.config import load_profile, load_region

REGION = "regions/test-grid.yaml"
COMMITTED = Path("tests/fixtures/test-grid/snapshot")
OSM_CREDIT = "© OpenStreetMap contributors, ODbL 1.0"
SECTIONS = [
    "summary",
    "map",
    "projects",
    "sheets",
    "method",
    "assumptions",
    "credits",
    "rebuild",
]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = {}
        self.tags = []
        self.attributes = []
        self.scripts = []
        self.rows = {}
        self.texts = {}
        self.stack = []
        self.script = None
        self.cross_sections = []
        self.project_maps = []
        self.current_svg = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.tags.append(tag)
        self.attributes.extend((tag, name, value) for name, value in attrs)
        self.stack.append((tag, values.get("id")))
        if "id" in values:
            self.ids[values["id"]] = tag
        if tag == "script":
            self.script = {"attrs": values, "text": ""}
        classes = values.get("class", "").split()
        if tag == "svg" and "cross-section" in classes:
            self.current_svg = {"attrs": values, "strips": []}
        elif tag == "svg" and "project-map" in classes:
            self.project_maps.append(values)
        if tag in {"rect", "line"} and self.current_svg is not None:
            self.current_svg["strips"].append({"tag": tag, **values})
        if tag == "tr":
            for _, section in reversed(self.stack):
                if section in SECTIONS:
                    self.rows[section] = self.rows.get(section, 0) + 1
                    break

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.scripts.append(self.script)
            self.script = None
        if tag == "svg" and self.current_svg is not None:
            self.cross_sections.append(self.current_svg)
            self.current_svg = None
        while self.stack and self.stack[-1][0] != tag:
            self.stack.pop()
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.script is not None:
            self.script["text"] += data
            return
        if any(tag in {"style"} for tag, _ in self.stack):
            return
        for _, section in self.stack:
            if section in SECTIONS:
                self.texts[section] = self.texts.get(section, "") + data


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    target = tmp_path_factory.mktemp("page") / "out"
    args = ["run", REGION, "--snapshot", str(COMMITTED), "--out", str(target)]
    assert main(args) == 0
    return target


@pytest.fixture(scope="module")
def page(out):
    parsed = Page()
    parsed.feed((out / "report.html").read_text())
    return parsed


def test_fr9_3_the_report_has_one_heading_for_each_section(page):
    assert page.tags.count("h1") == 1
    assert page.tags.count("h2") >= len(SECTIONS)


def test_fr9_3_the_pinned_leaflet_build_is_inlined(page):
    source = Path("src/bikeplan/assets/leaflet.js").read_text()
    inline = [item["text"] for item in page.scripts if not item["attrs"]]
    assert any(text.strip() == source.strip() for text in inline)
    assert "Leaflet 1.9.4" in source


def test_fr9_3_the_page_makes_no_network_request(page):
    for tag, name, value in page.attributes:
        if name in {"src", "href", "action"}:
            assert not (value or "").startswith(("http:", "https:", "//")), (tag, name, value)
    assert "link" not in page.tags
    assert "img" not in page.tags
    assert len(page.scripts) >= 3
    assert "map" in page.ids
    assert all("src" not in item["attrs"] for item in page.scripts)


def test_fr9_3_the_method_is_in_plain_words(page):
    text = page.texts["method"]
    for word in ("stress", "width", "access", "project"):
        assert word in text.lower(), word


def test_fr9_3_every_profile_value_is_listed_with_its_source(page):
    region = load_region(REGION)
    profile = load_profile(region.profile)
    lines = list(profile_lines(profile))
    assert page.rows["assumptions"] == len(lines) + 1
    text = page.texts["assumptions"]
    assert text.count("assumption") >= sum("[assumption]" in line for line in lines)
    assert any("[assumption]" in line for line in lines)


def test_fr9_6_the_report_credits_openstreetmap_and_each_source(page, out):
    summary = json.loads((out / "summary.json").read_text())
    text = page.texts["credits"]
    assert OSM_CREDIT in text
    for item in summary["credits"]:
        assert item["source"] in text
        assert item["licence"] in text


def test_fr9_6_the_summary_credits_openstreetmap_with_its_licence(out):
    summary = json.loads((out / "summary.json").read_text())
    lines = [item["line"] for item in summary["credits"]]
    assert OSM_CREDIT in lines
    for item in summary["credits"]:
        assert item["licence"] in item["line"]


def test_nfr7_the_credit_lines_are_in_the_report_and_the_summary(page, out):
    summary = json.loads((out / "summary.json").read_text())
    for item in summary["credits"]:
        assert item["line"] in page.texts["credits"]


def test_fr9_7_the_rebuild_commands_hold_the_snapshot_id_and_config_hash(page, out):
    summary = json.loads((out / "summary.json").read_text())
    text = page.texts["rebuild"]
    assert summary["snapshot"] in text
    assert summary["config_hash"] in text
    for command in ("snapshot pull", "bikeplan run", "bikeplan verify"):
        assert command in text, command


def test_fr9_3_two_runs_give_the_same_page(out, tmp_path):
    again = tmp_path / "again"
    args = ["run", REGION, "--snapshot", str(COMMITTED), "--out", str(again)]
    assert main(args) == 0
    text = (again / "report.html").read_text()
    assert 'id="rebuild"' in text
    assert (again / "report.html").read_bytes() == (out / "report.html").read_bytes()
