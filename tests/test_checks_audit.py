import copy
import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path

import pytest

from bikeplan import checks, main
from bikeplan.checks import run_output_checks
from bikeplan.config import load_region
from bikeplan.edition import edition, edition_page
from bikeplan.options import Joined
from tests.test_checks_opening import NAME, OLD, REGION, options_four
from tests.test_network_report import option

BOUNDARY = "POLYGON ((0 0, 1000 0, 1000 1000, 0 1000, 0 0))"
PLACES = [
    {"id": "node/1", "name": "Ash School", "type": "school", "x": 100.0, "y": 100.0},
    {"id": "node/2", "name": "Bay Station", "type": "station", "x": 900.0, "y": 900.0},
]


def audit(**changes):
    base = {
        "crs": "EPSG:3857",
        "boundary": BOUNDARY,
        "buffer_m": 200.0,
        "max_trip_km": 5.0,
        "longest_trip_m": 4200.0,
        "places": copy.deepcopy(PLACES),
    }
    return base | changes


def with_geometry(options):
    found = copy.deepcopy(options)
    for item in found:
        item["links"] = [[100.0, 100.0, 500.0, 100.0], [500.0, 100.0, 900.0, 900.0]]
        for work in item["works"]:
            work["least"] = work["score"]
    return found


def make_release(folder: Path, options=None, data=None, edit=None):
    options = with_geometry(options or options_four())
    region = load_region(REGION)
    joined = Joined([], [], {"school": {"joined": 1, "unjoined": 0}})._replace(
        audit=data or audit()
    )
    head, body, made, text = edition(region, options, [], joined, 0.9, [OLD])
    figures = [OLD, *made]
    page = edition_page(region, head, body, figures, "")
    files = {"figures.json": json.dumps(figures), "options.json": text}
    if edit:
        page, files = edit(page, files)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{NAME}-report.html").write_text(page)
    scratch = folder / "scratch"
    scratch.mkdir()
    with tarfile.open(folder / f"{NAME}.tar.gz", "w:gz") as tar:
        for name, content in files.items():
            (scratch / name).write_text(content)
            tar.add(scratch / name, arcname=f"./{name}")
    return text


def edit_data(change):
    def edit(page, files):
        data = json.loads(files["options.json"])
        change(data)
        return page, {**files, "options.json": json.dumps(data)}

    return edit


def edit_ask(names):
    def edit(page, files):
        found = re.search(r"<details><summary>.*?<p>.*?</p></details>", page, re.S)[0]
        return page.replace(found, f"<details><p>{names}</p></details>", 1), files

    return edit


def test_fr17_15_a_clean_build_passes_every_check(tmp_path):
    make_release(tmp_path)
    assert checks.audit_problems(tmp_path) == []
    assert run_output_checks(tmp_path, ["FR-17.15"]) == {"FR-17.15": []}


def test_fr17_15_a_place_outside_the_boundary_fails_and_is_named(tmp_path):
    def change(data):
        data["audit"]["places"][1].update(x=2500.0, name="Far Station")

    make_release(tmp_path, edit=edit_data(change))
    found = checks.audit_problems(tmp_path)
    assert len(found) == 1
    assert "Far Station" in found[0]
    assert "outside the boundary" in found[0]


def test_fr17_15_a_link_beyond_the_widened_boundary_fails_and_a_link_inside_it_passes(tmp_path):
    def inside(data):
        data["options"][2]["links"].append([1100.0, 500.0, 1190.0, 500.0])

    make_release(tmp_path / "inside", edit=edit_data(inside))
    assert checks.audit_problems(tmp_path / "inside") == []

    def beyond(data):
        data["options"][2]["links"].append([1100.0, 500.0, 1300.0, 500.0])

    make_release(tmp_path / "beyond", edit=edit_data(beyond))
    found = checks.audit_problems(tmp_path / "beyond")
    assert len(found) == 1
    assert "Main roads" in found[0]
    assert "link" in found[0]


def test_fr17_15_an_unnamed_street_in_the_ask_fails(tmp_path):
    make_release(tmp_path, edit=edit_ask("Ash St, unnamed service road, Oak St"))
    found = checks.audit_problems(tmp_path)
    assert any("unnamed service road" in line and "unnamed" in line for line in found)


def test_fr17_15_a_street_with_no_work_up_to_the_step_fails(tmp_path):
    make_release(tmp_path, edit=edit_ask("Ash St, Elm St, Zed St"))
    found = checks.audit_problems(tmp_path)
    assert len(found) == 1
    assert "Zed St" in found[0]


def test_fr17_15_the_eleventh_street_in_the_ask_fails(tmp_path):
    streets = [f"Street {letter}" for letter in "ABCDEFGHIJKL"]
    scores = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 100]
    spends = [0, *range(1, 13)]
    big = option("Calm streets", scores, spends, streets)
    rest = options_four()[1:]
    make_release(tmp_path / "clean", options=[big, *rest])
    assert checks.audit_problems(tmp_path / "clean") == []
    make_release(tmp_path / "plant", options=[big, *rest], edit=edit_ask(", ".join(streets[:11])))
    found = checks.audit_problems(tmp_path / "plant")
    assert len(found) == 1
    assert "11 streets" in found[0]


def test_fr17_15_a_six_kilometre_trip_fails(tmp_path):
    def change(data):
        data["audit"]["longest_trip_m"] = 6000.0

    make_release(tmp_path, edit=edit_data(change))
    found = checks.audit_problems(tmp_path)
    assert len(found) == 1
    assert "6.0 km" in found[0]


def test_fr17_15_parking_removed_where_a_cheaper_fix_fits_fails_but_a_dearer_one_passes(tmp_path):
    def cheaper(data):
        data["options"][3]["works"][1]["least"] = 0.5

    make_release(tmp_path / "cheaper", edit=edit_data(cheaper))
    found = checks.audit_problems(tmp_path / "cheaper")
    assert len(found) == 1
    assert "Mesh" in found[0]
    assert "Bay St" in found[0]

    def dearer(data):
        data["options"][3]["works"][1]["least"] = 99.0

    make_release(tmp_path / "dearer", edit=edit_data(dearer))
    assert checks.audit_problems(tmp_path / "dearer") == []


def test_fr17_15_a_work_that_removes_no_parking_is_not_judged(tmp_path):
    def change(data):
        work = data["options"][3]["works"][1]
        work.update(parking_spaces=0, least=0.0)

    make_release(tmp_path, edit=edit_data(change))
    assert checks.audit_problems(tmp_path) == []


def test_fr17_15_a_release_without_audit_data_fails_hard(tmp_path):
    def change(data):
        del data["audit"]

    make_release(tmp_path, edit=edit_data(change))
    assert checks.audit_problems(tmp_path) == [f"{NAME}: options.json holds no audit data"]


def test_fr17_15_the_checks_page_shows_fails_and_the_first_wrong_item(tmp_path):
    def change(data):
        data["audit"]["places"][0].update(x=-50.0, name="Wet School")

    make_release(tmp_path / "rel", edit=edit_data(change))
    found = run_output_checks(tmp_path / "rel", ["FR-17.15"])
    assert "Wet School" in found["FR-17.15"][0]


SNAPSHOT = Path("tests/fixtures/test-grid/snapshot")
EXTRA = [
    (3001, -33.9500021, 151.1499977, {"amenity": "school", "name": "West School"}),
    (3002, -33.9446909, 151.1566043, {"amenity": "school", "name": "East School"}),
    (3003, -33.9464289, 151.152239, {"railway": "station", "name": "Mid Station"}),
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = tmp_path_factory.mktemp("audit") / "snapshot"
    shutil.copytree(SNAPSHOT, folder)
    places = json.loads((folder / "places.json").read_text())
    for number, lat, lon, tags in EXTRA:
        places["elements"].append(
            {"type": "node", "id": number, "lat": lat, "lon": lon, "tags": tags}
        )
    content = json.dumps(places).encode()
    (folder / "places.json").write_bytes(content)
    manifest = json.loads((folder / "manifest.json").read_text())
    entry = next(item for item in manifest["files"] if item["name"] == "places.json")
    entry.update(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    out = tmp_path_factory.mktemp("built")
    assert main(["report", REGION, "--snapshot", str(folder), "--out", str(out)]) == 0
    return out


def test_fr17_15_a_real_test_grid_build_holds_the_audit_data_and_passes(built):
    data = json.loads((built / "options.json").read_text())
    audit = data["audit"]
    assert audit["buffer_m"] == 200.0
    assert audit["max_trip_km"] == 5.0
    assert [item["name"] for item in audit["places"]] == [
        "Grid School",
        "West School",
        "East School",
        "Mid Station",
    ]
    assert 0 < audit["longest_trip_m"] <= 5000.0
    assert all(item["links"] for item in data["options"])
    for item in data["options"]:
        assert all(len(line) >= 4 and len(line) % 2 == 0 for line in item["links"])
    page = (built / "report.html").read_text()
    assert checks.audit_problems_of(NAME, data, page) == []
