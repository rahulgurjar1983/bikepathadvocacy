import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITLEAKS = ROOT / ".tools" / "bin" / "gitleaks"


def scan(repo, base, binary):
    env = dict(os.environ, GITLEAKS_BIN=str(binary))
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / "secretscan.sh"), base],
        cwd=repo.path,
        env=env,
        capture_output=True,
        text=True,
    )


def planted_key():
    return "AKIA" + "Q7ZK4M2PXW6RT3VY"


def start(repo):
    repo.write("README.md", "start\n")
    base = repo.commit("base")
    repo.branch("loop/x")
    return base


def test_fr0_7_planted_key_fails(repo):
    base = start(repo)
    repo.write("settings.py", f'AWS_ACCESS_KEY_ID = "{planted_key()}"\n')
    repo.commit("oops")
    result = scan(repo, base, GITLEAKS)
    assert result.returncode == 1, result.stdout + result.stderr


def test_fr0_7_clean_range_passes(repo):
    base = start(repo)
    repo.write("settings.py", 'REGION = "ap-southeast-2"\n')
    repo.commit("clean")
    result = scan(repo, base, GITLEAKS)
    assert result.returncode == 0, result.stdout + result.stderr


def test_fr0_16_missing_gitleaks_fails_hard(repo):
    base = start(repo)
    result = scan(repo, base, "/nonexistent/gitleaks")
    assert result.returncode == 2
    assert "gitleaks" in result.stderr
