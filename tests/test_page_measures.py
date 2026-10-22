import re

import pytest

from bikeplan import checks, main
from tests.test_report_page import data_for, open_page, page_for

NAME = "town"
SPEC = """# Spec 20

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-20.7 | The page holds at most 1,000 words at load. | MUST |
| FR-20.21 | axe-core finds no serious violation. | MUST |
| FR-20.22 | The page stays at most 4 MB and opens offline. | MUST |

| Spec ID | What the tests show |
|---------|---------------------|
| FR-20.7 | Words are counted |
| FR-20.21 | axe-core is run |
| FR-20.22 | Size and requests are measured |
"""
JUNIT = """<testsuites><testsuite>
<testcase classname="tests.t" name="test_fr20_7_a"/>
<testcase classname="tests.t" name="test_fr20_21_a"/>
<testcase classname="tests.t" name="test_fr20_22_a"/>
</testsuite></testsuites>"""
WORDS = (
    "var t=document.querySelector('#plan-map');if(t)t.style.display='none';"
    "document.querySelectorAll('svg').forEach(s=>s.style.display='none');"
    "return document.body.innerText;"
)
IDS = ["FR-20.7", "FR-20.21", "FR-20.22"]


@pytest.fixture(scope="module")
def good_page():
    return page_for(data_for())


def release_with(folder, text):
    folder.mkdir()
    (folder / f"{NAME}-report.html").write_text(text)
    return folder


def line_of(release, spec_id, label):
    lines = checks.measure_lines(release)[spec_id]
    found = [line for line in lines if label in line]
    assert len(found) == 1, lines
    return found[0]


def test_fr20_23_the_words_at_load_are_the_count_a_browser_reads(good_page, tmp_path):
    release = release_with(tmp_path / "rel", good_page)
    driver = open_page(release / f"{NAME}-report.html")
    try:
        text = driver.execute_script(WORDS)
    finally:
        driver.quit()
    counted = len(re.findall(r"[A-Za-z0-9]+", text))
    assert 100 < counted <= 1000
    line = line_of(release, "FR-20.7", "words at load")
    assert line == f"{NAME}-report.html: words at load: {counted:,} of at most 1,000, met"


def test_fr20_23_a_page_over_1000_words_fails_the_words_measure(good_page, tmp_path):
    words = "<p>" + " ".join(["bike"] * 1200) + "</p>"
    release = release_with(tmp_path / "rel", good_page.replace("</body>", words + "</body>"))
    line = line_of(release, "FR-20.7", "words at load")
    assert line.endswith("of at most 1,000, fails")
    problems = checks.run_output_checks(release, IDS)
    assert any("words at load" in item for item in problems["FR-20.7"])
    assert problems["FR-20.21"] == [] and problems["FR-20.22"] == []


def test_fr20_23_the_size_measure_states_bytes_against_4_mb(good_page, tmp_path):
    release = release_with(tmp_path / "rel", good_page)
    size = (release / f"{NAME}-report.html").stat().st_size
    line = line_of(release, "FR-20.22", "page size")
    assert line == f"{NAME}-report.html: page size in bytes: {size:,} of at most 4,194,304, met"


def test_fr20_23_a_page_over_4_mb_fails_the_size_measure(good_page, tmp_path):
    padded = good_page.replace("</body>", "<!--" + "x" * (4 * 1024 * 1024) + "--></body>")
    release = release_with(tmp_path / "rel", padded)
    assert line_of(release, "FR-20.22", "page size").endswith("of at most 4,194,304, fails")
    assert checks.run_output_checks(release, IDS)["FR-20.22"] != []


def test_fr20_23_the_network_measure_counts_requests_at_load(good_page, tmp_path):
    release = release_with(tmp_path / "rel", good_page)
    line = line_of(release, "FR-20.22", "network requests")
    assert line == f"{NAME}-report.html: network requests at load: 0 of at most 0, met"
    leaky = good_page.replace(
        "</body>", '<img src="http://example.com/a.png" alt="x" width="9" height="9"></body>'
    )
    other = release_with(tmp_path / "leaky", leaky)
    assert line_of(other, "FR-20.22", "network requests").endswith("of at most 0, fails")
    assert checks.run_output_checks(other, IDS)["FR-20.22"] != []


def test_fr20_23_the_axe_measure_counts_serious_and_critical_violations_at_load(
    good_page, tmp_path
):
    release = release_with(tmp_path / "rel", good_page)
    line = line_of(release, "FR-20.21", "axe-core")
    assert line == (
        f"{NAME}-report.html: serious or critical axe-core violations at load: 0 of at most 0, met"
    )
    bad = good_page.replace(
        "</body>",
        '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="9" height="9"></body>',
    )
    other = release_with(tmp_path / "bad", bad)
    assert line_of(other, "FR-20.21", "axe-core").endswith("of at most 0, fails")
    assert checks.run_output_checks(other, IDS)["FR-20.21"] != []


def test_fr20_23_checks_html_shows_each_measured_value_and_its_limit(good_page, tmp_path):
    root = tmp_path / "tree"
    (root / "specs").mkdir(parents=True)
    (root / "specs/20-a.md").write_text(SPEC)
    (root / "SPECIFICATION.md").write_text("# Master\n")
    (root / "PROGRESS.md").write_text("")
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT)
    release = release_with(tmp_path / "rel", good_page)
    out = tmp_path / "checks.html"
    code = main(
        ["checks", str(junit), "--root", str(root), "--out", str(out), "--release", str(release)]
    )
    assert code == 0
    text = out.read_text()
    assert re.search(r"words at load: [\d,]+ of at most 1,000, met", text)
    assert "page size in bytes:" in text and "of at most 4,194,304, met" in text
    assert "network requests at load: 0 of at most 0, met" in text
    assert "axe-core violations at load: 0 of at most 0, met" in text
    assert text.count('<p class="status">met</p>') == 3


def test_fr20_23_a_failing_measure_makes_checks_fail(good_page, tmp_path):
    root = tmp_path / "tree"
    (root / "specs").mkdir(parents=True)
    (root / "specs/20-a.md").write_text(SPEC)
    (root / "SPECIFICATION.md").write_text("# Master\n")
    (root / "PROGRESS.md").write_text("")
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT)
    words = "<p>" + " ".join(["bike"] * 1200) + "</p>"
    release = release_with(tmp_path / "rel", good_page.replace("</body>", words + "</body>"))
    out = tmp_path / "checks.html"
    code = main(
        ["checks", str(junit), "--root", str(root), "--out", str(out), "--release", str(release)]
    )
    assert code == 1
    assert "of at most 1,000, fails" in out.read_text()
