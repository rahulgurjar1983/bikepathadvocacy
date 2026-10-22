import re

import pytest

from bikeplan import checks, main
from tests.test_page_measures import line_of, release_with
from tests.test_report_page import GRID, SNAPSHOT, open_page

IDS = ["FR-20.7", "FR-20.8", "FR-20.19", "FR-20.20", "FR-20.21", "FR-20.22", "FR-20.25"]
HERO = """
const parts = [document.querySelector('h1'), document.getElementById('lede'),
  ...document.querySelectorAll('.hero .tile')];
const map = document.getElementById('plan-map').getBoundingClientRect();
return {
  parts: parts.length,
  below: parts.filter(e => e.getBoundingClientRect().bottom > innerHeight).length,
  mapTop: map.top,
  mapBottom: map.bottom,
  height: innerHeight,
};
"""


@pytest.fixture(scope="module")
def grid_page(tmp_path_factory):
    out = tmp_path_factory.mktemp("w112-run") / "out"
    assert main(["run", GRID, "--snapshot", SNAPSHOT, "--out", str(out)]) == 0
    return (out / "report.html").read_text()


def hero_at(tmp_path, page, width, height, mobile):
    path = tmp_path / "report.html"
    path.write_text(page)
    driver = open_page(path, width)
    try:
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile},
        )
        return driver.execute_script(HERO)
    finally:
        driver.quit()


def measured(tmp_path, name, page):
    return release_with(tmp_path / name, page)


def verdict(release, spec_id, label):
    return line_of(release, spec_id, label).rsplit(", ", 1)[1]


@pytest.mark.parametrize(
    "size", [(390, 844, True), (1440, 900, False)], ids=["390x844", "1440x900"]
)
def test_fr20_8_proof_title_sentence_and_four_numbers_lie_in_the_first_screen(
    grid_page, tmp_path, size
):
    width, height, mobile = size
    got = hero_at(tmp_path, grid_page, width, height, mobile)
    assert got["parts"] == 6
    assert got["below"] == 0


def test_fr20_8_proof_the_map_starts_in_the_first_screen_at_1440_by_900(grid_page, tmp_path):
    got = hero_at(tmp_path, grid_page, 1440, 900, False)
    assert 0 <= got["mapTop"] < got["height"]


def test_fr20_8_proof_the_hero_measures_are_met_on_the_grid_page(grid_page, tmp_path):
    release = measured(tmp_path, "ok", grid_page)
    for size in ("390 by 844", "1440 by 900"):
        label = f"hero parts below the first screen at {size}"
        assert verdict(release, "FR-20.8", label) == "met"
    assert verdict(release, "FR-20.8", "map below the first screen at 1440 by 900") == "met"
    assert verdict(release, "FR-20.8", "hero big numbers missing") == "met"


def test_fr20_8_proof_a_hero_pushed_below_the_first_screen_fails_the_check(grid_page, tmp_path):
    pushed = grid_page.replace(
        "</head>",
        "<style>.hero-grid{margin-top:2000px}</style></head>",
        1,
    )
    release = measured(tmp_path, "pushed", pushed)
    for size in ("390 by 844", "1440 by 900"):
        label = f"hero parts below the first screen at {size}"
        assert verdict(release, "FR-20.8", label) == "fails"
    assert checks.run_output_checks(release, IDS)["FR-20.8"] != []


def test_fr20_19_proof_the_grid_page_text_has_no_banned_word(grid_page, tmp_path):
    release = measured(tmp_path, "ok", grid_page)
    assert verdict(release, "FR-20.19", "plain words broken") == "met"
    assert checks.run_output_checks(release, IDS)["FR-20.19"] == []


@pytest.mark.parametrize("plant", ["some_code_word", "step 4", "unnamed", "3.1416"])
def test_fr20_19_proof_a_planted_word_or_four_figure_decimal_fails_the_check(
    grid_page, tmp_path, plant
):
    bad = grid_page.replace("</main>", f"<p>It is {plant} here.</p></main>", 1)
    assert bad != grid_page
    release = measured(tmp_path, "bad", bad)
    assert verdict(release, "FR-20.19", "plain words broken") == "fails"
    problems = checks.run_output_checks(release, IDS)["FR-20.19"]
    assert any("plain words broken" in item for item in problems)
    assert re.search(plant.split()[0], bad)
