import hashlib
import json
import shutil

import pytest

from bikeplan import main
from tests.test_run import COMMITTED, run_command


@pytest.fixture(scope="module")
def good(tmp_path_factory):
    folder = tmp_path_factory.mktemp("good") / "out"
    assert run_command(COMMITTED, folder) == 0
    return folder


@pytest.fixture
def copy(good, tmp_path):
    folder = tmp_path / "out"
    shutil.copytree(good, folder)
    return folder


def edit(folder, name, change):
    path = folder / name
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def reseal(folder):
    lines = []
    for path in sorted(folder.iterdir()):
        if path.name != "outputs.sha256":
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (folder / "outputs.sha256").write_text("".join(lines))


def failures(folder, capsys):
    code = main(["verify", str(folder)])
    captured = capsys.readouterr()
    failed = [line for line in captured.err.splitlines() if line.startswith("fail ")]
    return code, failed, captured.out


def test_fr9_5_verify_prints_each_check_and_passes_good_outputs(copy, capsys):
    code, failed, out = failures(copy, capsys)
    assert code == 0
    assert failed == []
    names = [line.split()[1] for line in out.splitlines() if line.startswith("ok ")]
    assert names == [
        "hashes",
        "aaa_after",
        "margins",
        "scores",
        "score_order",
        "project_totals",
        "summary_totals",
        "projects",
    ]


def test_fr9_5_verify_fails_a_changed_byte(copy, capsys):
    with (copy / "report.html").open("ab") as handle:
        handle.write(b" ")
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert [line.split()[1].rstrip(":") for line in failed] == ["hashes"]
    assert "report.html" in failed[0]


def test_fr9_5_verify_fails_a_missing_hash_file(copy, capsys):
    (copy / "outputs.sha256").unlink()
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert failed


def test_fr9_5_verify_fails_an_element_left_at_lts_2(copy, capsys):
    edit(copy, "projects.json", lambda data: data[0]["elements"][0].update(aaa_after=False))
    reseal(copy)
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert [line.split()[1].rstrip(":") for line in failed] == ["aaa_after"]


def test_fr9_5_verify_fails_a_negative_margin(copy, capsys):
    edit(copy, "projects.json", lambda data: data[0]["elements"][0].update(margin_m=-0.2))
    reseal(copy)
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert [line.split()[1].rstrip(":") for line in failed] == ["margins"]


def test_fr9_5_verify_fails_a_score_of_101(copy, capsys):
    edit(copy, "summary.json", lambda data: data["score"].update(after=101.0))
    reseal(copy)
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert "scores" in [line.split()[1].rstrip(":") for line in failed]


def test_fr9_5_verify_fails_a_project_that_lowers_the_score(copy, capsys):
    edit(copy, "projects.json", lambda data: data[0].update(score_after=1.0))
    reseal(copy)
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert [line.split()[1].rstrip(":") for line in failed] == ["score_order"]


def test_fr9_5_verify_fails_a_project_total_that_is_not_the_sum(copy, capsys):
    edit(copy, "projects.json", lambda data: data[0]["totals"].update(signals=5))
    reseal(copy)
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert "project_totals" in [line.split()[1].rstrip(":") for line in failed]


def test_fr9_5_verify_fails_a_summary_total_that_is_not_the_sum(copy, capsys):
    edit(copy, "summary.json", lambda data: data["disruption"].update(signals=7))
    reseal(copy)
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert [line.split()[1].rstrip(":") for line in failed] == ["summary_totals"]


def test_fr9_5_verify_fails_candidates_with_no_project(copy, capsys):
    def clear(data):
        data["candidates"] = 4
        data["projects"] = 0
        data["score"]["after"] = data["score"]["before"]
        data["km_by_fix"] = {}
        data["projects_by_kind"] = dict.fromkeys(data["projects_by_kind"], 0)
        data["disruption"] = dict.fromkeys(data["disruption"], 0)
        data["safe_people_gain"] = dict.fromkeys(data["safe_people_gain"], 0)

    edit(copy, "summary.json", clear)
    edit(copy, "projects.json", lambda data: data.clear())
    reseal(copy)
    code, failed, _ = failures(copy, capsys)
    assert code == 1
    assert [line.split()[1].rstrip(":") for line in failed] == ["projects"]
    assert "no project" in failed[0]


def test_fr9_5_run_records_margin_and_aaa_for_each_element(good):
    projects = json.loads((good / "projects.json").read_text())
    for element in (item for project in projects for item in project["elements"]):
        assert element["aaa_after"] is True
        assert "margin_m" in element
