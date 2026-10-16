import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest
import yaml

from bikeplan import main

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "regions" / "sets" / "greater-sydney.yaml"
BASE = "au-nsw-bayside"


def set_problems(*args):
    from bikeplan.snapshot_set import set_problems as found

    return found(*args)


FILES = {
    "kontur_population": "population.gpkg",
    "nsw_cadastre": "parcels.gpkg",
    "copernicus_glo30": "elevation.tif",
    "nsw_road_segment": "road_segments.gpkg",
    "tfnsw_speed_zones": "speed_zones.gpkg",
}


def bayside_manifest():
    region = yaml.safe_load((ROOT / "regions" / f"{BASE}.yaml").read_text())
    names = ["boundary.geojson", "network.osm.gz", "places.json"]
    names += [FILES[a] for a in region["snapshot"]["adapters"]]
    return {
        "snapshot_id": region["snapshot"]["osm_date"][:10],
        "osm_date": region["snapshot"]["osm_date"],
        "files": [{"name": n, "path": n} for n in names],
    }


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


def test_fr18_2_every_published_council_has_a_manifest_like_bayside():
    problems = set_problems(SET, ROOT)
    others = [p for p in problems if not p.endswith(": no manifest")]
    assert [p for p in others if not p.startswith("au-nsw-bayside:")] == []
    assert len(problems) < len(councils())


GH_STAND_IN = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["release", "view"]:
    sys.exit(1)
"""


@pytest.fixture
def stand_ins(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(GH_STAND_IN.format(python=sys.executable))
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GH_LOG", str(log))
    fetched = []
    broken = set()

    def fake_fetch(region, out, endpoint=None):
        fetched.append(region.id)
        if region.id in broken:
            raise OSError("overpass 504")
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        entries = []
        for name in bayside_manifest()["files"]:
            content = f"{region.id} {name['name']}".encode()
            (out / name["name"]).write_bytes(content)
            entries.append(
                {
                    "name": name["name"],
                    "path": name["name"],
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                }
            )
        manifest = dict(
            bayside_manifest(), region=region.id, osm_date=region.snapshot.osm_date, files=entries
        )
        (out / "manifest.json").write_text(json.dumps(manifest))
        return manifest

    monkeypatch.setattr("bikeplan.snapshot_set.fetch_snapshot", fake_fetch)

    def uploads():
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return [c[2] for c in calls if c[:2] == ["release", "upload"]]

    return fetched, broken, uploads


def run_set(root):
    return main(
        [
            "snapshot",
            "set",
            str(root / "regions" / "sets" / "greater-sydney.yaml"),
            "--root",
            str(root),
            "--cache",
            str(root / "cache"),
        ]
    )


def test_fr18_2_the_set_command_fetches_checks_and_publishes_only_missing_councils(
    tmp_path, stand_ins
):
    fetched, _, uploads = stand_ins
    ids = councils()
    root = tree(tmp_path / "repo", ids[:-2])

    assert run_set(root) == 0

    assert fetched == ids[-2:]
    date = bayside_manifest()["snapshot_id"]
    assert sorted(uploads()) == sorted(f"snapshot-{i}-{date}" for i in ids[-2:])
    assert set_problems(root / "regions" / "sets" / "greater-sydney.yaml", root) == []


def test_fr18_2_a_second_run_of_the_set_command_fetches_nothing(tmp_path, stand_ins):
    fetched, _, _ = stand_ins
    root = tree(tmp_path / "repo", councils()[:-1])
    assert run_set(root) == 0
    fetched.clear()

    assert run_set(root) == 0

    assert fetched == []


def test_fr18_2_a_failed_council_does_not_stop_the_rest_and_a_rerun_resumes(
    tmp_path, stand_ins, capsys
):
    fetched, broken, _ = stand_ins
    ids = councils()
    root = tree(tmp_path / "repo", ids[:-3])
    broken.add(ids[-3])

    assert run_set(root) == 1

    assert fetched == ids[-3:]
    assert ids[-3] in capsys.readouterr().err
    problems = set_problems(root / "regions" / "sets" / "greater-sydney.yaml", root)
    assert problems == [f"{ids[-3]}: no manifest"]
    broken.clear()
    fetched.clear()

    assert run_set(root) == 0
    assert fetched == [ids[-3]]


def test_fr18_2_a_snapshot_that_fails_its_check_is_not_published(tmp_path, stand_ins, monkeypatch):
    _, _, uploads = stand_ins
    root = tree(tmp_path / "repo", councils()[:-1])
    from bikeplan import snapshot_set

    inner = snapshot_set.fetch_snapshot

    def corrupt(region, out, endpoint=None):
        manifest = inner(region, out, endpoint)
        (Path(out) / "network.osm.gz").write_bytes(b"changed")
        return manifest

    monkeypatch.setattr(snapshot_set, "fetch_snapshot", corrupt)

    assert run_set(root) == 1
    assert uploads() == []


def test_fr18_2_an_overpass_error_on_one_council_does_not_stop_the_rest(
    tmp_path, stand_ins, monkeypatch, capsys
):
    fetched, _, _ = stand_ins
    ids = councils()
    root = tree(tmp_path / "repo", ids[:-3])
    from bikeplan import snapshot_set
    from bikeplan.snapshot import OverpassError

    inner = snapshot_set.fetch_snapshot

    def flaky(region, out, endpoint=None):
        if region.id == ids[-3]:
            raise OverpassError("HTTP Error 502: Bad Gateway")
        return inner(region, out, endpoint)

    monkeypatch.setattr("bikeplan.snapshot_set.fetch_snapshot", flaky)

    assert run_set(root) == 1

    assert fetched == ids[-2:]
    assert ids[-3] in capsys.readouterr().err


def test_fr18_2_only_fetches_just_the_named_councils(tmp_path, stand_ins):
    fetched, _, _ = stand_ins
    ids = councils()
    root = tree(tmp_path / "repo", ids[:-3])

    code = main(
        [
            "snapshot",
            "set",
            str(root / "regions" / "sets" / "greater-sydney.yaml"),
            "--root",
            str(root),
            "--cache",
            str(root / "cache"),
            "--only",
            ids[-1],
        ]
    )

    assert code == 0
    assert fetched == [ids[-1]]


def test_fr18_2_a_council_over_its_seconds_limit_is_named_and_the_run_goes_on(
    tmp_path, stand_ins, monkeypatch, capsys
):
    import time

    ids = councils()
    root = tree(tmp_path / "repo", ids[:-2])
    from bikeplan import snapshot_set

    inner = snapshot_set.fetch_snapshot

    def slow(region, out, endpoint=None):
        if region.id == ids[-2]:
            time.sleep(30)
        return inner(region, out, endpoint)

    monkeypatch.setattr("bikeplan.snapshot_set.fetch_snapshot", slow)

    started = time.monotonic()
    code = main(
        [
            "snapshot",
            "set",
            str(root / "regions" / "sets" / "greater-sydney.yaml"),
            "--root",
            str(root),
            "--cache",
            str(root / "cache"),
            "--seconds",
            "1",
        ]
    )

    assert time.monotonic() - started < 20
    assert code == 1
    assert ids[-2] in capsys.readouterr().err
    problems = set_problems(root / "regions" / "sets" / "greater-sydney.yaml", root)
    assert problems == [f"{ids[-2]}: no manifest"]


def test_fr18_2_the_seconds_limit_ends_a_council_stuck_inside_the_retry_loop(
    tmp_path, stand_ins, monkeypatch, capsys
):
    import time

    ids = councils()
    root = tree(tmp_path / "repo", ids[:-2])
    from bikeplan import snapshot, snapshot_set

    monkeypatch.setattr(snapshot, "RETRY_BASE_SECONDS", 0)
    inner = snapshot_set.fetch_snapshot

    def stuck(region, out, endpoint=None):
        if region.id == ids[-2]:
            snapshot.with_retries(lambda: time.sleep(6))
        return inner(region, out, endpoint)

    monkeypatch.setattr("bikeplan.snapshot_set.fetch_snapshot", stuck)

    started = time.monotonic()
    code = main(
        [
            "snapshot",
            "set",
            str(root / "regions" / "sets" / "greater-sydney.yaml"),
            "--root",
            str(root),
            "--cache",
            str(root / "cache"),
            "--seconds",
            "1",
        ]
    )

    assert time.monotonic() - started < 5
    assert code == 1
    assert ids[-2] in capsys.readouterr().err
    problems = set_problems(root / "regions" / "sets" / "greater-sydney.yaml", root)
    assert problems == [f"{ids[-2]}: no manifest"]
