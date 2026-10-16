import json
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

from bikeplan import main
from bikeplan.edition import edition
from tests.test_edition import REGION, SNAPSHOT
from tests.test_network_blockers import FOUR, blocked_option

OLD = [{"id": "F1", "value": 10, "unit": "km", "label": "Street"}]
JOINED = SimpleNamespace(counts={}, unjoined=[])


@pytest.fixture(scope="module")
def made():
    options = [blocked_option(FOUR, ceiling=71.5)]
    _, body, figures, text = edition(None, options, [], JOINED, 0.9, OLD)
    return body, figures, text


def late(figures):
    return [item for item in figures if item["spec"] == "spec 17 blockers"]


def test_fr17_14_each_blocker_value_and_the_ceiling_is_a_figure_after_all_others(made):
    _, figures, _ = made
    ids = [item["id"] for item in figures]
    assert ids == [f"F{n}" for n in range(2, 2 + len(figures))]
    found = late(figures)
    assert [item["id"] for item in found] == ids[-len(found) :]
    labels = " ".join(item["label"] for item in found)
    assert "Ace St" in labels
    assert "ceiling" in labels
    assert len(found) == 4 + 4 + 1


def test_fr17_14_the_figure_values_are_the_blocker_trips_km_and_ceiling(made):
    _, figures, _ = made
    values = {item["label"].split(": ")[1]: item["value"] for item in late(figures)}
    assert values["blocker 1, Ace St, trips it stops"] == 30
    assert values["blocker 4, Dew St, trips it stops"] == 5
    assert values["blocker 2, Bay St, length"] == 0.4
    assert values["safety score if every blocker were fixed too (a ceiling)"] == 71.5


def test_fr17_14_every_blocker_figure_recipe_prints_its_value_from_options_json(made, tmp_path):
    _, figures, text = made
    (tmp_path / "options.json").write_text(text)
    for item in late(figures):
        shown = subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert float(shown) == pytest.approx(item["value"])


def test_fr17_14_the_page_links_resolve_to_the_final_figure_ids(made):
    body, figures, _ = made
    links = set(re.findall(r'href="#([A-Za-z0-9]+)"', body))
    assert not [link for link in links if link.startswith("L")]
    ids = {item["id"] for item in figures} | {"F1"}
    assert links <= ids
    assert {item["id"] for item in late(figures)} <= links


def test_fr17_14_options_json_holds_blockers_and_the_ceiling_of_each_option(made):
    _, _, text = made
    option = json.loads(text)["options"][0]
    assert option["ceiling"] == 71.5
    assert [item["street"] for item in option["blockers"]] == [
        "Ace St",
        "Bay St",
        "Cow St",
        "Dew St",
    ]
    assert set(option["blockers"][0]) == {
        "street",
        "km",
        "road_type",
        "trips",
        "reasons",
        "state",
        "links",
    }


@pytest.fixture(scope="module")
def release(tmp_path_factory):
    out = tmp_path_factory.mktemp("blockers")
    assert main(["report", REGION, "--snapshot", SNAPSHOT, "--out", str(out)]) == 0
    return out


def test_fr17_14_a_built_release_holds_a_ceiling_no_lower_than_the_final_score(release):
    for option in json.loads((release / "options.json").read_text())["options"]:
        assert option["ceiling"] >= option["steps"][-1]["score"] - 1e-9
        assert isinstance(option["blockers"], list)


def test_fr17_14_a_built_page_has_the_blockers_table_and_the_ceiling_label(release):
    page = (release / "report.html").read_text()
    section = page.split('<section id="no-fix">')[1].split("</section>")[0]
    assert '<table id="blockers">' in section
    assert "ceiling, not a plan" in section
