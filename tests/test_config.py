import copy
import re

import pytest
import yaml

from bikeplan.config import ConfigError, config_hash, load_region

GOOD = yaml.safe_load("""
id: au-nsw-bayside
name: Bayside Council, New South Wales
country: AU
subdivision: AU-NSW
boundary:
  osm_relation: 7038238
analysis_buffer_m: 2680
profile: au-nsw
snapshot:
  osm_date: "2026-10-01T00:00:00Z"
  adapters: [kontur_population]
population:
  source: kontur_population
destinations:
  school: {weight: 3}
  library: {weight: 1}
access:
  reach_m: 2680
  detour_max: 1.25
proposals:
  max_projects: 25
  budget_km: 40
  candidate_pool: 20
  min_gain: 0.05
  metres_per_point: 10
  disruption_weights:
    parking_space: 1.0
    lane_km: 40.0
    speed_km: 2.0
    signal: 15.0
    refuge: 3.0
    path_km: 5.0
""")


def write(tmp_path, data, name="region.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data))
    return path


def changed(**edits):
    data = copy.deepcopy(GOOD)
    for dotted, value in edits.items():
        keys = dotted.split("__")
        target = data
        for key in keys[:-1]:
            target = target[key]
        if value is DROP:
            del target[keys[-1]]
        else:
            target[keys[-1]] = value
    return data


DROP = object()


def fails(tmp_path, data, key):
    path = write(tmp_path, data)
    with pytest.raises(ConfigError) as info:
        load_region(path)
    message = str(info.value)
    assert key in message
    assert str(path) in message


def test_fr1_1_good_file_loads(tmp_path):
    region = load_region(write(tmp_path, GOOD))
    assert region.id == "au-nsw-bayside"
    assert region.boundary.osm_relation == 7038238
    assert region.boundary.geojson is None
    assert region.destinations["school"].weight == 3
    assert region.access.detour_max == 1.25
    assert region.proposals.disruption_weights.lane_km == 40.0
    assert region.snapshot.adapters == ["kontur_population"]


def test_fr1_1_unknown_key_names_the_key(tmp_path):
    fails(tmp_path, changed(access__surprise=1), "surprise")


def test_fr1_1_unknown_top_key_names_the_key(tmp_path):
    data = changed()
    data["extra_thing"] = 1
    fails(tmp_path, data, "extra_thing")


def test_fr1_1_missing_key_names_the_key(tmp_path):
    fails(tmp_path, changed(proposals__budget_km=DROP), "budget_km")


def test_fr1_1_wrong_type_names_the_key(tmp_path):
    fails(tmp_path, changed(analysis_buffer_m="wide"), "analysis_buffer_m")


def test_fr1_1_boolean_is_not_a_number(tmp_path):
    fails(tmp_path, changed(access__reach_m=True), "reach_m")


def test_fr1_1_both_boundary_kinds_fail(tmp_path):
    fails(tmp_path, changed(boundary={"osm_relation": 1, "geojson": "a.geojson"}), "boundary")


def test_fr1_1_no_boundary_kind_fails(tmp_path):
    fails(tmp_path, changed(boundary={}), "boundary")


def test_fr1_1_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_region(tmp_path / "nope.yaml")
    assert "nope.yaml" in str(info.value)


def test_fr1_1_non_mapping_file_is_a_config_error(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- 1\n- 2\n")
    with pytest.raises(ConfigError) as info:
        load_region(path)
    assert "list.yaml" in str(info.value)


def test_fr11_4_geojson_boundary_loads(tmp_path):
    region = load_region(write(tmp_path, changed(boundary={"geojson": "boundary.geojson"})))
    assert region.boundary.geojson == "boundary.geojson"
    assert region.boundary.osm_relation is None


def test_fr11_4_both_boundary_kinds_fail_and_name_the_key(tmp_path):
    fails(tmp_path, changed(boundary={"osm_relation": 5, "geojson": "b.geojson"}), "geojson")


def test_fr1_8_negative_weight_names_the_key(tmp_path):
    fails(tmp_path, changed(destinations__library={"weight": -1}), "destinations.library.weight")


def test_fr1_8_all_zero_weights_name_the_key(tmp_path):
    data = changed(destinations={"school": {"weight": 0}, "library": {"weight": 0}})
    fails(tmp_path, data, "destinations")


def test_fr1_8_zero_weight_beside_a_positive_one_loads(tmp_path):
    data = changed(destinations={"school": {"weight": 0}, "library": {"weight": 2}})
    assert load_region(write(tmp_path, data)).destinations["school"].weight == 0


def test_fr1_8_detour_max_below_one_names_the_key(tmp_path):
    fails(tmp_path, changed(access__detour_max=0.9), "detour_max")


def test_fr1_8_detour_max_of_exactly_one_loads(tmp_path):
    assert load_region(write(tmp_path, changed(access__detour_max=1.0))).access.detour_max == 1.0


def test_fr1_8_reach_not_above_zero_names_the_key(tmp_path):
    fails(tmp_path, changed(access__reach_m=0), "reach_m")


def test_fr1_6_hash_is_stable_across_loads(tmp_path):
    path = write(tmp_path, GOOD)
    profile = {"id": "au-nsw", "speed": {"value": 30, "source": "x"}}
    first = config_hash(load_region(path), profile)
    second = config_hash(load_region(path), profile)
    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)


def test_fr1_6_hash_ignores_key_order_in_the_file(tmp_path):
    a = write(tmp_path, GOOD, "a.yaml")
    b = tmp_path / "b.yaml"
    b.write_text(yaml.safe_dump(GOOD, sort_keys=True))
    profile = {"id": "p"}
    assert config_hash(load_region(a), profile) == config_hash(load_region(b), profile)


def test_fr1_6_hash_changes_when_a_region_value_changes(tmp_path):
    profile = {"id": "p"}
    base = config_hash(load_region(write(tmp_path, GOOD)), profile)
    other = config_hash(load_region(write(tmp_path, changed(access__reach_m=2681))), profile)
    assert base != other


def test_fr1_6_hash_changes_when_a_profile_value_changes(tmp_path):
    region = load_region(write(tmp_path, GOOD))
    assert config_hash(region, {"v": 1}) != config_hash(region, {"v": 2})
