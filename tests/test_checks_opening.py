import json
import tarfile
from pathlib import Path

import pytest

from bikeplan import main
from bikeplan.checks import opening_problems, run_output_checks
from bikeplan.config import load_region
from bikeplan.edition import edition, edition_page
from bikeplan.options import Joined
from tests.test_checks import entries, status_of
from tests.test_network_report import calm, option, shortest

REGION = "tests/fixtures/test-grid/region.yaml"
NAME = "town"
SPEC = """# Spec 17

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-17.11 | The report holds no survey. | MUST |
| FR-17.12 | The opening is made of figures. | MUST |

| Spec ID | What the tests show |
|---------|---------------------|
| FR-17.11 | No survey text |
| FR-17.12 | Every opening figure is met |
"""
JUNIT = """<testsuites><testsuite>
<testcase classname="tests.t" name="test_fr17_11_a"/>
<testcase classname="tests.t" name="test_fr17_12_a"/>
</testsuite></testsuites>"""
OLD = {
    "id": "F1",
    "label": "Street with no width estimate",
    "value": 1.5,
    "unit": "km",
    "spec": "spec 05",
    "method": "I count.",
    "inputs": [{"name": "segments.csv", "sha256": "0"}],
    "sources": [],
    "recipe": "print(1.5)",
}


def options_four():
    main_roads = option(
        "Main roads", [0, 30, 70, 90], [0, 3, 6, 9], ["Bay St", "Fir St", "Gum St"], no_fix=[]
    )
    mesh = option("Mesh", [0, 20, 40, 60], [0, 2, 4, 6], ["Ash St", "Bay St", "Cox St"])
    return [calm(), shortest(95.0), main_roads, mesh]


def make_release(folder: Path, options=None, edit=None):
    options = options or options_four()
    region = load_region(REGION)
    joined = Joined(
        [],
        [{"id": "node/9", "type": "school", "name": "Far School", "reason": "no bike route"}],
        {
            "school": {"joined": 3, "unjoined": 1},
            "station": {"joined": 2, "unjoined": 0},
            "town_centre": {"joined": 1, "unjoined": 0},
        },
    )
    head, body, made, text = edition(region, options, [], joined, 0.9, [OLD])
    figures = [OLD, *made]
    page = edition_page(region, head, body, figures, "")
    files = {
        "figures.json": json.dumps(figures, indent=2, sort_keys=True),
        "options.json": text,
    }
    if edit:
        page, files = edit(page, files)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{NAME}-report.html").write_text(page)
    scratch = folder / "scratch"
    scratch.mkdir()
    with tarfile.open(folder / f"{NAME}.tar.gz", "w:gz") as tar:
        for name, content in files.items():
            (scratch / name).write_text(content)
            tar.add(scratch / name, arcname=f"./{name}")
    return made


def test_fr17_12_a_release_with_matching_figures_has_no_problem(tmp_path):
    made = make_release(tmp_path)
    assert len(made) > 40
    assert opening_problems(tmp_path) == []


def test_fr17_12_a_changed_option_file_fails_the_hash_and_the_recipes(tmp_path):
    def edit(page, files):
        data = json.loads(files["options.json"])
        data["options"][0]["km"] = 99.0
        return page, {**files, "options.json": json.dumps(data)}

    make_release(tmp_path, edit=edit)
    problems = opening_problems(tmp_path)
    assert any("does not match its hash" in line for line in problems)


def test_fr17_12_a_changed_figure_value_fails_its_recipe_even_with_the_hash_right(tmp_path):
    def edit(page, files):
        figures = json.loads(files["figures.json"])
        figures[1]["value"] += 1
        return page, {**files, "figures.json": json.dumps(figures)}

    make_release(tmp_path, edit=edit)
    problems = opening_problems(tmp_path)
    assert any("its recipe does not print" in line for line in problems)
    assert not any("hash" in line for line in problems)


def test_fr17_12_a_bare_number_in_the_opening_fails(tmp_path):
    def edit(page, files):
        return page.replace("<p>My pick:", "<p>Cost 12 dollars. My pick:", 1), files

    make_release(tmp_path, edit=edit)
    assert any("not a figure link" in line for line in opening_problems(tmp_path))


def test_fr17_12_a_missing_option_in_the_opening_fails(tmp_path):
    def edit(page, files):
        return page.replace("<td>Mesh", "<td>Other", 1), files

    make_release(tmp_path, edit=edit)
    assert any("does not list Mesh" in line for line in opening_problems(tmp_path))


def test_fr17_12_no_option_with_a_gain_fails_and_says_so(tmp_path):
    flat = [
        option(name, [10, 10], [0, 0], ["Ash St"]) for name in ("Calm", "Short", "Main", "Mesh")
    ]
    make_release(tmp_path, options=flat)
    assert any("no option gains safety" in line for line in opening_problems(tmp_path))


def test_fr17_12_a_release_with_no_option_file_fails_hard(tmp_path):
    (tmp_path / "town-report.html").write_text("<html></html>")
    assert opening_problems(tmp_path) == ["no region report in the release holds options.json"]


def test_fr17_11_a_survey_word_in_a_region_report_fails(tmp_path):
    def edit(page, files):
        return page.replace("<h1>", "<p>Survey the roads</p><h1>", 1), files

    make_release(tmp_path, edit=edit)
    found = run_output_checks(tmp_path, ["FR-17.11"])
    assert found["FR-17.11"] == [f"{NAME}-report.html: the word survey is in the page"]


def test_fr17_11_a_report_without_the_word_has_no_problem(tmp_path):
    make_release(tmp_path)
    assert run_output_checks(tmp_path, ["FR-17.11"]) == {"FR-17.11": []}


@pytest.fixture
def spec_tree(tmp_path):
    root = tmp_path / "tree"
    (root / "specs").mkdir(parents=True)
    (root / "specs/17-x.md").write_text(SPEC)
    (root / "SPECIFICATION.md").write_text("# Master\n")
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT)
    return root, junit, tmp_path / "checks.html", tmp_path / "release"


def run_checks(tree):
    root, junit, out, release = tree
    return main(
        ["checks", str(junit), "--root", str(root), "--out", str(out), "--release", str(release)]
    )


def test_fr13_14_an_opening_that_matches_the_release_shows_met(spec_tree):
    make_release(spec_tree[3])
    assert run_checks(spec_tree) == 0
    found = entries(spec_tree[2])
    assert status_of(found["FR-17.12"]) == "met"
    assert status_of(found["FR-17.11"]) == "met"
    assert "town-report.html" in found["FR-17.12"]


def test_fr13_14_an_opening_that_does_not_match_shows_fails(spec_tree, capsys):
    def edit(page, files):
        data = json.loads(files["options.json"])
        data["options"][1]["km"] = 7.0
        return page, {**files, "options.json": json.dumps(data)}

    make_release(spec_tree[3], edit=edit)
    assert run_checks(spec_tree) == 1
    assert status_of(entries(spec_tree[2])["FR-17.12"]) == "fails"
    assert "FR-17.12" in capsys.readouterr().err
