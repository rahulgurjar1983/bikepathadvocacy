import copy

from bikeplan.checks import measure_lines
from tests.test_checks_sections import blockers_section, release, run
from tests.test_page_measures import release_with
from tests.test_report_page import data_for, page_for, pick


def test_fr19_6_a_region_whose_run_lists_no_corridor_segments_needs_no_section(tmp_path):
    data = {"corridors": {"counts": {}, "segments": []}, "blockers": {"trips": 9}}
    folder = release(tmp_path, page=blockers_section(), data=data, figures=[])
    assert run(folder, "FR-19.6") == []


def test_fr19_6_a_region_with_no_corridors_key_needs_no_section(tmp_path):
    folder = release(tmp_path, page=blockers_section(), data={"blockers": {"trips": 9}})
    assert run(folder, "FR-19.6") == []


def test_fr19_6_a_region_that_lists_segments_still_needs_the_section(tmp_path):
    folder = release(tmp_path, page=blockers_section())
    assert any("corridors section" in line for line in run(folder, "FR-19.6"))


def test_fr20_19_counts_of_a_thousand_or_more_print_with_a_comma(tmp_path):
    big = copy.deepcopy(pick())
    for item in big["steps"]:
        item["totals"]["trips"] = 4043
    big["works"][1]["trips"] = 1234
    text = page_for(data_for(options=[big]))
    lines = measure_lines(release_with(tmp_path / "rel", text))["FR-20.19"]
    broken = [line for line in lines if "plain words broken" in line]
    assert len(broken) == 1 and broken[0].endswith("0 of at most 0, met"), broken
