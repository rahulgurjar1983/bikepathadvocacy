import pytest

from tests.test_report_page import data_for, pick, work


def rates():
    from bikeplan.cost import load_rates

    return load_rates()


def test_fr20_4_the_shipped_rates_hold_every_fix_with_its_source_fields():
    found = rates()
    assert (found["low"], found["high"]) == (0.8, 1.3)
    assert found["note"] == "rough cost from 2025 Victorian rates"
    for fix in (
        "quietway",
        "cycleway_in_spare",
        "cycleway_parking_one_side",
        "cycleway_parking_both_sides",
        "road_diet",
        "verge_path",
        "new_path",
        "short_path",
        "raised_zebra",
        "signals",
    ):
        rate = found["rates"][fix]
        assert rate["likely"] > 0
        assert rate["unit"] in ("per_km", "per_spot")
        assert rate["table"].startswith("Table ")


def test_fr20_4_a_work_costs_its_km_times_its_rate():
    from bikeplan.cost import work_cost

    assert work_cost({"fix": "quietway", "km": 2.0}, rates()) == pytest.approx(700000.0)
    assert work_cost({"fix": "road_diet", "km": 0.5}, rates()) == pytest.approx(750000.0)


def test_fr20_4_a_spot_costs_its_crossing_and_a_short_path_adds_its_km():
    from bikeplan.cost import work_cost

    zebra = {"fix": "raised_zebra_crossing", "km": 0.04, "spot": True, "assumed": False}
    signals = {"fix": "bike_walk_signals", "km": 0.05, "spot": True, "assumed": True}
    short = {"fix": "short_path_crossing", "km": 0.05, "spot": True, "assumed": False}
    on_signals = short | {"assumed": True}
    assert work_cost(zebra, rates()) == pytest.approx(100000.0)
    assert work_cost(signals, rates()) == pytest.approx(1500000.0)
    assert work_cost(short, rates()) == pytest.approx(0.05 * 900000 + 100000)
    assert work_cost(on_signals, rates()) == pytest.approx(0.05 * 900000 + 1500000)


def test_fr20_4_a_fix_with_no_rate_has_no_cost():
    from bikeplan.cost import work_cost

    assert work_cost({"fix": "mystery", "km": 1.0}, rates()) is None


def test_fr20_4_the_range_is_minus_20_to_plus_30_percent_rounded_out():
    from bikeplan.cost import stage_cost

    found = stage_cost([{"fix": "quietway", "km": 4.0}], rates())
    assert found["likely"] == pytest.approx(1.4)
    assert (found["low"], found["high"]) == (pytest.approx(1.12), pytest.approx(1.82))
    assert found["text"] == "$1 to 2 million"
    assert found["missing"] == 0


def test_fr20_4_a_missing_rate_says_at_least_and_all_missing_says_not_known():
    from bikeplan.cost import stage_cost

    part = stage_cost([{"fix": "quietway", "km": 4.0}, {"fix": "mystery", "km": 1.0}], rates())
    assert part["text"] == "at least $1 to 2 million"
    assert part["missing"] == 1
    none = stage_cost([{"fix": "mystery", "km": 1.0}], rates())
    assert none["text"] == "cost not known"
    assert none["likely"] == 0.0


def test_fr20_4_no_works_cost_nothing():
    from bikeplan.cost import stage_cost

    assert stage_cost([], rates())["text"] == "$0"


def stages_for(**more):
    return data_for(rates=rates(), **more)["stages"]


def test_fr20_3_each_stage_holds_its_hand_worked_cost_and_counts():
    today, first, full = (stages_for()[key] for key in ("today", "first", "works"))
    assert (today["cost_text"], today["n_works"], today["n_spots"]) == ("$0", 0, 0)
    assert first["cost"] == pytest.approx(1.4)
    assert (first["cost_low"], first["cost_high"]) == (pytest.approx(1.12), pytest.approx(1.82))
    assert (first["cost_text"], first["n_works"], first["n_spots"]) == ("$1 to 2 million", 1, 0)
    assert full["cost"] == pytest.approx(3.0)
    assert full["cost_text"] == "$2 to 4 million"
    assert (full["n_works"], full["n_spots"], full["cost_missing"]) == (1, 2, 0)


def test_fr20_3_a_stage_without_a_rate_says_at_least():
    unknown = pick()
    unknown["works"].append(work("Gum Street", "mystery", 1.0, 0))
    unknown["steps"][3]["works"] = [2, 3]
    data = data_for(options=[unknown], rates=rates())
    assert data["stages"]["works"]["cost_text"] == "at least $2 to 4 million"
    assert data["stages"]["works"]["cost_missing"] == 1
    assert data["stages"]["first"]["cost_missing"] == 0


def test_fr20_4_the_data_holds_the_note_each_work_cost_and_the_spot_cost():
    data = data_for(rates=rates())
    assert data["cost_note"] == "rough cost from 2025 Victorian rates"
    assert [(w["i"], w["cost"]) for w in data["works"]] == [(0, pytest.approx(1.4))]
    assert data["spot_cost"] == pytest.approx(1.6)
