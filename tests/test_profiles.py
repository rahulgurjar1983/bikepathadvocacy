import re
from pathlib import Path

import pytest
import yaml

from bikeplan.config import ConfigError, config_hash, load_profile

SPEC = Path(__file__).resolve().parents[1] / "specs" / "01-config.md"
ROAD_CLASSES = {
    "living_street": (10, 200, 1),
    "service": (20, 200, 1),
    "residential": (50, 750, 2),
    "unclassified": (50, 1500, 2),
    "tertiary": (50, 5000, 2),
    "secondary": (60, 12000, 2),
    "primary": (60, 25000, 4),
    "trunk": (70, 35000, 4),
}


def spec_table(heading):
    text = SPEC.read_text()
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([^`]+)` \| (\S+) \| (.+) \|$", section, re.M)
    assert rows
    return rows


def parse(raw):
    if raw in ("true", "false"):
        return raw == "true"
    return float(raw) if "." in raw else int(raw)


def lookup(profile, dotted):
    node = profile
    for part in dotted.split("."):
        match = re.fullmatch(r"(\w+)(?:\[(\d+)\])?", part)
        node = getattr(node, match.group(1))
        if match.group(2):
            node = node[int(match.group(2))]
    return node


GOOD = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "profiles" / "au-nsw.yaml").read_text()
)


def write_profile(tmp_path, data):
    (tmp_path / "tiny.yaml").write_text(yaml.safe_dump(data))
    return tmp_path


def real(name):
    return load_profile(name)


@pytest.mark.parametrize("name,heading", [("au-nsw", "## 6."), ("generic", "## 7.")])
def test_fr1_3_fr1_4_every_value_matches_the_spec_table(name, heading):
    profile = real(name)
    for key, raw, source in spec_table(heading):
        number = lookup(profile, key)
        assert number.value == parse(raw), key
        assert number.assumption == source.startswith("assumption:"), key
        assert number.source == source, key


def test_fr1_3_au_nsw_table_has_every_row_checked():
    assert len(spec_table("## 6.")) == 20


def test_fr1_4_generic_table_has_every_row_checked():
    assert len(spec_table("## 7.")) == 20


@pytest.mark.parametrize("name", ["au-nsw", "generic"])
def test_fr1_5_each_road_class_has_speed_adt_and_lanes(name):
    profile = real(name)
    assert set(profile.road_classes) == set(ROAD_CLASSES)
    for cls, (speed, adt, lanes) in ROAD_CLASSES.items():
        found = profile.road_classes[cls]
        assert (found.speed_kmh.value, found.adt.value, found.lanes.value) == (speed, adt, lanes)
        assert found.speed_kmh.assumption and found.adt.assumption and found.lanes.assumption


@pytest.mark.parametrize("name", ["au-nsw", "generic"])
def test_fr1_5_implicit_speed_codes_map_to_kmh(name):
    codes = real(name).implicit_speeds
    assert codes["AU:urban"].value == 50
    assert codes["AU:rural"].value == 100
    assert codes["GB:nsl_single"].value == pytest.approx(96.56)
    assert codes["GB:nsl_dual"].value == pytest.approx(112.65)
    assert all(item.source for item in codes.values())


def test_fr1_2_number_without_source_names_the_key(tmp_path):
    data = yaml.safe_load(yaml.safe_dump(GOOD))
    del data["aaa"]["mixed_traffic"][0]["max_adt"]["source"]
    with pytest.raises(ConfigError) as info:
        load_profile("tiny", write_profile(tmp_path, data))
    assert "max_adt" in str(info.value)
    assert "source" in str(info.value)


def test_fr1_2_bare_number_names_the_key(tmp_path):
    data = yaml.safe_load(yaml.safe_dump(GOOD))
    data["aaa"]["mixed_traffic"][0]["max_adt"] = 2000
    with pytest.raises(ConfigError) as info:
        load_profile("tiny", write_profile(tmp_path, data))
    assert "max_adt" in str(info.value)


def test_fr1_2_empty_source_names_the_key(tmp_path):
    data = yaml.safe_load(yaml.safe_dump(GOOD))
    data["aaa"]["painted_lanes_count"]["source"] = ""
    with pytest.raises(ConfigError) as info:
        load_profile("tiny", write_profile(tmp_path, data))
    assert "painted_lanes_count" in str(info.value)


def test_fr1_2_unknown_profile_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_profile("nope", tmp_path)
    assert "nope" in str(info.value)


def test_fr1_2_assumption_source_is_kept_and_flagged():
    number = real("au-nsw").widths_m.verge_default
    assert number.assumption is True
    assert number.source.startswith("assumption:")
    assert real("au-nsw").widths_m.parking_lane.assumption is False


def test_fr1_2_profile_changes_the_config_hash():
    assert config_hash({"a": 1}, real("au-nsw")) != config_hash({"a": 1}, real("generic"))
    assert config_hash({"a": 1}, real("au-nsw")) == config_hash({"a": 1}, real("au-nsw"))
