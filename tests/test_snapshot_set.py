import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "regions" / "sets" / "greater-sydney.yaml"
BASE = "au-nsw-bayside"


def set_problems(*args):
    from bikeplan.snapshot_set import set_problems as found

    return found(*args)


def bayside_manifest():
    found = sorted((ROOT / "snapshots" / BASE).glob("*/manifest.json"))
    return json.loads(found[-1].read_text())


def tree(tmp_path, names):
    shutil.copytree(ROOT / "regions", tmp_path / "regions")
    bayside = bayside_manifest()
    for name in names:
        folder = tmp_path / "snapshots" / name / bayside["snapshot_id"]
        folder.mkdir(parents=True)
        manifest = dict(bayside, region=name)
        (folder / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def councils():
    return [c["id"] for c in yaml.safe_load(SET.read_text())["councils"]]


def test_fr18_2_a_missing_manifest_fails_and_names_the_council(tmp_path):
    ids = councils()
    root = tree(tmp_path, ids[:-1])
    problems = set_problems(root / "regions" / "sets" / "greater-sydney.yaml", root)
    assert problems == [f"{ids[-1]}: no manifest"]


def test_fr18_2_a_wrong_date_or_adapter_list_fails(tmp_path):
    ids = councils()
    root = tree(tmp_path, ids)
    bad = next((root / "snapshots" / ids[3]).glob("*/manifest.json"))
    data = json.loads(bad.read_text())
    data["osm_date"] = "2026-09-01T00:00:00Z"
    bad.write_text(json.dumps(data))
    worse = next((root / "snapshots" / ids[4]).glob("*/manifest.json"))
    data = json.loads(worse.read_text())
    data["files"] = [f for f in data["files"] if f["name"] != "population.gpkg"]
    worse.write_text(json.dumps(data))
    problems = set_problems(root / "regions" / "sets" / "greater-sydney.yaml", root)
    assert [p.split(":")[0] for p in problems] == [ids[3], ids[4]]
    assert "osm_date" in problems[0]
    assert "population.gpkg" in problems[1]


def test_fr18_2_every_council_in_the_set_has_a_manifest_like_bayside():
    assert set_problems(SET, ROOT) == []


def test_fr18_2_each_council_has_a_recorded_run_time_and_memory():
    runs = json.loads((ROOT / "artifacts" / "G1.2" / "runs.json").read_text())
    assert [r["region"] for r in runs] == councils()
    for run in runs:
        assert run["seconds"] > 0
        assert run["peak_rss_mb"] > 0
