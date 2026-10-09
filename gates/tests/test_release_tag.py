import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FAKE_GH = """import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as handle:
    handle.write(json.dumps(args) + "\\n")
if args[:2] == ["release", "view"]:
    sys.exit(1)
if args[:2] == ["release", "list"]:
    print("v-old")
if args[:2] == ["release", "download"]:
    target = Path(args[args.index("--dir") + 1])
    shutil.copytree(os.environ["PAST_FILES"], target)
"""
FAKE_BIKEPLAN = """import hashlib, sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("--out") + 1])
if args[0] == "checks":
    out.write_text("checks")
else:
    out.mkdir(parents=True)
    (out / "report.html").write_text("new report")
    digest = hashlib.sha256((out / "report.html").read_bytes()).hexdigest()
    (out / "SHA256SUMS").write_text(digest + "  report.html\\n")
"""


@pytest.mark.parametrize("matching_parent", [True, False])
def test_fr0_31_reuse_never_overwrites_a_past_tag(repo, tmp_path, matching_parent):
    repo.write("regions/council.yaml", 'id: council\nosm_date: "2026-10-01T00:00:00Z"\n')
    repo.write("snapshots/council/2026-10-01/manifest.json", "{}")
    repo.write("data/cache/council/2026-10-01/manifest.json", "{}")
    repo.write("artifacts/check.txt", "proof")
    parent = repo.commit("baseline")
    repo.write("README.md", "input change\n")
    repo.commit("docs only")
    past = tmp_path / "past"
    past.mkdir()
    (past / "index.html").write_text(parent if matching_parent else "stale")
    for name in ("council-report.html", "council.tar.gz"):
        (past / name).write_text("old bytes")
    (past / "SHA256SUMS").write_text(
        "".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
            for path in sorted(past.iterdir())
        )
    )
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in (("gh", FAKE_GH), ("bikeplan", FAKE_BIKEPLAN), ("pytest", "pass")):
        path = binaries / name
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)
    script = repo.path / "scripts/release.sh"
    script.parent.mkdir()
    shutil.copy(ROOT / "scripts/release.sh", script)
    log = tmp_path / "gh.jsonl"
    env = dict(os.environ)
    env.update(
        PATH=f"{binaries}{os.pathsep}{env['PATH']}",
        GH_LOG=str(log),
        PAST_FILES=str(past),
        BIKEPLAN=str(binaries / "bikeplan"),
        PYTEST=str(binaries / "pytest"),
    )
    result = subprocess.run(
        ["bash", str(script), "v-new"], cwd=repo.path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    mutations = [call for call in calls if call[1] in ("create", "upload", "edit", "delete")]
    assert mutations
    assert all(call[2] == "v-new" for call in mutations)


def test_fr0_31_skips_past_releases_without_an_index(repo, tmp_path):
    repo.write("regions/council.yaml", 'id: council\nosm_date: "2026-10-01T00:00:00Z"\n')
    repo.write("snapshots/council/2026-10-01/manifest.json", "{}")
    repo.write("data/cache/council/2026-10-01/manifest.json", "{}")
    repo.write("artifacts/check.txt", "proof")
    repo.commit("baseline")
    repo.write("README.md", "docs only\n")
    repo.commit("docs only")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    gh_body = (
        FAKE_GH.replace('print("v-old")', 'print("v-legacy")')
        .replace('print("index.html")', 'print("")')
        .replace(
            'target = Path(args[args.index("--dir") + 1])',
            'print("no assets match the file pattern", file=sys.stderr)\n    sys.exit(1)\n'
            '    target = Path(args[args.index("--dir") + 1])',
        )
    )
    for name, body in (("gh", gh_body), ("bikeplan", FAKE_BIKEPLAN), ("pytest", "pass")):
        path = binaries / name
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)
    script = repo.path / "scripts/release.sh"
    script.parent.mkdir()
    shutil.copy(ROOT / "scripts/release.sh", script)
    log = tmp_path / "gh.jsonl"
    env = dict(os.environ)
    env.update(
        PATH=f"{binaries}{os.pathsep}{env['PATH']}",
        GH_LOG=str(log),
        BIKEPLAN=str(binaries / "bikeplan"),
        PYTEST=str(binaries / "pytest"),
    )
    result = subprocess.run(
        ["bash", str(script), "v-new"], cwd=repo.path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert sum(call[:3] == ["release", "download", "v-legacy"] for call in calls) == 1
    assert "has no index" in result.stdout
    assert any(call[:3] == ["release", "upload", "v-new"] for call in calls)
