import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from bikeplan import main

FILES = {"boundary.geojson": b'{"type":"Polygon"}', "network.osm.gz": b"abcdef" * 50}


def make_snapshot(directory: Path) -> Path:
    directory.mkdir(parents=True)
    entries = []
    for name, content in FILES.items():
        (directory / name).write_bytes(content)
        entries.append(
            {
                "name": name,
                "path": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
    manifest = {"region": "test-region", "snapshot_id": "2026-10-01", "files": entries}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


def run_verify(capsys, directory):
    code = main(["snapshot", "verify", str(directory)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_fr2_5_verify_passes_and_prints_each_file_with_sha256(tmp_path, capsys):
    directory = make_snapshot(tmp_path / "snap")

    code, out, _ = run_verify(capsys, directory)

    assert code == 0
    for name, content in FILES.items():
        assert f"{name} ok {hashlib.sha256(content).hexdigest()}" in out


def test_fr2_5_verify_fails_on_a_changed_byte_and_names_the_file(tmp_path, capsys):
    directory = make_snapshot(tmp_path / "snap")
    changed = bytearray(FILES["network.osm.gz"])
    changed[0] ^= 1
    (directory / "network.osm.gz").write_bytes(bytes(changed))

    code, _, err = run_verify(capsys, directory)

    assert code != 0
    assert "network.osm.gz" in err
    assert "boundary.geojson" not in err


def test_fr2_5_verify_fails_on_a_missing_file_and_names_it(tmp_path, capsys):
    directory = make_snapshot(tmp_path / "snap")
    (directory / "boundary.geojson").unlink()

    code, _, err = run_verify(capsys, directory)

    assert code != 0
    assert "boundary.geojson" in err


def test_fr2_5_verify_fails_on_a_wrong_size_and_names_the_file(tmp_path, capsys):
    directory = make_snapshot(tmp_path / "snap")
    with (directory / "boundary.geojson").open("ab") as handle:
        handle.write(b"x")

    code, _, err = run_verify(capsys, directory)

    assert code != 0
    assert "boundary.geojson" in err
    assert "size" in err


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
        if source.name != "manifest.json":
            shutil.copy(source, target / source.name)
"""


@pytest.fixture
def gh_on_path(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(GH_STAND_IN.format(python=sys.executable))
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GH_LOG", str(log))
    monkeypatch.delenv("GH_RELEASE_EXISTS", raising=False)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()]

    return calls


def test_fr2_6_publish_creates_the_release_uploads_every_file_and_copies_the_manifest(
    tmp_path, monkeypatch, gh_on_path
):
    directory = make_snapshot(tmp_path / "snap")
    work = tmp_path / "repo"
    work.mkdir()
    monkeypatch.chdir(work)

    assert main(["snapshot", "publish", str(directory)]) == 0

    tag = "snapshot-test-region-2026-10-01"
    calls = gh_on_path()
    create = [c for c in calls if c[:2] == ["release", "create"]]
    upload = [c for c in calls if c[:2] == ["release", "upload"]]
    assert len(create) == 1 and create[0][2] == tag
    assert len(upload) == 1 and upload[0][2] == tag
    for name in FILES:
        assert str(directory / name) in upload[0]
    copied = work / "snapshots/test-region/2026-10-01/manifest.json"
    assert copied.read_bytes() == (directory / "manifest.json").read_bytes()


def test_fr2_6_publish_reuses_an_existing_release(tmp_path, monkeypatch, gh_on_path):
    directory = make_snapshot(tmp_path / "snap")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_RELEASE_EXISTS", "1")

    assert main(["snapshot", "publish", str(directory)]) == 0

    calls = gh_on_path()
    assert not [c for c in calls if c[:2] == ["release", "create"]]
    assert [c for c in calls if c[:2] == ["release", "upload"]]


def test_fr2_6_publish_refuses_a_snapshot_that_fails_verify(
    tmp_path, monkeypatch, gh_on_path, capsys
):
    directory = make_snapshot(tmp_path / "snap")
    (directory / "boundary.geojson").write_bytes(b"tampered")
    monkeypatch.chdir(tmp_path)

    assert main(["snapshot", "publish", str(directory)]) != 0

    assert not (tmp_path / "gh.log").exists()
    assert not (tmp_path / "snapshots").exists()


def test_fr2_7_pull_downloads_into_the_cache_and_verifies(
    tmp_path, monkeypatch, gh_on_path, capsys
):
    source = make_snapshot(tmp_path / "source")
    manifest = tmp_path / "snapshots/test-region/2026-10-01/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes((source / "manifest.json").read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_SOURCE", str(source))

    code = main(["snapshot", "pull", str(manifest)])

    cache = tmp_path / "data/cache/test-region/2026-10-01"
    assert code == 0
    for name, content in FILES.items():
        assert (cache / name).read_bytes() == content
    assert (cache / "manifest.json").exists()
    download = [c for c in gh_on_path() if c[:2] == ["release", "download"]]
    assert download[0][2] == "snapshot-test-region-2026-10-01"
    assert f"{name} ok" in capsys.readouterr().out


def test_fr2_7_pull_fails_when_a_downloaded_file_is_tampered(
    tmp_path, monkeypatch, gh_on_path, capsys
):
    source = make_snapshot(tmp_path / "source")
    manifest = tmp_path / "m/manifest.json"
    manifest.parent.mkdir()
    manifest.write_bytes((source / "manifest.json").read_bytes())
    (source / "network.osm.gz").write_bytes(b"tampered")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_SOURCE", str(source))

    code = main(["snapshot", "pull", str(manifest)])

    assert code != 0
    assert "network.osm.gz" in capsys.readouterr().err


def test_fr2_5_verify_runs_as_the_installed_command(tmp_path):
    directory = make_snapshot(tmp_path / "snap")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from bikeplan import main; sys.exit(main())",
            "snapshot",
            "verify",
            str(directory),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "boundary.geojson ok" in result.stdout
