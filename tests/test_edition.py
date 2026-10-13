import json
import re
import subprocess
import sys

import pytest

from bikeplan import main
from bikeplan.network_report import network_report
from tests.test_network_report import calm, shortest

REGION = "tests/fixtures/test-grid/region.yaml"
SNAPSHOT = "tests/fixtures/test-grid/snapshot"
ORDER = ["options", "map", "chart", "works", "no-fix", "quality", "places", "archive-figures"]


@pytest.fixture(scope="module")
def release(tmp_path_factory):
    out = tmp_path_factory.mktemp("edition")
    assert main(["report", REGION, "--snapshot", SNAPSHOT, "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def figures(release):
    return json.loads((release / "figures.json").read_text())


@pytest.fixture(scope="module")
def page(release):
    return (release / "report.html").read_text()


def option_figures(figures):
    return [item for item in figures if item["spec"] == "spec 17"]


def test_fr17_12_the_report_holds_every_option_number_as_a_figure(figures):
    made = option_figures(figures)
    per_option = 1 + 2 + 1 + 5 + 1
    assert len(made) == 4 * per_option + 7 + 3 * 2
    assert [item["id"] for item in made] == [f"F{n}" for n in range(32, 32 + len(made))]


def test_fr17_12_each_option_recipe_prints_its_value_from_the_release_files(
    release, figures, tmp_path
):
    for name in ("options.json",):
        (tmp_path / name).write_bytes((release / name).read_bytes())
    for item in option_figures(figures):
        shown = subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert float(shown) == pytest.approx(item["value"])


def test_fr17_12_the_figures_name_the_four_options_and_the_pick_step(figures):
    labels = [item["label"] for item in option_figures(figures)]
    for name in ("Calm streets", "Shortest", "Main roads with separation", "Mesh"):
        assert any(label.startswith(f"{name}: length") for label in labels)
    assert "Recommended step of my pick" in labels
    assert "Streets named in my ask" in labels


def test_fr17_12_no_number_in_the_opening_sits_outside_a_figure_link(page):
    opening = re.search(r'<section id="options">.*?</section>', page, re.S)[0]
    bare = re.sub(r"<a [^>]*>.*?</a>", "", opening, flags=re.S)
    assert not re.findall(r"\d", re.sub(r"<[^>]*>", " ", bare))
    assert opening.count('href="#F') == 4 * 9 + 3


def test_fr17_1_the_place_counts_are_figures(release, figures):
    data = json.loads((release / "options.json").read_text())
    counts = {
        item["label"]: item["value"]
        for item in figures
        if item["label"].startswith("Places of type")
    }
    assert counts == {
        f"Places of type {kind}, {state}": data["joined"][kind][state]
        for kind in ("school", "station", "town_centre")
        for state in ("joined", "unjoined")
    }
    assert counts["Places of type school, joined"] == 1


def test_fr17_8_the_page_follows_the_spec_17_order(page):
    spots = [page.index(f'id="{name}"') for name in ORDER]
    assert spots == sorted(spots)
    assert page.index('id="report-glossary"') < page.index('id="appendix"')
    assert page.index('id="archive-figures"') < page.index('id="report-glossary"')


def test_fr17_8_the_old_parts_have_left_the_page(page):
    for name in ("selected-projects", "projects", "sheets", "delivery", "street-plans"):
        assert f'id="{name}"' not in page


def test_fr17_11_the_report_holds_no_survey_text_or_layer(release, page):
    for name in ("report.html", "options.json"):
        assert "survey" not in (release / name).read_text().lower()
    assert "survey_options" not in (release / "map.json").read_text()
    assert "layer-survey" not in page


def test_fr17_8_the_ask_folds_its_streets_below_one_plain_sentence():
    _, body = network_report([calm(), shortest(95.0)], 0.9)
    opening = body.split('id="map"')[0]
    sentence, folded = opening.split("<details>")
    assert "Council adopts Calm streets as its bike network plan" in sentence
    assert "Ash St" not in sentence
    assert "Ash St, Elm St, Oak St" in folded.split("</details>")[0]
