import re

import pytest

from bikeplan import checks, main
from tests.test_page_measures import JUNIT, NAME, good_page, line_of, release_with  # noqa: F401

SPEC_IDS = ["FR-20.7", "FR-20.8", "FR-20.19", "FR-20.20", "FR-20.21", "FR-20.22", "FR-20.25"]


def measured(folder, text):
    return release_with(folder, text)


def met(release, spec_id, label):
    line = line_of(release, spec_id, label)
    assert line.endswith(", met"), line
    return line


def fails(release, spec_id, label):
    line = line_of(release, spec_id, label)
    assert line.endswith(", fails"), line
    assert checks.run_output_checks(release, SPEC_IDS)[spec_id] != []


def test_fr20_23_the_hero_words_are_within_the_title_and_sentence_limits(good_page, tmp_path):
    release = measured(tmp_path / "ok", good_page)
    met(release, "FR-20.8", "words in the title")
    met(release, "FR-20.8", "words in the opening sentence")
    long = good_page.replace("<h1>", "<h1>" + "word " * 12, 1)
    fails(measured(tmp_path / "long", long), "FR-20.8", "words in the title")


def test_fr20_23_the_hero_parts_sit_inside_the_first_screen_at_both_sizes(good_page, tmp_path):
    release = measured(tmp_path / "ok", good_page)
    for size in ("390 by 844", "1440 by 900"):
        met(release, "FR-20.8", f"hero parts below the first screen at {size}")
    met(release, "FR-20.8", "map below the first screen at 1440 by 900")
    met(release, "FR-20.8", "hero big numbers missing")
    pushed = good_page.replace("</head>", "<style>.tiles{margin-top:2000px}</style></head>", 1)
    other = measured(tmp_path / "pushed", pushed)
    fails(other, "FR-20.8", "hero parts below the first screen at 390 by 844")
    fails(other, "FR-20.8", "hero parts below the first screen at 1440 by 900")


@pytest.mark.parametrize(
    "plant", ["step 4", "some_code_word", "unnamed", "LTS", "AAA", "Steiner", "3.14159", "12345"]
)
def test_fr20_23_a_planted_code_word_or_long_number_fails_the_plain_words_measure(
    good_page, tmp_path, plant
):
    met(measured(tmp_path / "ok", good_page), "FR-20.19", "plain words broken")
    bad = good_page.replace("</main>", f"<p>It is {plant} here.</p></main>", 1)
    fails(measured(tmp_path / "bad", bad), "FR-20.19", "plain words broken")


def test_fr20_23_counts_with_commas_and_years_pass_the_plain_words_measure(good_page, tmp_path):
    ok = good_page.replace("</main>", "<p>In 2026 there are 12,345 homes.</p></main>", 1)
    met(measured(tmp_path / "ok", ok), "FR-20.19", "plain words broken")


def test_fr20_23_the_look_measures_hold_for_the_page(good_page, tmp_path):
    release = measured(tmp_path / "ok", good_page)
    met(release, "FR-20.20", "pixels of sideways scroll at 360 px")
    met(release, "FR-20.20", "pixels body text is short of 17")
    met(release, "FR-20.20", "pixels a big number is short of 40 at 390 px")
    met(release, "FR-20.20", "font downloads")
    met(release, "FR-20.20", "pages printed on A4")


def test_fr20_23_a_wide_block_fails_the_sideways_scroll_measure(good_page, tmp_path):
    wide = good_page.replace("</main>", '<div style="width:900px;height:5px"></div></main>', 1)
    fails(measured(tmp_path / "wide", wide), "FR-20.20", "pixels of sideways scroll at 360 px")


def test_fr20_23_a_font_download_and_small_text_fail_the_look_measures(good_page, tmp_path):
    style = "<style>@font-face{font-family:X;src:url(x.woff2)}body{font-size:14px}</style></head>"
    other = measured(tmp_path / "small", good_page.replace("</head>", style, 1))
    fails(other, "FR-20.20", "font downloads")
    fails(other, "FR-20.20", "pixels body text is short of 17")


def test_fr20_23_a_very_long_page_fails_the_print_measure(good_page, tmp_path):
    tall = good_page.replace(
        "</head>", "<style>@media print{main{height:9000px}}</style></head>", 1
    )
    fails(measured(tmp_path / "tall", tall), "FR-20.20", "pages printed on A4")


def test_fr20_23_axe_core_is_run_with_a_place_card_and_a_street_card_open(good_page, tmp_path):
    release = measured(tmp_path / "ok", good_page)
    for card in ("place card", "street card"):
        met(release, "FR-20.21", f"serious or critical axe-core violations with a {card} open")
    faint = "<style>#result.show *{color:#ccc!important}</style></head>"
    other = measured(tmp_path / "faint", good_page.replace("</head>", faint, 1))
    met(other, "FR-20.21", "axe-core violations at load")
    fails(other, "FR-20.21", "serious or critical axe-core violations with a place card open")
    fails(other, "FR-20.21", "serious or critical axe-core violations with a street card open")


def test_fr20_23_every_named_control_is_reached_by_the_tab_key(good_page, tmp_path):
    met(measured(tmp_path / "ok", good_page), "FR-20.21", "named controls the Tab key misses")
    skipped = good_page.replace('id="play"', 'id="play" tabindex="-1"', 1)
    fails(measured(tmp_path / "skip", skipped), "FR-20.21", "named controls the Tab key misses")
    met(measured(tmp_path / "ok2", good_page), "FR-20.21", "focus stops without a visible ring")


def test_fr20_23_sections_out_of_the_mock_order_fail_the_template_measure(good_page, tmp_path):
    met(measured(tmp_path / "ok", good_page), "FR-20.25", "sections out of the mock's order")
    met(measured(tmp_path / "ok2", good_page), "FR-20.25", "unfilled slots")
    swapped = (
        good_page.replace('id="find"', 'id="TMP"', 1)
        .replace('id="streets"', 'id="find"', 1)
        .replace('id="TMP"', 'id="streets"', 1)
    )
    fails(measured(tmp_path / "bad", swapped), "FR-20.25", "sections out of the mock's order")
    slot = good_page.replace("</main>", "<p>{{AREA_FULL}}</p></main>", 1)
    fails(measured(tmp_path / "slot", slot), "FR-20.25", "unfilled slots")


def test_fr20_23_checks_html_lists_the_new_measures_for_every_named_requirement(
    good_page, tmp_path
):
    root = tmp_path / "tree"
    (root / "specs").mkdir(parents=True)
    rows = "".join(f"| {i} | Needs a measure. | MUST |\n" for i in SPEC_IDS)
    cover = "".join(f"| {i} | Measured |\n" for i in SPEC_IDS)
    (root / "specs/20-a.md").write_text(
        f"# Spec 20\n\n| ID | Requirement | Priority |\n|----|---|---|\n{rows}\n"
        f"| Spec ID | What the tests show |\n|---|---|\n{cover}"
    )
    (root / "SPECIFICATION.md").write_text("# Master\n")
    (root / "PROGRESS.md").write_text("")
    cases = "".join(
        f'<testcase classname="t" name="test_fr20_{i[6:].replace(".", "_")}_a"/>' for i in SPEC_IDS
    )
    junit = tmp_path / "junit.xml"
    junit.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
    release = measured(tmp_path / "rel", good_page)
    out = tmp_path / "checks.html"
    code = main(
        ["checks", str(junit), "--root", str(root), "--out", str(out), "--release", str(release)]
    )
    text = out.read_text()
    assert code == 0, re.findall(r"[^<>]*fails[^<>]*", text)[:5]
    assert text.count('<p class="status">met</p>') == len(SPEC_IDS)
