import json

import pytest
from bikeplan.community_verify import community_problems

from bikeplan.verify import verify_outputs
from tests.community_folder import build, rehash, tampered, write
from tests.test_run import COMMITTED, run_command


def package(files, rank=1):
    return files["frontier.json"]["scenarios"][0]["trip_packages"][rank]


def catalog(files):
    return files["frontier.json"]["scenarios"][0]["works_catalog"]


def school_set(files):
    package(files)["school_coverage"]["served"]["after"] = []


def school_origins(files):
    package(files)["school_coverage"]["sites"][0]["origins"]["after"] = [0]


def school_reach(files):
    package(files)["school_coverage"]["sites"][0]["resident_reach"]["after"] += 40


def route_break(files):
    package(files)["strict"][0]["outbound"]["edges"][1] = [5, 6, 0]


def route_distance(files):
    package(files)["strict"][0]["return"]["distance_m"] = 1.0


def route_status(files):
    package(files)["strict"][0]["outbound"]["links"][0]["status"] = "unknown"


def route_end(files):
    package(files)["strict"][0]["return"]["edges"].pop()


def resident_total(files):
    package(files)["resident_outcomes"]["strict"]["unique_residents"]["after"] += 100


def resident_member(files):
    package(files)["resident_outcomes"]["strict"]["membership"]["after"].pop()


def resident_double(files):
    members = package(files)["resident_outcomes"]["strict"]["membership"]["after"]
    members.append(dict(members[0]))


def resident_type(files):
    package(files)["resident_outcomes"]["strict"]["by_place_type"]["school"]["after"] = 1.0


def roads(files):
    package(files)["works"]["unique_roads"] += 2


def km(files):
    package(files)["works"]["km_by_design"]["protected_cycleway"] += 0.5


def sections(files):
    package(files)["works"]["sections"].pop()


def parking_total(files):
    package(files)["works"]["parking_spaces"]["removed"]["known_subtotal"] += 3


def parking_row(files):
    catalog(files)["segment:a"]["parking_spaces"]["after"] = 99


def stage_unknown(files):
    files["frontier.json"]["option_sets"]["stage_plan"]["stages"][1]["depends_on"] = ["ghost"]


def stage_cycle(files):
    stages = files["frontier.json"]["option_sets"]["stage_plan"]["stages"]
    stages[0]["depends_on"] = ["two"]


def stage_closure(files):
    files["frontier.json"]["option_sets"]["stage_plan"]["stages"][1]["elements"] = ["segment:b"]


def stage_people(files):
    files["frontier.json"]["option_sets"]["stage_plan"]["stages"][1]["people_gained"] = 1.0


def stage_claim(files):
    files["frontier.json"]["option_sets"]["stage_plan"]["stages"][0]["standalone_access_claim"] = (
        True
    )


def cost_total(files):
    package(files)["delivery"]["costs"]["capital"]["low"] = 1


def cost_budget(files):
    package(files)["delivery"]["costs"]["capital"]["high"] += 5


def source_cost(files):
    files["frontier.json"]["proposal_metadata"]["contents"]["costs"][0]["high"] = 99


def stage_order(files):
    package(files)["delivery"]["stages"][1]["depends_on"] = ["ghost"]


def selected_works(files):
    files["proposal.json"]["selected"]["works"]["unique_roads"] = 9


def selected_cost(files):
    files["proposal.json"]["selected"]["costs"]["capital"]["low"] = 1


def selected_trips(files):
    files["proposal.json"]["selected"]["outcomes"]["strict_complete_trips"] = 7


def selected_residents(files):
    selected = files["proposal.json"]["selected"]
    selected["outcomes"]["resident_outcomes"]["strict"]["unique_residents"]["after"] = 1


CASES = [
    school_set,
    school_origins,
    school_reach,
    route_break,
    route_distance,
    route_status,
    route_end,
    resident_total,
    resident_member,
    resident_double,
    resident_type,
    roads,
    km,
    sections,
    parking_total,
    parking_row,
    stage_unknown,
    stage_cycle,
    stage_closure,
    stage_people,
    stage_claim,
    cost_total,
    cost_budget,
    source_cost,
    stage_order,
    selected_works,
    selected_cost,
    selected_trips,
    selected_residents,
]


def test_fr16_12_untouched_saved_results_pass_every_community_check(tmp_path):
    assert community_problems(write(tmp_path / "out", build())) == []


@pytest.mark.parametrize("edit", CASES, ids=lambda edit: edit.__name__)
def test_fr16_12_a_rehashed_change_to_saved_results_still_fails(tmp_path, edit):
    files = build()
    folder = write(tmp_path / "out", tampered(files, edit))
    assert community_problems(folder)


@pytest.mark.parametrize("name", ["frontier.json", "proposal.json"])
def test_fr16_12_a_missing_output_part_is_a_problem_not_a_pass(tmp_path, name):
    folder = write(tmp_path / "out", build())
    (folder / name).unlink()
    assert any(name in line for line in community_problems(folder))


def test_fr15_7_a_changed_stored_value_with_matching_hashes_names_what_differs(tmp_path):
    files = tampered(build(), roads)
    folder = write(tmp_path / "out", files)
    assert any("unique_roads" in line for line in community_problems(folder))


def test_fr15_7_the_verify_command_runs_the_community_checks_on_a_real_run(tmp_path):
    assert run_command(COMMITTED, tmp_path / "out") == 0
    results = dict(verify_outputs(tmp_path / "out"))
    assert results["community"] == []
    assert all(not found for found in results.values())


def test_fr15_7_the_verify_command_fails_a_rehashed_real_run(tmp_path):
    assert run_command(COMMITTED, tmp_path / "out") == 0
    out = tmp_path / "out"
    data = json.loads((out / "frontier.json").read_text())
    data["scenarios"][0]["trip_packages"][1]["works"]["unique_roads"] += 4
    (out / "frontier.json").write_text(json.dumps(data, indent=2) + "\n")
    rehash(out)
    results = dict(verify_outputs(out))
    assert results["hashes"] == []
    assert results["community"]
