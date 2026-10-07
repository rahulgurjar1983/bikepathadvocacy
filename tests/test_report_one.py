import json
import re

import bikeplan.report
import pytest

from bikeplan import main
from tests.test_report import COMMITTED, REGION


@pytest.fixture(scope="module")
def run_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("one-run")
    assert main(["run", REGION, "--snapshot", str(COMMITTED), "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def report_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("one-report")
    assert main(["report", REGION, "--snapshot", str(COMMITTED), "--out", str(out)]) == 0
    return out


def test_fr13_12_run_and_report_write_the_same_report_bytes(run_out, report_out):
    assert (run_out / "report.html").read_bytes() == (report_out / "report.html").read_bytes()


def test_fr13_12_the_report_lists_the_ranked_projects_with_a_sheet_each(report_out, run_out):
    html = (report_out / "report.html").read_text()
    projects = json.loads((run_out / "projects.json").read_text())
    assert projects
    ranks = [item["rank"] for item in projects]
    assert ranks == sorted(ranks)
    for item in projects:
        assert f'id="project-{item["id"]}"' in html
        assert item["name"] in html


def test_fr13_12_the_report_has_the_summary_method_and_credits_of_the_run(report_out):
    html = (report_out / "report.html").read_text()
    for name in ("summary", "projects", "sheets", "method", "assumptions", "credits", "rebuild"):
        assert f'id="{name}"' in html


def test_fr13_12_the_proposed_changes_switch_is_on_in_the_page(report_out):
    html = (report_out / "report.html").read_text()
    box = re.search(r'<input type="checkbox" id="layer-proposed"([^>]*)>', html)
    assert box
    assert "disabled" not in box.group(1)
    assert 'id="proposed-note"></p>' in html
    data = re.search(r'<script type="application/json" id="map-data">(.*?)</script>', html, re.S)
    assert len(json.loads(data.group(1))["projects"]) == 1


def test_fr13_12_no_list_of_missing_stages_exists():
    assert not hasattr(bikeplan.report, "MISSING_STAGES")
    assert bikeplan.report.has_stage("propose")
    assert not bikeplan.report.has_stage("nothing_here")
