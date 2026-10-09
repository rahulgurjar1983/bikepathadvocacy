import pytest

from bikeplan.access import Reach, homes
from bikeplan.change import STEP_FIGURES
from bikeplan.propose import curve_picks, csv_row, greedy_picks, planning_network, project_records
from bikeplan.review import ranked_like
from bikeplan.run import project_summary
from tests.test_propose_network import BUSY, PROFILE, REGION
from tests.test_propose_picks import DETOUR, REACH_M, star


def test_fr15_6_new_destinations_union_people_and_types():
    from bikeplan.access import people_gains

    placed = [("school", 10), ("school", 11), ("station", 12)]
    before = [Reach({}, set()), Reach({}, {1}), Reach({}, set())]
    after = [Reach({}, {1, 2}), Reach({}, {1, 2}), Reach({}, {1})]
    found = people_gains({1: 0.4, 2: 0.6}, placed, before, after, ["school", "station"])
    assert found == {
        "unique_people": 1.0,
        "unique_people_by_type": {"school": 1.0, "station": 0.4},
        "gains_by_type": pytest.approx(1.4),
    }


def picks():
    graph = star([(400, BUSY), (800, BUSY)])
    planning = planning_network(graph, PROFILE, REGION)
    found = greedy_picks(
        graph,
        planning,
        [("school", 0), ("school", 0), ("station", 0)],
        {1: 30, 2: 10},
        {"school": 1, "station": 1},
        REGION.proposals,
        REACH_M,
        DETOUR,
    )
    return found, planning


def test_fr15_6_packages_records_curves_exports_and_review_use_same_measures():
    picked, planning = picks()
    records = project_records(picked, planning)
    measures = {
        "unique_people": 40,
        "unique_people_by_type": {"school": 40, "station": 40},
        "gains_by_type": 80,
    }
    assert records[-1]["totals"]["package_access_gains"] == measures
    assert records[0]["totals"]["access_gains"]["unique_people"] == 30
    assert curve_picks(picked, planning)[-1]["unique_people"] == 40
    assert project_summary(records, ["school", "station"])["access_gains"] == measures
    assert ranked_like(records, 2, ["school", "station"])["access_gains"] == measures
    row = csv_row(records[0], ["school", "station"])
    assert row["unique_people"] == 30
    assert row["gains_by_type"] == 60
    figure = next(item for item in STEP_FIGURES if item[0] == "F10")
    assert figure[-1](curve_picks(picked, planning)[-1]) == 40


def test_fr15_6_shared_population_unit_is_allocated_once():
    from bikeplan.access import people_gains
    from shapely.geometry import box

    graph = star([(400, BUSY), (800, BUSY)])
    area = box(-2000, -2000, 2000, 2000)
    resident = homes([{"polygon": area, "people": 90}], graph, area)
    placed = [("school", 10), ("school", 11), ("station", 12)]
    before = [Reach({}, set()) for _ in placed]
    after = [Reach({}, set(resident.people)) for _ in placed]
    found = people_gains(resident.people, placed, before, after, ["school", "station"])
    assert found["unique_people"] == pytest.approx(90)
    assert found["unique_people_by_type"] == pytest.approx({"school": 90, "station": 90})
    assert found["gains_by_type"] == pytest.approx(180)
