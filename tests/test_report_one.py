import importlib

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


def test_fr13_12_no_list_of_missing_stages_exists():
    report = importlib.import_module("bikeplan.report")
    assert not hasattr(report, "MISSING_STAGES")
    assert report.has_stage("propose")
    assert not report.has_stage("nothing_here")
