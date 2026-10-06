import os
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def smoke(env):
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / "smoke.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_fr11_2_smoke_fails_hard_without_docker(tmp_path):
    bash = Path("/usr/bin/bash")
    (tmp_path / "bash").symlink_to(bash)
    result = smoke({"PATH": str(tmp_path)})
    assert result.returncode != 0
    assert "docker" in result.stderr.lower()


def test_fr11_2_smoke_builds_image_and_runs_version_in_container():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    result = smoke(dict(os.environ))
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert f"bikeplan {version}" in result.stdout


def test_nfr8_image_runs_python_3_12_from_locked_environment():
    built = smoke(dict(os.environ))
    assert built.returncode == 0, built.stderr[-2000:]
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python", "bikeplan:smoke", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("Python 3.12.")
