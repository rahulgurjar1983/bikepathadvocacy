import json
import re
import subprocess

from tests.test_neighbourhood_wiring import TWO_AREAS, command, supplied


def built(tmp_path, areas=TWO_AREAS):
    inputs = supplied(tmp_path, areas) if areas else None
    return command("run", tmp_path, inputs)


def test_fr16_8_page_section_shows_each_area_with_benefits_impacts_and_work_links(tmp_path):
    from bikeplan.neighbourhood_view import neighbourhood_section

    out = built(tmp_path)
    proposal = json.loads((out / "proposal.json").read_text())
    text = neighbourhood_section(proposal, "F90", "F91")
    assert text.startswith('<section id="neighbourhoods">')
    rows = re.findall(r'<div data-area-id="([^"]+)" data-pattern="([^"]+)"', text)
    areas = proposal["selected"]["local_areas"]["areas"]
    assert rows == [(a["id"], a["pattern"]) for a in areas]
    works = [k for a in areas for k in a["works"]["parking_element_ids"]]
    assert works
    for key in works:
        assert f'data-work-id="{key}"' in text
    assert 'href="#physical-works"' in text
    assert 'href="#F90"' in text and 'href="#F91"' in text
    assert "not the sum of the areas" in text


def test_fr16_8_page_section_without_boundaries_says_unknown_and_has_no_figures(tmp_path):
    from bikeplan.neighbourhood_view import neighbourhood_figures, neighbourhood_section

    out = built(tmp_path, None)
    proposal = json.loads((out / "proposal.json").read_text())
    assert proposal["selected"]["local_areas"] is None
    text = neighbourhood_section(proposal, "F90", "F91")
    assert "No sourced area boundaries" in text
    assert "data-area-id" not in text
    assert neighbourhood_figures(proposal, (out / "proposal.json").read_bytes(), 90) == []


def test_fr16_8_unallocated_works_are_listed_not_hidden(tmp_path):
    from bikeplan.neighbourhood_view import neighbourhood_section

    far = [
        dict(
            TWO_AREAS[0],
            id="far",
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [[150.0, -33.0], [150.1, -33.0], [150.1, -32.9], [150.0, -32.9], [150.0, -33.0]]
                ],
            },
        )
    ]
    out = built(tmp_path, far)
    proposal = json.loads((out / "proposal.json").read_text())
    loose = proposal["selected"]["local_areas"]["unallocated"]["works"]
    assert loose
    text = neighbourhood_section(proposal, "F90", "F91")
    for item in loose:
        assert f'data-unallocated-id="{item["id"]}"' in text


def test_fr16_8_figures_recompute_from_the_saved_proposal(tmp_path):
    from bikeplan.neighbourhood_view import neighbourhood_figures

    out = built(tmp_path)
    blob = (out / "proposal.json").read_bytes()
    proposal = json.loads(blob)
    figures = neighbourhood_figures(proposal, blob, 90)
    assert [f["id"] for f in figures] == ["F90", "F91"]
    region = proposal["selected"]["local_areas"]["region"]["residents"]
    assert figures[0]["value"] == region["located_newly_gained"]
    assert figures[1]["value"] == len(proposal["selected"]["local_areas"]["unallocated"]["works"])
    for figure in figures:
        done = subprocess.run(
            ["python3", "-c", figure["recipe"]],
            cwd=out,
            capture_output=True,
            text=True,
            check=True,
        )
        assert float(done.stdout) == figure["value"]


def test_fr16_8_the_full_run_page_carries_the_section_and_its_figures(tmp_path):
    out = built(tmp_path)
    page = (out / "report.html").read_text()
    assert page.count('id="neighbourhoods"') == 1
    ids = re.findall(r'<div data-area-id="([^"]+)"', page)
    assert ids == ["east", "west"]
    section = page[page.index('id="neighbourhoods"') :]
    linked = re.findall(r'href="#(F\d+)"', section)
    assert len(set(linked)) >= 2
    for figure in set(linked):
        assert f'id="{figure}"' in page
