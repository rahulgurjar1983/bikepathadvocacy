import gzip
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/network/junctions.osm"
BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [151.10, -33.97],
                [151.14, -33.97],
                [151.14, -33.88],
                [151.10, -33.88],
                [151.10, -33.97],
            ]
        ],
    },
}
GH_STAND_IN = """#!{python}
import json, os, shutil, sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["release", "view"]:
    sys.exit(0 if os.environ.get("GH_RELEASE_EXISTS") else 1)
if args[:2] == ["release", "download"]:
    target = Path(args[args.index("--dir") + 1])
    target.mkdir(parents=True, exist_ok=True)
    for source in Path(os.environ["GH_SOURCE"]).iterdir():
        shutil.copy(source, target / source.name)
"""
BIKEPLAN_STAND_IN = """#!{python}
import sys
from bikeplan import main

sys.exit(main(sys.argv[1:]))
"""


def executable(path: Path, text: str) -> Path:
    path.write_text(text.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    (work / "regions").mkdir()
    shutil.copy(ROOT / "regions/au-nsw-bayside.yaml", work / "regions/au-nsw-bayside.yaml")
    source = tmp_path / "source"
    source.mkdir()
    (source / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (source / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    entries = [
        {
            "name": path.name,
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in sorted(source.iterdir())
    ]
    manifest = {"region": "au-nsw-bayside", "snapshot_id": "2026-10-01", "files": entries}
    folder = work / "snapshots/au-nsw-bayside/2026-10-01"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable(bin_dir / "gh", GH_STAND_IN)
    executable(bin_dir / "bikeplan", BIKEPLAN_STAND_IN)
    return work, source, bin_dir


def run_script(work, source, bin_dir, tag, path=None):
    script = work / "scripts/release-report.sh"
    if (ROOT / "scripts/release-report.sh").exists():
        shutil.copy(ROOT / "scripts/release-report.sh", script)
    env = dict(os.environ)
    env["PATH"] = path if path is not None else f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["GH_LOG"] = str(bin_dir.parent / "gh.log")
    env["GH_SOURCE"] = str(source)
    env["BIKEPLAN"] = str(bin_dir / "bikeplan")
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        ["bash", str(work / "scripts/release-report.sh"), tag],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )


def calls(bin_dir):
    log = bin_dir.parent / "gh.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_fr13_7_uploads_every_file_named_in_sha256sums_to_the_release(repo):
    work, source, bin_dir = repo

    result = run_script(work, source, bin_dir, "v2026.10.07")

    assert result.returncode == 0, result.stderr[-2000:]
    uploads = [c for c in calls(bin_dir) if c[:2] == ["release", "upload"]]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload[2] == "v2026.10.07"
    assert "--clobber" in upload
    names = {Path(arg).name for arg in upload[3:] if not arg.startswith("--")}
    assert {"report.html", "figures.json", "SHA256SUMS"} <= names
    sums = next(Path(arg) for arg in upload[3:] if arg.endswith("SHA256SUMS"))
    listed = {line.split("  ", 1)[1] for line in sums.read_text().splitlines()}
    assert listed <= names


def test_fr13_7_pulls_the_snapshot_release_named_in_the_region_file(repo):
    work, source, bin_dir = repo

    run_script(work, source, bin_dir, "v2026.10.07")

    downloads = [c for c in calls(bin_dir) if c[:2] == ["release", "download"]]
    assert [c[2] for c in downloads] == ["snapshot-au-nsw-bayside-2026-10-01"]


def test_fr13_7_fails_hard_without_gh(repo, tmp_path):
    work, source, bin_dir = repo
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "bash").symlink_to("/usr/bin/bash")

    result = run_script(work, source, bin_dir, "v2026.10.07", path=str(bare))

    assert result.returncode != 0
    assert "gh" in result.stderr


def test_fr13_7_fails_hard_and_uploads_nothing_when_the_snapshot_is_missing(repo):
    work, source, bin_dir = repo
    shutil.rmtree(work / "snapshots")

    result = run_script(work, source, bin_dir, "v2026.10.07")

    assert result.returncode != 0
    assert "release-report: no snapshot manifest" in result.stderr
    assert not [c for c in calls(bin_dir) if c[:2] == ["release", "upload"]]
