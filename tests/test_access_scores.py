import gzip
import json
import shutil
from pathlib import Path

from bikeplan import main
from bikeplan.access import Reach, score_access
from tests.test_width_fusion import BOUNDARY

WEIGHTS = {"school": 2.0, "library": 1.0, "station": 5.0}
PLACED = [("school", 10), ("school", 11), ("library", 12)]
PEOPLE = {1: 100.0, 2: 200.0}
RESULTS = [
    Reach({1: 100.0, 2: 300.0}, {1}),
    Reach({1: 200.0}, set()),
    Reach({1: 50.0}, {1}),
]


def test_fr7_7_home_score_is_the_weighted_mean_of_its_type_scores():
    found = score_access(PEOPLE, PLACED, RESULTS, WEIGHTS)
    assert found["homes"][1]["types"] == {"school": 0.5, "library": 1.0}
    assert abs(found["homes"][1]["score"] - 2 / 3) < 1e-9


def test_fr7_7_a_type_with_no_place_in_reach_is_left_out_of_the_mean():
    found = score_access(PEOPLE, PLACED, RESULTS, WEIGHTS)
    assert found["homes"][2]["types"] == {"school": 0.0}
    assert found["homes"][2]["score"] == 0.0


def test_fr7_7_region_score_is_population_weighted_times_100_to_one_decimal():
    found = score_access(PEOPLE, PLACED, RESULTS, WEIGHTS)
    assert found["score"] == 22.2


def test_fr7_7_each_type_gets_a_region_score_and_a_count_of_people_with_safe_reach():
    found = score_access(PEOPLE, PLACED, RESULTS, WEIGHTS)
    assert found["types"] == {"school": 16.7, "library": 100.0, "station": 0.0}
    assert found["safe_people"] == {"school": 100.0, "library": 100.0, "station": 0.0}


def test_fr7_7_homes_with_no_place_in_reach_score_zero_but_still_count_people():
    found = score_access({1: 100.0, 3: 300.0}, PLACED, RESULTS, WEIGHTS)
    assert found["homes"][3]["score"] == 0.0
    assert found["score"] == 16.7


def test_fr7_7_a_zero_weight_type_does_not_move_the_score():
    found = score_access(PEOPLE, PLACED, RESULTS, {**WEIGHTS, "library": 0.0})
    assert found["homes"][1]["score"] == 0.5


def snapshot(tmp_path):
    tmp_path.mkdir()
    (tmp_path / "network.osm.gz").write_bytes(
        gzip.compress(Path("tests/fixtures/network/cases.osm").read_bytes(), mtime=0)
    )
    (tmp_path / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    school = {"type": "node", "id": 7, "lat": -33.9124, "lon": 151.1205}
    school["tags"] = {"amenity": "school", "name": "Test School"}
    far = {"type": "node", "id": 8, "lat": -33.5, "lon": 151.1205}
    far["tags"] = {"amenity": "library"}
    (tmp_path / "places.json").write_text(json.dumps({"elements": [school, far]}))
    source = Path("tests/fixtures/kontur/kontur_population_AU_20231101.gpkg.gz")
    with gzip.open(source) as raw, (tmp_path / "population.gpkg").open("wb") as target:
        shutil.copyfileobj(raw, target)
    return tmp_path


def test_fr7_8_the_command_writes_the_three_files(tmp_path):
    folder = snapshot(tmp_path / "snap")
    out = tmp_path / "out"
    code = main(
        ["access", "regions/au-nsw-bayside.yaml", "--snapshot", str(folder), "--out", str(out)]
    )
    assert code == 0
    places = json.loads((out / "places.geojson").read_text())
    assert [f["properties"]["name"] for f in places["features"]] == ["Test School"]
    homes = json.loads((out / "access_homes.geojson").read_text())
    assert homes["type"] == "FeatureCollection"
    for feature in homes["features"]:
        assert {"node", "people", "score", "types"} <= set(feature["properties"])
    summary = json.loads((out / "access_summary.json").read_text())
    assert {"score", "types", "safe_people", "not_snapped"} <= set(summary)
    assert set(summary["types"]) == {
        "school",
        "college",
        "university",
        "aged_care",
        "library",
        "town_centre",
        "station",
    }


def test_fr7_8_the_command_fails_hard_without_a_places_file(tmp_path, capsys):
    folder = snapshot(tmp_path / "snap")
    (folder / "places.json").unlink()
    code = main(
        [
            "access",
            "regions/au-nsw-bayside.yaml",
            "--snapshot",
            str(folder),
            "--out",
            str(tmp_path / "o"),
        ]
    )
    assert code == 1
    assert "places.json" in capsys.readouterr().err
