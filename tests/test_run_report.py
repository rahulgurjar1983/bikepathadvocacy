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

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.tags.append(tag)
        self.attributes.extend((tag, name, value) for name, value in attrs)
        self.stack.append((tag, values.get("id")))
        if "id" in values:
            self.ids[values["id"]] = tag
        if tag == "script":
            self.script = {"attrs": values, "text": ""}
        if tag == "tr":
            for _, section in reversed(self.stack):
                if section in SECTIONS:
                    self.rows[section] = self.rows.get(section, 0) + 1
                    break

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.scripts.append(self.script)
            self.script = None
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


def test_fr9_3_the_report_holds_each_section(page):
    for name in SECTIONS:
        assert page.ids.get(name) == "section", name


def test_fr9_3_the_report_has_one_heading_for_each_section(page):
    assert page.tags.count("h1") == 1
    assert page.tags.count("h2") >= len(SECTIONS)


def test_fr9_3_the_summary_gives_the_scores_and_totals(page):
    text = page.texts["summary"]
    assert "25.0" in text
    assert "100.0" in text
    assert "Signals" in text
    assert "750" in text


def test_fr9_3_the_data_is_inlined_as_json(page, out):
    blocks = [item for item in page.scripts if item["attrs"].get("type") == "application/json"]
    assert blocks
    data = json.loads(blocks[0]["text"])
    summary = json.loads((out / "summary.json").read_text())
    assert data["summary"] == summary
    assert len(data["projects"]) == 1
    assert data["network"]["type"] == "FeatureCollection"
    assert data["places"]["type"] == "FeatureCollection"
    assert data["project_shapes"]["type"] == "FeatureCollection"


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
    assert all("src" not in item["attrs"] for item in page.scripts)


def test_fr9_3_the_map_has_a_layer_control_for_each_layer(page):
    for name in ("lts", "aaa", "places", "projects"):
        assert page.ids.get(f"layer-{name}") == "input", name
    assert page.ids.get("report-map-canvas") == "div"


def test_fr9_3_the_project_table_has_a_row_for_each_project(page, out):
    projects = json.loads((out / "projects.json").read_text())
    assert page.rows["projects"] == len(projects) + 1


def test_fr9_3_each_project_has_a_sheet(page, out):
    projects = json.loads((out / "projects.json").read_text())
    for project in projects:
        assert page.ids.get(f"project-{project['id']}") == "article"
        assert project["name"] in page.texts["sheets"]


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
    assert (again / "report.html").read_bytes() == (out / "report.html").read_bytes()
