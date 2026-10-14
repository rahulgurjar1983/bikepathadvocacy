from pathlib import Path

import yaml

from bikeplan.config import load_region

ROOT = Path(__file__).resolve().parents[1]
COUNCILS = (
    "Bayside, Blacktown, Blue Mountains, Burwood, Camden, Campbelltown, Canada Bay, "
    "Canterbury-Bankstown, Cumberland, Fairfield, Georges River, Hawkesbury, Hornsby, "
    "Hunters Hill, Inner West, Ku-ring-gai, Lane Cove, Liverpool, Mosman, North Sydney, "
    "Northern Beaches, Parramatta, Penrith, Randwick, Ryde, Strathfield, Sutherland, Sydney, "
    "The Hills, Waverley, Willoughby, Wollondilly, Woollahra"
).split(", ")
SETTINGS_APART = ("id", "name", "boundary")


def listed():
    raw = yaml.safe_load((ROOT / "regions" / "sets" / "greater-sydney.yaml").read_text())
    return raw["councils"]


def settings(path):
    raw = yaml.safe_load(Path(path).read_text())
    return {key: value for key, value in raw.items() if key not in SETTINGS_APART}


def differences(path, base):
    return sorted(
        key
        for key in set(settings(path)) | set(settings(base))
        if settings(path).get(key) != settings(base).get(key)
    )


def test_fr18_1_the_set_lists_the_33_councils_in_order_with_relation_ids():
    councils = listed()
    assert [c["name"] for c in councils] == COUNCILS
    relations = [c["osm_relation"] for c in councils]
    assert all(isinstance(r, int) and r > 0 for r in relations)
    assert len(set(relations)) == 33
    assert len({c["id"] for c in councils}) == 33


def test_fr18_1_each_council_has_a_region_file_that_loads_with_its_relation():
    for council in listed():
        found = load_region(ROOT / "regions" / f"{council['id']}.yaml")
        assert found.id == council["id"]
        assert found.boundary.osm_relation == council["osm_relation"]
        assert found.boundary.geojson is None
        assert council["name"].split("-")[0] in found.name


def test_fr18_1_every_setting_matches_bayside_except_id_name_and_boundary():
    base = ROOT / "regions" / "au-nsw-bayside.yaml"
    for council in listed():
        path = ROOT / "regions" / f"{council['id']}.yaml"
        assert differences(path, base) == [], council["id"]


def test_fr18_1_bayside_is_the_first_council_and_its_file_is_the_shipped_one():
    first = listed()[0]
    assert first["id"] == "au-nsw-bayside"
    assert first["osm_relation"] == 7038238
