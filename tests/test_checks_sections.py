import hashlib
import json
import tarfile
from pathlib import Path

from bikeplan.checks import run_output_checks

NAME = "au-nsw-test"
SEGMENTS = [
    {"id": "T1", "verdict": "covered"},
    {"id": "T2", "verdict": "missed"},
    {"id": "T3", "verdict": None},
]
CORRIDORS = {"counts": {"covered": 1, "partly": 0, "missed": 1}, "segments": SEGMENTS}


def figure(figure_id, spec, digest, expression, value):
    return {
        "id": figure_id,
        "spec": spec,
        "value": value,
        "inputs": [{"name": "options.json", "sha256": digest}],
        "recipe": f"import json;d=json.load(open('options.json'));print({expression})",
    }


def corridor_section(rows="<tr><td>T1</td></tr><tr><td>T2</td></tr><tr><td>T3</td></tr>"):
    return (
        '<section id="corridors"><h2>How my pick fits the TfNSW corridors</h2>'
        '<p>My pick covers <a href="#F1">1</a> of the 3 segments.</p>'
        f"<table><tbody>{rows}</tbody></table></section>"
        '<label><input type="checkbox" id="overlay-corridors"> TfNSW corridors</label>'
    )


def blockers_section(rows='<tr><td>Ash Street</td><td><a href="#F3">9</a></td></tr>'):
    return f'<table id="blockers"><tbody>{rows}</tbody></table><p>The ceiling is not a plan.</p>'


def release(folder: Path, page=None, data=None, figures=None, skew=False):
    folder.mkdir(parents=True, exist_ok=True)
    data = data or {"corridors": CORRIDORS, "blockers": {"trips": 9}}
    raw = json.dumps(data).encode()
    digest = hashlib.sha256(raw).hexdigest()
    if figures is None:
        figures = [
            figure("F1", "spec 19", digest, "d['corridors']['counts']['covered']", 1),
            figure("F3", "spec 17 blockers", digest, "d['blockers']['trips']", 9),
        ]
    if skew:
        figures[0]["inputs"][0]["sha256"] = "0" * 64
    page = page if page is not None else corridor_section() + blockers_section()
    body = f'<main>{page}</main><section id="appendix"></section>'
    (folder / f"{NAME}-report.html").write_text(body)
    files = {"options.json": raw, "figures.json": json.dumps(figures).encode()}
    scratch = folder / "scratch"
    scratch.mkdir(exist_ok=True)
    with tarfile.open(folder / f"{NAME}.tar.gz", "w:gz") as tar:
        for name, content in files.items():
            (scratch / name).write_bytes(content)
            tar.add(scratch / name, arcname=f"./{name}")
    return folder


def run(folder, spec_id):
    return run_output_checks(folder, [spec_id])[spec_id]


def test_fr19_6_a_release_with_the_section_overlay_and_figures_passes(tmp_path):
    assert run(release(tmp_path), "FR-19.6") == []


def test_fr19_6_a_page_without_the_corridors_section_fails(tmp_path):
    folder = release(tmp_path, page=blockers_section())
    assert any("corridors section" in line for line in run(folder, "FR-19.6"))


def test_fr19_6_a_page_without_the_overlay_switch_fails(tmp_path):
    page = corridor_section().replace("overlay-corridors", "other") + blockers_section()
    assert any("overlay" in line for line in run(release(tmp_path, page=page), "FR-19.6"))


def test_fr19_6_a_segment_missing_from_the_table_fails(tmp_path):
    page = corridor_section("<tr><td>T1</td></tr><tr><td>T2</td></tr>") + blockers_section()
    assert any("T3" in line for line in run(release(tmp_path, page=page), "FR-19.6"))


def test_fr19_6_counts_that_disagree_with_the_verdicts_fail(tmp_path):
    counts = {"covered": 2, "partly": 0, "missed": 1}
    data = {"corridors": CORRIDORS | {"counts": counts}, "blockers": {"trips": 9}}
    assert any("counts" in line for line in run(release(tmp_path, data=data), "FR-19.6"))


def test_fr19_6_a_corridor_figure_that_is_not_linked_fails(tmp_path):
    page = corridor_section().replace('<a href="#F1">1</a>', "1") + blockers_section()
    assert any("F1" in line for line in run(release(tmp_path, page=page), "FR-19.6"))


def test_fr19_6_a_corridor_figure_whose_recipe_prints_another_value_fails(tmp_path):
    data = {"corridors": CORRIDORS, "blockers": {"trips": 9}}
    digest = hashlib.sha256(json.dumps(data).encode()).hexdigest()
    figures = [figure("F1", "spec 19", digest, "d['corridors']['counts']['covered']", 5)]
    assert any(
        "F1" in line for line in run(release(tmp_path, data=data, figures=figures), "FR-19.6")
    )


def test_fr19_6_a_figure_that_does_not_match_options_json_fails(tmp_path):
    assert any("hash" in line for line in run(release(tmp_path, skew=True), "FR-19.6"))


def test_fr19_6_a_release_without_corridor_figures_fails(tmp_path):
    figures = [figure("F3", "spec 17 blockers", "0" * 64, "1", 1)]
    assert any("figure" in line for line in run(release(tmp_path, figures=figures), "FR-19.6"))


def test_fr17_14_a_release_with_the_blockers_table_and_figures_passes(tmp_path):
    assert run(release(tmp_path), "FR-17.14") == []


def test_fr17_14_a_page_without_the_blockers_table_fails(tmp_path):
    folder = release(tmp_path, page=corridor_section())
    assert any("blockers table" in line for line in run(folder, "FR-17.14"))


def test_fr17_14_an_empty_blockers_table_fails(tmp_path):
    page = corridor_section() + blockers_section(rows="")
    assert any("no blocker" in line for line in run(release(tmp_path, page=page), "FR-17.14"))


def test_fr17_14_a_page_without_the_ceiling_words_fails(tmp_path):
    page = (corridor_section() + blockers_section()).replace("ceiling", "top")
    assert any("ceiling" in line for line in run(release(tmp_path, page=page), "FR-17.14"))


def test_fr17_14_a_blocker_figure_that_is_not_linked_fails(tmp_path):
    page = corridor_section() + blockers_section(rows="<tr><td>Ash Street</td><td>9</td></tr>")
    assert any("F3" in line for line in run(release(tmp_path, page=page), "FR-17.14"))


def test_fr17_14_a_blocker_figure_whose_recipe_prints_another_value_fails(tmp_path):
    data = {"corridors": CORRIDORS, "blockers": {"trips": 9}}
    digest = hashlib.sha256(json.dumps(data).encode()).hexdigest()
    figures = [figure("F3", "spec 17 blockers", digest, "d['blockers']['trips']", 4)]
    assert any(
        "F3" in line for line in run(release(tmp_path, data=data, figures=figures), "FR-17.14")
    )
