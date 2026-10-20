import subprocess
import sys
from types import SimpleNamespace

import pytest

from tests.test_report_page import CHOICE, JOINED, pick
from tests.test_spot_facts import ladder_for


def priced(rates_low=0.8, rates_high=1.3):
    base = pick()
    likely = {0: 1_400_000, 1: 100_000, 2: 1_500_000}
    works = [
        work | {"price": [likely[index] * rates_low, likely[index] * rates_high]}
        for index, work in enumerate(base["works"])
    ]
    return base | {"works": works}


def figures_for(item):
    from bikeplan.edition import options_text
    from bikeplan.report_page import page_figures

    joined = SimpleNamespace(counts=JOINED, unjoined=[])
    text = options_text([item], 0.9, joined)
    return page_figures([item], CHOICE, text, 100), text


def run_recipe(item, text, folder):
    (folder / "options.json").write_text(text)
    return float(
        subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=folder,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )


def test_fr20_3_the_ladder_counts_the_safe_trips_without_its_spots():
    ladder = ladder_for()
    full = ladder["steps"][-1]["totals"]
    assert ladder["no_spots_safe"] < full["safe_trips"]
    assert ladder["no_spots_safe"] == pytest.approx(ladder["no_spots"] / 100 * full["trips"])


def test_fr20_3_the_share_of_trips_made_safe_by_spots_alone_is_a_figure(tmp_path):
    figures, text = figures_for(pick() | {"no_spots_safe": 12})
    found = {item["label"]: item for item in figures}
    share = found["Share of trips made safe by spots alone"]
    assert share["value"] == 35.0
    assert share["unit"] == "%"
    assert run_recipe(share, text, tmp_path) == pytest.approx(35.0)


def test_fr20_3_without_the_safe_trip_count_there_is_no_spots_alone_figure():
    figures, _ = figures_for(pick())
    assert "Share of trips made safe by spots alone" not in {item["label"] for item in figures}


def test_fr20_4_the_stage_cost_figures_hold_the_low_and_high_cost_in_millions(tmp_path):
    figures, text = figures_for(priced())
    found = {item["label"]: item for item in figures}
    want = {
        "Cost of the first stage of my pick, low end": 1.12,
        "Cost of the first stage of my pick, high end": 1.82,
        "Cost of the full plan of my pick, low end": 2.4,
        "Cost of the full plan of my pick, high end": 3.9,
    }
    assert {label: found[label]["value"] for label in want} == want
    for label, value in want.items():
        assert found[label]["unit"] == "$ million"
        assert run_recipe(found[label], text, tmp_path) == pytest.approx(value)


def test_fr20_4_unpriced_works_leave_the_stage_cost_figures_out():
    figures, _ = figures_for(pick())
    assert not [item for item in figures if item["label"].startswith("Cost of")]


def test_fr20_4_price_works_adds_the_low_and_high_cost_of_each_known_fix():
    from bikeplan.cost import load_rates
    from bikeplan.report_page import price_works

    options = [pick() | {"works": pick()["works"] + [{"fix": "mystery", "km": 1.0}]}]
    price_works(options, load_rates())
    prices = [work.get("price") for work in options[0]["works"]]
    assert prices[0] == pytest.approx([1_120_000, 1_820_000])
    assert prices[1] == pytest.approx([80_000, 130_000])
    assert prices[2] == pytest.approx([1_200_000, 1_950_000])
    assert prices[3] is None


def test_fr20_4_options_json_keeps_the_price_of_a_work():
    from bikeplan.edition import option_data

    assert next(work.get("price") for work in option_data(priced())["works"]) == pytest.approx(
        [1_120_000, 1_820_000]
    )
