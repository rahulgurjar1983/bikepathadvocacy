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
if args[:2] == ["release", "list"]:
    print(os.environ.get("GH_LAST", ""))
if args[:2] == ["release", "download"]:
    key = "GH_SOURCE" if args[2].startswith("snapshot-") else "GH_LAST_SOURCE"
    target = Path(args[args.index("--dir") + 1])
    target.mkdir(parents=True, exist_ok=True)
    for source in Path(os.environ[key]).iterdir():
        shutil.copy(source, target / source.name)
"""
BIKEPLAN_STAND_IN = """#!{python}
import hashlib, json, os, sys
from pathlib import Path

args = sys.argv[1:]
if os.environ.get("BP_REAL"):
    from bikeplan import main

    sys.exit(main(args))
with open(os.environ["BP_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["snapshot", "pull"]:
    if os.environ.get("GH_FAIL_PULL"):
        sys.exit(1)
    sys.exit(0)
if args[0] in ("report", "review"):
    out = Path(args[args.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    name = Path(args[1]).stem
    (out / "report.html").write_text(f"<html>{{args[0]}} {{name}}</html>")
    (out / "figures.json").write_text("{{}}")
    sums = "".join(
        hashlib.sha256((out / f).read_bytes()).hexdigest() + "  " + f + "\\n"
        for f in ("figures.json", "report.html")
    )
    (out / "SHA256SUMS").write_text(sums)
    sys.exit(0)
sys.exit(2)
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
    (work / "artifacts/X1").mkdir(parents=True)
    (work / "artifacts/X1/out.txt").write_text("one\n")
    (work / "VOICE.md").write_text("one\n")
    git(work, "init", "-q", "-b", "main")
    commit(work, "first")
    return work, source, bin_dir


def git(work, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t")
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    return subprocess.run(
        ["git", *args], cwd=work, env=env, check=True, capture_output=True, text=True
    )


def commit(work, message):
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", message)
    return git(work, "rev-parse", "HEAD").stdout.strip()


def add_review(work, name, public):
    folder = work / "routes" / name
    folder.mkdir(parents=True)
    (folder / "review.yaml").write_text(
        f"public: {public}\nroute: route.gpx\nclaims: claims.yaml\n"
        "region: ../../regions/au-nsw-bayside.yaml\n"
    )
    (folder / "route.gpx").write_text("<gpx/>")
    (folder / "claims.yaml").write_text("[]\n")


def last_release(tmp_path, names=("au-nsw-bayside-report.html", "au-nsw-bayside.tar.gz")):
    last = tmp_path / "last"
    last.mkdir()
    for name in names:
        (last / name).write_text(f"old {name}")
    lines = "".join(
        hashlib.sha256((last / n).read_bytes()).hexdigest() + "  " + n + "\n" for n in names
    )
    (last / "SHA256SUMS").write_text(lines)
    return last


def run_script(work, source, bin_dir, tag, path=None, **extra):
    script = work / "scripts/release.sh"
    if (ROOT / "scripts/release.sh").exists():
        shutil.copy(ROOT / "scripts/release.sh", script)
    env = dict(os.environ)
    env["PATH"] = path if path is not None else f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["GH_LOG"] = str(bin_dir.parent / "gh.log")
    env["BP_LOG"] = str(bin_dir.parent / "bp.log")
    env["GH_SOURCE"] = str(source)
    env["BIKEPLAN"] = str(bin_dir / "bikeplan")
    env["PYTHONPATH"] = str(ROOT / "src")
    env["RELEASE_OUT"] = str(bin_dir.parent / "out")
    env.update(extra)
    return subprocess.run(
        ["bash", str(script), tag],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )


def bp_calls(bin_dir):
    log = bin_dir.parent / "bp.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def upload_args(bin_dir):
    uploads = [c for c in calls(bin_dir) if c[:2] == ["release", "upload"]]
    assert len(uploads) == 1
    return uploads[0]


def uploaded(bin_dir):
    return {Path(a).name: Path(a) for a in upload_args(bin_dir)[3:] if not a.startswith("--")}


def calls(bin_dir):
    log = bin_dir.parent / "gh.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_fr13_7_uploads_every_file_named_in_sha256sums_to_the_release(repo):
    work, source, bin_dir = repo

    result = run_script(work, source, bin_dir, "v2026.10.07", BP_REAL="1")

    assert result.returncode == 0, result.stderr[-2000:]
    upload = upload_args(bin_dir)
    assert upload[2] == "v2026.10.07"
    assert "--clobber" in upload
    files = uploaded(bin_dir)
    assert {
        "au-nsw-bayside-report.html",
        "au-nsw-bayside.tar.gz",
        "artifacts.tar.gz",
        "index.html",
        "SHA256SUMS",
    } <= set(files)
    listed = {line.split("  ", 1)[1] for line in files["SHA256SUMS"].read_text().splitlines()}
    assert listed == set(files) - {"SHA256SUMS"}
    subprocess.run(
        ["sha256sum", "--check", "--strict", "SHA256SUMS"],
        cwd=files["SHA256SUMS"].parent,
        check=True,
        capture_output=True,
    )


def test_fr13_7_pulls_the_snapshot_release_named_in_the_region_file(repo):
    work, source, bin_dir = repo

    run_script(work, source, bin_dir, "v2026.10.07", BP_REAL="1")

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
    assert "release: no report to build" in result.stderr
    assert not [c for c in calls(bin_dir) if c[:2] == ["release", "upload"]]


def test_fr13_7_fails_hard_and_uploads_nothing_when_the_snapshot_pull_fails(repo):
    work, source, bin_dir = repo

    result = run_script(work, source, bin_dir, "v2026.10.07", GH_FAIL_PULL="1")

    assert result.returncode != 0
    assert [c for c in bp_calls(bin_dir) if c[:2] == ["snapshot", "pull"]]
    assert not [c for c in calls(bin_dir) if c[:2] == ["release", "upload"]]


def test_fr13_7_uploads_a_public_review_and_leaves_a_private_one_out(repo):
    work, source, bin_dir = repo
    add_review(work, "ride22", "true")
    add_review(work, "secret", "false")
    commit(work, "reviews")

    result = run_script(work, source, bin_dir, "v2026.10.07")

    assert result.returncode == 0, result.stderr[-2000:]
    files = uploaded(bin_dir)
    assert {"ride22-review.html", "ride22.tar.gz"} <= set(files)
    assert not [n for n in files if "secret" in n]
    reviews = [c for c in bp_calls(bin_dir) if c[0] == "review"]
    assert len(reviews) == 1
    assert "--claims" in reviews[0] and "--region" in reviews[0]
    assert "secret" not in files["index.html"].read_text()


def test_fr13_7_index_links_each_report_with_region_snapshot_and_commit(repo):
    work, source, bin_dir = repo
    head = git(work, "rev-parse", "HEAD").stdout.strip()

    result = run_script(work, source, bin_dir, "v2026.10.07")

    assert result.returncode == 0, result.stderr[-2000:]
    index = uploaded(bin_dir)["index.html"].read_text()
    assert 'href="au-nsw-bayside-report.html"' in index
    assert "au-nsw-bayside" in index
    assert "2026-10-01" in index
    assert head in index


def test_fr13_7_artifacts_archive_holds_the_artifacts_folder(repo):
    work, source, bin_dir = repo

    run_script(work, source, bin_dir, "v2026.10.07")

    listing = subprocess.run(
        ["tar", "-tzf", str(uploaded(bin_dir)["artifacts.tar.gz"])],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert "artifacts/X1/out.txt" in listing


def test_fr13_7_a_merge_that_changes_only_specs_copies_the_last_release_reports(repo, tmp_path):
    work, source, bin_dir = repo
    last = last_release(tmp_path)
    (work / "specs").mkdir()
    (work / "specs/00-scaffold.md").write_text("changed\n")
    commit(work, "spec only")

    result = run_script(
        work, source, bin_dir, "v2026.10.07", GH_LAST="v2026.10.06", GH_LAST_SOURCE=str(last)
    )

    assert result.returncode == 0, result.stderr[-2000:]
    assert not [c for c in bp_calls(bin_dir) if c[0] in ("report", "review")]
    files = uploaded(bin_dir)
    assert files["au-nsw-bayside-report.html"].read_text() == "old au-nsw-bayside-report.html"
    assert "v2026.10.06" in files["index.html"].read_text()


def test_fr13_7_a_merge_that_changes_the_voice_file_rebuilds_every_report(repo, tmp_path):
    work, source, bin_dir = repo
    last = last_release(tmp_path)
    (work / "VOICE.md").write_text("two\n")
    commit(work, "code change")

    result = run_script(
        work, source, bin_dir, "v2026.10.07", GH_LAST="v2026.10.06", GH_LAST_SOURCE=str(last)
    )

    assert result.returncode == 0, result.stderr[-2000:]
    assert [c for c in bp_calls(bin_dir) if c[0] == "report"]
    assert "old" not in uploaded(bin_dir)["au-nsw-bayside-report.html"].read_text()
    assert "v2026.10.06" not in uploaded(bin_dir)["index.html"].read_text()


def test_fr13_7_fails_hard_when_a_copied_report_no_longer_matches_its_sum(repo, tmp_path):
    work, source, bin_dir = repo
    last = last_release(tmp_path)
    (last / "au-nsw-bayside-report.html").write_text("tampered")
    (work / "specs").mkdir()
    (work / "specs/00-scaffold.md").write_text("changed\n")
    commit(work, "spec only")

    result = run_script(
        work, source, bin_dir, "v2026.10.07", GH_LAST="v2026.10.06", GH_LAST_SOURCE=str(last)
    )

    assert result.returncode != 0
    assert "au-nsw-bayside-report.html" in result.stdout + result.stderr
    assert not [c for c in calls(bin_dir) if c[:2] == ["release", "upload"]]
