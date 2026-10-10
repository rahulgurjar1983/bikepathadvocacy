import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from gates.tests.test_release_tag import FAKE_BIKEPLAN, FAKE_GH

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("private_field", ["review", "route", "claims", "region", "reply"])
def test_fr0_31_public_flag_cannot_publish_a_private_reference(repo, tmp_path, private_field):
    repo.write(".gitignore", "data/private/\ndata/cache/\n")
    region = 'id: council\nosm_date: "2026-10-01T00:00:00Z"\n'
    repo.write("regions/council.yaml", region)
    repo.write("snapshots/council/2026-10-01/manifest.json", "{}")
    repo.write("data/cache/council/2026-10-01/manifest.json", "{}")
    repo.write("artifacts/check.txt", "proof")
    files = {
        "review": repo.write(
            "routes/public/review.yaml",
            "public: true\nregion: region.yaml\nroute: route.gpx\n"
            "claims: claims.yaml\nreply: reply.md\n",
        ),
        "region": repo.write("routes/public/region.yaml", region),
        "route": repo.write("routes/public/route.gpx", "public route"),
        "claims": repo.write("routes/public/claims.yaml", "public claims"),
        "reply": repo.write("routes/public/reply.md", "public reply"),
    }
    repo.commit("public inputs")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in (("gh", FAKE_GH), ("bikeplan", FAKE_BIKEPLAN), ("pytest", "pass")):
        path = binaries / name
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)
    (repo.path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/release.sh", repo.path / "scripts/release.sh")
    output = tmp_path / "release"
    env = dict(os.environ)
    env.update(
        PATH=f"{binaries}{os.pathsep}{env['PATH']}",
        PYTHONPATH=str(tmp_path / "no-importable-packages"),
        GH_LOG=str(tmp_path / "gh.jsonl"),
        BIKEPLAN=str(binaries / "bikeplan"),
        PYTEST=str(binaries / "pytest"),
        RELEASE_OUT=str(output),
    )
    args = ["bash", "scripts/release.sh", "v-portable"]
    public = subprocess.run(args, cwd=repo.path, env=env, capture_output=True, text=True)
    assert public.returncode == 0, public.stdout + public.stderr
    assert (output / "public-review.html").exists()
    shutil.rmtree(output)
    private = repo.write("data/private/hidden.yaml", files[private_field].read_text())
    files[private_field].unlink()
    files[private_field].symlink_to(private)
    hidden = subprocess.run(args, cwd=repo.path, env=env, capture_output=True, text=True)
    assert hidden.returncode == 0, hidden.stdout + hidden.stderr
    assert (output / "council-report.html").exists()
    assert not (output / "public-review.html").exists()
    assert not (output / "public.tar.gz").exists()
    assert "private review excluded" in hidden.stdout


def test_fr0_31_release_excludes_a_private_symlink_without_hiding_other_errors(repo, tmp_path):
    repo.write(".gitignore", "data/private/\ndata/cache/\n")
    region = 'id: council\nosm_date: "2026-10-01T00:00:00Z"\n'
    repo.write("regions/council.yaml", region)
    repo.write("snapshots/council/2026-10-01/manifest.json", "{}")
    repo.write("data/cache/council/2026-10-01/manifest.json", "{}")
    repo.write("artifacts/check.txt", "proof")
    private = repo.write(
        "data/private/secret/review.yaml",
        "public: true\nregion: region.yaml\nroute: route.gpx\nclaims: claims.yaml\n",
    ).parent
    repo.write("data/private/secret/region.yaml", region)
    repo.write("data/private/secret/route.gpx", "private route")
    repo.write("data/private/secret/claims.yaml", "private claims")
    (repo.path / "routes").mkdir()
    (repo.path / "routes/secret").symlink_to(private, target_is_directory=True)
    repo.commit("public data and a misplaced flag")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in (("gh", FAKE_GH), ("bikeplan", FAKE_BIKEPLAN), ("pytest", "pass")):
        path = binaries / name
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)
    (repo.path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/release.sh", repo.path / "scripts/release.sh")
    output = tmp_path / "release"
    env = dict(os.environ)
    env.update(
        PATH=f"{binaries}{os.pathsep}{env['PATH']}",
        PYTHONPATH=str(ROOT),
        GH_LOG=str(tmp_path / "gh.jsonl"),
        BIKEPLAN=str(binaries / "bikeplan"),
        PYTEST=str(binaries / "pytest"),
        RELEASE_OUT=str(output),
    )
    result = subprocess.run(
        ["bash", "scripts/release.sh", "v-safe"],
        cwd=repo.path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (output / "council-report.html").exists()
    assert not (output / "secret-review.html").exists()
    assert not (output / "secret.tar.gz").exists()
    assert "private review excluded" in result.stdout
    (repo.path / "routes/secret").unlink()
    repo.write("routes/broken/review.yaml", "public: true\nregion: absent.yaml\n")
    failed = subprocess.run(
        ["bash", "scripts/release.sh", "v-broken"],
        cwd=repo.path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
