import json
import subprocess
import sys

from bikeplan.community_figures import community_figures, community_section
from tests.community_folder import build

LABELS = ["trips", "residents", "roads", "parking"]


def made(files, number=90):
    text = json.dumps(files["frontier.json"])
    return community_figures(files["frontier.json"], files["proposal.json"], text, number)


def run(recipe, folder):
    return subprocess.run(
        [sys.executable, "-I", "-c", recipe],
        cwd=folder,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_fr16_12_four_independent_figures_take_the_next_ids_and_read_only_frontier():
    figures = made(build())
    assert [item["id"] for item in figures] == ["F90", "F91", "F92", "F93"]
    for item in figures:
        assert [i["name"] for i in item["inputs"]] == ["frontier.json"]
        assert "proposal" not in item["recipe"]
        assert item["spec"] == "spec 16"


def test_fr16_12_the_values_come_from_routes_shares_and_the_works_catalog():
    values = [item["value"] for item in made(build())]
    assert values == [2, 150.0, 1, 0]


def test_fr13_3_each_independent_recipe_prints_its_value_in_a_clean_folder(tmp_path):
    files = build()
    (tmp_path / "frontier.json").write_text(json.dumps(files["frontier.json"]))
    for item in made(files):
        assert run(item["recipe"], tmp_path) == str(item["value"])


def test_fr16_12_a_recipe_follows_frontier_not_the_saved_proposal(tmp_path):
    files = build()
    figures = made(files)
    files["frontier.json"]["trip_sources"]["population"]["shares"][0]["people"] = 7.0
    files["frontier.json"]["scenarios"][0]["trip_packages"][1]["strict"].pop()
    (tmp_path / "frontier.json").write_text(json.dumps(files["frontier.json"]))
    assert run(figures[0]["recipe"], tmp_path) == "1"
    assert run(figures[1]["recipe"], tmp_path) == "7.0"


def test_fr16_12_residents_with_no_known_after_count_make_no_residents_figure():
    files = build()
    for package in files["frontier.json"]["scenarios"][0]["trip_packages"]:
        package["resident_outcomes"]["strict"]["unique_residents"]["after"] = None
    assert [item["id"] for item in made(files)] == ["F90", "F91", "F92"]


def test_fr16_12_the_section_links_each_figure_and_shows_every_number_inside_a_link():
    figures = made(build())
    text = community_section(figures)
    for item in figures:
        assert f'href="#{item["id"]}"' in text
    assert 'id="independent-checks"' in text
    assert "<a " in text and "survey" not in text.lower()
