import dataclasses
import subprocess
import sys
from pathlib import Path

from bikeplan.config import Num, config_hash, load_profile, load_region

ROOT = Path(__file__).resolve().parents[1]


def region(name):
    return load_region(ROOT / "regions" / f"{name}.yaml")


def nums(item, prefix=""):
    if isinstance(item, Num):
        yield prefix, item
    elif isinstance(item, dict):
        for key, value in item.items():
            yield from nums(value, f"{prefix}.{key}")
    elif isinstance(item, list):
        for index, value in enumerate(item):
            yield from nums(value, f"{prefix}[{index}]")
    elif dataclasses.is_dataclass(item):
        for field in dataclasses.fields(item):
            yield from nums(getattr(item, field.name), f"{prefix}.{field.name}")


def show(name):
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "from bikeplan import main; raise SystemExit(main())",
            "config",
            "show",
            f"regions/{name}.yaml",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin"},
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_fr1_7_bayside_region_points_at_relation_and_au_nsw():
    found = region("au-nsw-bayside")
    assert found.id == "au-nsw-bayside"
    assert found.boundary.osm_relation == 7038238
    assert found.profile == "au-nsw"


def test_fr1_7_cambridge_region_points_at_relation_and_generic():
    found = region("gb-cambridge")
    assert found.id == "gb-cambridge"
    assert found.country == "GB"
    assert found.boundary.osm_relation == 295355
    assert found.profile == "generic"


def test_fr1_7_test_grid_region_uses_geojson_box_and_au_nsw():
    found = region("test-grid")
    assert found.id == "test-grid"
    assert found.boundary.osm_relation is None
    assert found.boundary.geojson.endswith(".geojson")
    assert found.profile == "au-nsw"


def test_fr1_9_show_prints_every_profile_value_with_source_and_hash():
    out = show("au-nsw-bayside")
    found = region("au-nsw-bayside")
    profile = load_profile(found.profile)
    assert "au-nsw-bayside" in out
    assert config_hash(found, profile) in out
    lines = out.splitlines()
    for key, num in nums(profile):
        line = next(x for x in lines if x.strip().startswith(f"{key.lstrip('.')} "))
        assert str(num.value) in line
        assert num.source in line


def test_fr1_9_show_marks_assumptions():
    out = show("gb-cambridge")
    profile = load_profile("generic")
    for key, num in nums(profile):
        line = next(x for x in out.splitlines() if x.strip().startswith(f"{key.lstrip('.')} "))
        assert ("[assumption]" in line) == num.assumption
