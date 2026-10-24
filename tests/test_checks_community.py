import json
import tarfile
from pathlib import Path

from bikeplan import checks
from bikeplan.checks import run_output_checks
from bikeplan.community_figures import community_figures, delivery_figures
from tests.community_folder import build, tampered

PAGE = '<html><meta name="viewport" content="x"><style>@media print{}</style></html>'


def release(folder: Path, files=None, figures=True, drop=()):
    files = files or build()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bayside-report.html").write_text(PAGE)
    frontier, proposal = files["frontier.json"], files["proposal.json"]
    text = json.dumps(frontier)
    made = community_figures(frontier, proposal, text, 90)
    made += delivery_figures(frontier, proposal, text, 90 + len(made))
    scratch = folder / "scratch"
    scratch.mkdir()
    members = {
        "frontier.json": text,
        "proposal.json": json.dumps(proposal),
        "figures.json": json.dumps(made if figures else []),
    }
    with tarfile.open(folder / "bayside.tar.gz", "w:gz") as tar:
        for name, content in members.items():
            if name in drop:
                continue
            (scratch / name).write_text(content)
            tar.add(scratch / name, arcname=f"./{name}")
    return folder


def test_fr15_8_a_clean_release_passes_the_full_community_check(tmp_path):
    release(tmp_path)
    assert checks.community_release_problems(tmp_path) == []
    assert run_output_checks(tmp_path, ["FR-15.8"]) == {"FR-15.8": []}


def test_fr15_8_a_tampered_route_fails_the_release_check(tmp_path):
    def edit(data):
        data["frontier.json"]["scenarios"][0]["trip_packages"][1]["strict"][0]["edges"] = []

    release(tmp_path, tampered(build(), edit))
    found = checks.community_release_problems(tmp_path)
    assert found
    assert all(line.startswith("bayside") for line in found)


def test_fr15_8_a_missing_frontier_file_fails_instead_of_passing(tmp_path):
    release(tmp_path, drop=("frontier.json",))
    assert any("frontier.json" in line for line in checks.community_release_problems(tmp_path))


def test_fr15_8_no_independent_figures_fail_the_release_check(tmp_path):
    release(tmp_path, figures=False)
    assert any("independent" in line for line in checks.community_release_problems(tmp_path))


def test_fr15_8_a_wrong_figure_value_fails_its_recipe(tmp_path):
    files = build()
    release(tmp_path, files)
    archive = tmp_path / "bayside.tar.gz"
    found = checks.archive_files(archive, ("figures.json", "frontier.json", "proposal.json"))
    figures = json.loads(found["figures.json"])
    figures[0]["value"] += 5
    found["figures.json"] = json.dumps(figures).encode()
    archive.unlink()
    with tarfile.open(archive, "w:gz") as tar:
        for name, content in found.items():
            (tmp_path / "scratch" / name).write_bytes(content)
            tar.add(tmp_path / "scratch" / name, arcname=f"./{name}")
    found = checks.community_release_problems(tmp_path)
    assert any(figures[0]["id"] in line for line in found)
