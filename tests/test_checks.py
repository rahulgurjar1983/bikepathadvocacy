import json
import re
from pathlib import Path

import pytest

from bikeplan import main
from gates import ledger
from tests.test_release import (  # noqa: F401
    bp_calls,
    calls,
    repo,
    run_script,
)

ROOT = Path(__file__).resolve().parent.parent
SPEC = """# Spec 01

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | The tool does a thing. | MUST |
| FR-1.2 | The tool does another thing. | MUST |
| FR-1.3 | The tool does a third thing, as FR-1.1 does. | SHOULD |
| FR-1.4 | The tool does a fourth thing. | MUST |

| Spec ID | What the tests show |
|---------|---------------------|
| FR-1.1 | The thing is done once |
| FR-1.2 | The other thing is done twice |
"""
JUNIT = """<testsuites><testsuite>
<testcase classname="tests.t" name="test_fr1_1_does_it"/>
<testcase classname="tests.t" name="test_fr1_1_does_it_again"/>
<testcase classname="tests.t" name="test_fr1_2_does_it"><failure message="boom"/></testcase>
<testcase classname="tests.t" name="test_fr1_3_does_it"><skipped message="no"/></testcase>
<testcase classname="tests.t" name="test_fr11_4_other"/>
</testsuite></testsuites>"""


@pytest.fixture
def release(request):
    return request.getfixturevalue("repo")


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "tree"
    (root / "specs").mkdir(parents=True)
    (root / "specs/01-a.md").write_text(SPEC)
    (root / "SPECIFICATION.md").write_text("# Master\n")
    (root / "PROGRESS.md").write_text("- [x] **P1.1** Does things (FR-1.1)\n")
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT)
    figures = tmp_path / "figures.json"
    figures.write_text(json.dumps([{"id": "F1", "label": "Km of road", "spec": "spec 01"}]))
    return root, junit, figures, tmp_path / "checks.html"


def build(tree):
    _, junit, figures, out = tree
    argv = ["checks", str(junit), "--root", str(tree[0]), "--figures", str(figures)]
    return main([*argv, "--out", str(out)]), out


def entries(out):
    text = out.read_text()
    parts = re.split(r'<section class="check" id="', text)[1:]
    return {part.split('"', 1)[0]: part for part in parts}


def status_of(entry):
    return re.search(r'<p class="status">([^<]*)</p>', entry).group(1)


def test_fr13_11_every_spec_id_in_the_repo_has_an_entry(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text("<testsuites/>")
    figures = tmp_path / "figures.json"
    figures.write_text("[]")
    out = tmp_path / "checks.html"
    code = main(
        ["checks", str(junit), "--root", str(ROOT), "--figures", str(figures), "--out", str(out)]
    )
    wanted = set()
    for path in [ROOT / "SPECIFICATION.md", *sorted((ROOT / "specs").glob("*.md"))]:
        wanted.update(ledger.SPEC_ID.findall(path.read_text()))
    assert code == 0
    assert len(wanted) > 150
    assert set(entries(out)) == wanted


def test_fr13_11_status_comes_from_the_test_run_not_from_progress(tree):
    code, out = build(tree)
    found = entries(out)
    assert status_of(found["FR-1.1"]) == "met"
    assert status_of(found["FR-1.2"]) == "fails"
    assert status_of(found["FR-1.3"]) == "fails"
    assert status_of(found["FR-1.4"]) == "not built yet"
    assert code == 1


def test_fr13_11_a_run_with_no_failing_check_exits_zero(tree):
    junit = tree[1]
    junit.write_text(
        JUNIT.split('<testcase classname="tests.t" name="test_fr1_2')[0]
        + "</testsuite></testsuites>"
    )
    code, out = build(tree)
    assert code == 0
    assert status_of(entries(out)["FR-1.1"]) == "met"


def test_fr13_11_a_planted_failing_check_shows_fails_and_fails_the_command(tree, capsys):
    code, out = build(tree)
    assert code == 1
    assert "FR-1.2" in capsys.readouterr().err
    assert "fails" in entries(out)["FR-1.2"]


def test_fr13_11_a_spec_id_with_no_entry_fails(tree, capsys):
    root = tree[0]
    (root / "specs/02-b.md").write_text("A rule that cites FR-9.9 and NFR-4 with no row.\n")
    code, _ = build(tree)
    err = capsys.readouterr().err
    assert code == 1
    assert "FR-9.9" in err and "NFR-4" in err


def test_fr13_11_each_entry_has_every_field(tree):
    _, out = build(tree)
    entry = entries(out)["FR-1.1"]
    for label in [
        "In plain words",
        "Status in this release",
        "See it in the report",
        "Check it with no tools",
        "Check it with commands",
        "What you should see",
        "This release's own result",
    ]:
        assert f"<dt>{label}</dt>" in entry
    assert "The tool does a thing." in entry
    assert "The thing is done once" in entry
    assert "test_fr1_1_" in entry
    assert "uv run pytest" in entry
    assert "2 passed, 0 failed" in entry
    assert "P1.1" in entry


def test_fr13_11_the_entry_points_at_the_figures_of_its_spec(tree):
    _, out = build(tree)
    assert "F1" in entries(out)["FR-1.1"]
    assert "Km of road" in entries(out)["FR-1.1"]


def test_fr13_11_the_page_is_the_same_bytes_on_every_build(tree):
    _, out = build(tree)
    first = out.read_bytes()
    out.unlink()
    build(tree)
    assert out.read_bytes() == first


def test_fr13_11_the_page_has_a_viewport_and_counts_by_status(tree):
    _, out = build(tree)
    text = out.read_text()
    assert '<meta name="viewport"' in text
    assert "1 met, 2 fail, 1 not built yet" in text


def test_fr13_11_a_missing_results_file_fails_hard(tree, capsys):
    tree[1].unlink()
    code, out = build(tree)
    assert code == 1
    assert not out.exists()
    assert "junit.xml" in capsys.readouterr().err


def test_fr13_11_the_release_runs_the_tests_and_uploads_checks_html(release):
    work, source, bin_dir = release
    result = run_script(work, source, bin_dir, "v2026.10.07", BP_REAL="1")
    assert result.returncode == 0, result.stderr[-2000:]
    log = (bin_dir.parent / "pytest.log").read_text()
    assert "--junitxml=" in log
    checks = [c for c in bp_calls(bin_dir) if c[0] == "checks"]
    assert len(checks) == 1
    upload = next(c for c in calls(bin_dir) if c[:2] == ["release", "upload"])
    assert any(a.endswith("checks.html") for a in upload)
    sums = (bin_dir.parent / "out/SHA256SUMS").read_text()
    assert "  checks.html" in sums


def test_fr13_11_a_failing_check_fails_the_release_script_and_uploads_nothing(release):
    work, source, bin_dir = release
    result = run_script(work, source, bin_dir, "v2026.10.07", BP_FAIL_CHECKS="1")
    assert result.returncode != 0
    assert not [c for c in calls(bin_dir) if c[:2] == ["release", "upload"]]


def test_fr13_11_a_failing_test_run_still_builds_the_page_then_fails_the_release(release):
    work, source, bin_dir = release
    result = run_script(work, source, bin_dir, "v2026.10.07", PYTEST_EXIT="1")
    assert [c for c in bp_calls(bin_dir) if c[0] == "checks"]
    assert result.returncode != 0
    assert not [c for c in calls(bin_dir) if c[:2] == ["release", "upload"]]
