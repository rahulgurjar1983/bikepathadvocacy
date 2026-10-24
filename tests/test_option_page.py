import json
import re
import subprocess

from tests.test_neighbourhood_wiring import command


def row(name, kind, same, goals, people, parking):
    return {
        "id": name,
        "kind": kind,
        "element_ids": ["segment:a"],
        "identical_to": same,
        "parking_spaces": parking,
        "people": people,
        "trip_count": 2,
        "label": "candidate",
        "goals": goals,
    }


def frontier():
    return {
        "default": "shipped",
        "option_sets": {
            "stage_plan": {"valid": True, "problems": [], "stages": [{"id": "s1"}, {"id": "s2"}]},
            "comparison": {
                "options": [],
                "unbuilt": {"parking_retention": "No complete trip forms from the picks"},
            },
            "options": [
                row(
                    "first_stage",
                    "first_stage",
                    None,
                    [{"id": "g1", "status": "unmet", "reason": "no_complete_trip"}],
                    120.0,
                    3,
                ),
                row(
                    "broader_network",
                    "broader_network",
                    "first_stage",
                    [{"id": "g1", "status": "met", "reason": None}],
                    120.0,
                    3,
                ),
            ],
        },
    }


def test_fr16_9_page_lists_each_option_with_label_goal_result_and_twin():
    from bikeplan.option_page import option_section

    text = option_section(frontier(), 70)
    assert text.startswith('<section id="option-comparison">')
    assert re.findall(r'<li data-option-id="([^"]+)"', text) == ["first_stage", "broader_network"]
    assert "candidate" in text
    assert "no complete trip" in text
    assert 'data-goal-status="unmet"' in text and 'data-goal-status="met"' in text
    assert "same works as" in text
    assert "No complete trip forms from the picks" in text
    assert 'href="#F70"' in text and 'href="#F72"' in text and 'href="#F73"' in text


def test_fr16_9_page_without_option_sets_says_unknown_and_has_no_figures():
    from bikeplan.option_page import option_figures, option_section

    bare = {"default": "shipped"}
    assert "unknown" in option_section(bare, 70)
    assert option_figures(bare, "{}", 70) == []


def test_fr16_9_figures_recompute_from_the_saved_frontier(tmp_path):
    from bikeplan.option_page import option_figures

    (tmp_path / "frontier.json").write_text(json.dumps(frontier()))
    figures = option_figures(frontier(), (tmp_path / "frontier.json").read_text(), 70)
    assert [f["id"] for f in figures] == ["F70", "F71", "F72", "F73", "F74", "F75"]
    assert [f["value"] for f in figures] == [2, 1, 120.0, 3, 120.0, 3]
    for figure in figures:
        done = subprocess.run(
            ["python3", "-c", figure["recipe"]],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert float(done.stdout) == figure["value"]


def test_fr16_9_the_full_run_keeps_option_sets_and_shows_the_section(tmp_path):
    out = command("run", tmp_path)
    saved = json.loads((out / "frontier.json").read_text())
    assert "option_sets" in saved
    page = (out / "report.html").read_text()
    assert page.count('id="option-comparison"') == 1
    section = page[page.index('id="option-comparison"') :]
    assert "No complete trip forms from the picks" in section
    linked = set(re.findall(r'href="#(F\d+)"', section[: section.index("</section>")]))
    assert linked
    for figure in linked:
        assert f'id="{figure}"' in page
