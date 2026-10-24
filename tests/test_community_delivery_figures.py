import json

from bikeplan.community_figures import delivery_figures
from tests.community_folder import build
from tests.test_community_figures import run


def made(files, number=95):
    text = json.dumps(files["frontier.json"])
    return delivery_figures(files["frontier.json"], files["proposal.json"], text, number)


def test_fr16_12_school_stage_and_cost_figures_take_the_next_ids_and_read_only_frontier():
    figures = made(build())
    assert [item["id"] for item in figures] == ["F95", "F96", "F97", "F98"]
    for item in figures:
        assert [i["name"] for i in item["inputs"]] == ["frontier.json"]
        assert "proposal.json" not in item["recipe"]
        assert item["spec"] == "spec 16"


def test_fr16_12_the_values_come_from_routes_stage_records_and_cost_records():
    assert [item["value"] for item in made(build())] == [1, 2, 10, 20]


def test_fr15_8_each_delivery_recipe_prints_its_value_in_a_clean_folder(tmp_path):
    files = build()
    (tmp_path / "frontier.json").write_text(json.dumps(files["frontier.json"]))
    for item in made(files):
        assert run(item["recipe"], tmp_path) == str(item["value"])


def test_fr16_12_a_delivery_recipe_follows_frontier_not_the_saved_proposal(tmp_path):
    files = build()
    figures = made(files)
    frontier = files["frontier.json"]
    frontier["proposal_metadata"]["contents"]["costs"][0]["high"] = 99
    frontier["proposal_metadata"]["contents"]["stages"].pop()
    frontier["scenarios"][0]["trip_packages"][1]["strict"].clear()
    (tmp_path / "frontier.json").write_text(json.dumps(frontier))
    assert [run(item["recipe"], tmp_path) for item in figures] == ["0", "1", "10", "99"]


def test_fr16_12_no_stage_or_cost_records_make_no_stage_or_cost_figure():
    files = build()
    files["frontier.json"]["proposal_metadata"]["contents"] = {"version": 1, "public": True}
    assert [item["id"] for item in made(files)] == ["F95"]


def test_fr16_12_no_school_sites_make_no_school_figure():
    files = build()
    for package in files["frontier.json"]["scenarios"][0]["trip_packages"]:
        del package["school_coverage"]
    assert [item["id"] for item in made(files)] == ["F95", "F96", "F97"]
